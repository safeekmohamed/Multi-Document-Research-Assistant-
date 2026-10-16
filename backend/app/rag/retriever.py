import math
import os
import re
import logging
import time
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from sentence_transformers import CrossEncoder

from app.database.mongodb import documents_collection
from app.core.model_cache import synchronized_lru_cache
from app.documents.document_service import classify_document
from app.rag.vector_store import (
    get_all_user_chunks,
    search_semantic,
    search_semantic_by_sources,
)


logger = logging.getLogger(__name__)
RERANK_CANDIDATES_PER_SOURCE = 12


WORD_PATTERN = re.compile(r"[a-zA-Z0-9]+")


SECTION_QUERY_PATTERNS = [
    r"\bsection\s+([0-9]+(?:\.[0-9]+)*)\b",
    r"\bchapter\s+([0-9]+(?:\.[0-9]+)*)\b",
    r"\bpart\s+([0-9]+(?:\.[0-9]+)*)\b",
]


ALL_SOURCE_PHRASES = {
    "all documents",
    "all files",
    "all sources",
    "all my documents",
    "all my files",
    "show all documents",
    "show all files",
    "list all documents",
    "list all files",
    "every document",
    "every file",
    "my documents",
    "my files",
    "my sources",
}


SOURCE_DISCOVERY_ACTIONS = {
    "all",
    "available",
    "display",
    "every",
    "find",
    "list",
    "show",
    "uploaded",
}


SOURCE_CONTENT_TERMS = {
    "about",
    "contain",
    "contains",
    "content",
    "explain",
    "mention",
    "mentions",
    "say",
    "says",
    "skill",
    "skills",
    "summarize",
    "summary",
    "with",
    "what",
    "which",
}


COMPARISON_WORDS = {
    "compare",
    "comparison",
    "difference",
    "differences",
    "similarities",
    "similarity",
    "both",
    "between",
    "versus",
    "vs",
    "shared",
    "common",
}


DEFINITION_QUERY_PATTERNS = (
    r"^(?:what\s+is|what\s+are)\s+(.+?)\s*[?.!]*$",
    r"^what\s+does\s+(.+?)\s+(?:mean|stand\s+for)\s*[?.!]*$",
    r"^(?:define|definition\s+of|explanation\s+of|meaning\s+of|explain|describe)\s+(.+?)\s*[?.!]*$",
)


DEFINITION_PREDICATE = re.compile(
    r"^(?:(?:typically|generally|often|usually|commonly|primarily)\s+)?"
    r"(?:is|are|was|were|means|refers?\s+to|stands?\s+for|denotes?|"
    r"represents?|describes?|defines?|signifies?|consists?\s+of|"
    r"uses?|employs?|relies?\s+on|operates?|functions?|works?|"
    r"have?\s+become|are\s+trained|are\s+designed|can\s+be|"
    r"may\s+be|enables?|allows?|provides?|supports?)\b",
    re.IGNORECASE,
)


RESUME_DOCUMENT_TYPES = {
    "resume",
    "cv",
    "curriculum_vitae",
}


DOCUMENT_DISCOVERY_TERMS = {
    "resume",
    "resumes",
    "cv",
    "cvs",
}


DOCUMENT_DISCOVERY_ACTIONS = {
    "what",
    "which",
    "list",
    "show",
    "display",
    "find",
    "available",
    "there",
    "have",
    "exist",
    "uploaded",
    "upload",
}


RESUME_CONTENT_TERMS = {
    "skill",
    "skills",
    "experience",
    "education",
    "qualification",
    "qualifications",
    "project",
    "projects",
    "certificate",
    "certificates",
    "certification",
    "certifications",
    "llm",
    "python",
    "java",
    "javascript",
    "react",
    "nextjs",
    "next",
    "sql",
    "developer",
    "internship",
    "internships",
    "work",
    "job",
    "role",
    "roles",
    "technology",
    "technologies",
    "tool",
    "tools",
}


RESUME_QUERY_INTENT_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "both",
    "common",
    "contain",
    "contains",
    "cv",
    "cvs",
    "do",
    "does",
    "experience",
    "find",
    "has",
    "have",
    "in",
    "is",
    "list",
    "mention",
    "mentioned",
    "mentions",
    "my",
    "of",
    "resume",
    "resumes",
    "shared",
    "show",
    "skill",
    "skills",
    "technology",
    "technologies",
    "the",
    "their",
    "uploaded",
    "what",
    "which",
    "your",
}


# ============================================================
# RERANKER
# ============================================================

@synchronized_lru_cache(maxsize=1)
def get_reranker():
    model_name = os.getenv(
        "RERANKER_MODEL",
        "cross-encoder/ms-marco-MiniLM-L6-v2",
    )

    started_at = time.perf_counter()
    logger.info("Loading cross-encoder reranker: model=%s", model_name)
    try:
        model = CrossEncoder(model_name)
    except Exception:
        logger.exception(
            "Cross-encoder initialization failed: model=%s elapsed_seconds=%.3f",
            model_name,
            time.perf_counter() - started_at,
        )
        raise
    logger.info(
        "Cross-encoder initialized: model=%s elapsed_seconds=%.3f",
        model_name,
        time.perf_counter() - started_at,
    )
    return model


# ============================================================
# BASIC TEXT HELPERS
# ============================================================

def tokenize(
    text: str,
) -> list[str]:
    if not text:
        return []

    return [
        token.lower()
        for token in WORD_PATTERN.findall(
            str(text)
        )
    ]


def keyword_score(
    query: str,
    text: str,
) -> float:
    query_tokens = set(
        tokenize(query)
    )

    text_tokens = set(
        tokenize(text)
    )

    if not query_tokens or not text_tokens:
        return 0.0

    overlap = query_tokens.intersection(
        text_tokens
    )

    return len(overlap) / len(
        query_tokens
    )


def bm25_candidates(
    query: str,
    chunks: dict,
    source_filter: dict | None = None,
) -> list[dict]:
    """Rank the user's complete indexed corpus with an independent BM25 pass."""
    query_terms = tokenize(query)
    ids = chunks.get("ids", []) or []
    documents = chunks.get("documents", []) or []
    metadatas = chunks.get("metadatas", []) or []
    if not query_terms or not documents:
        return []

    eligible = [
        index
        for index in range(len(documents))
        if source_matches_filter(
            metadatas[index] if index < len(metadatas) else {}, source_filter
        )
    ]
    documents = [documents[index] for index in eligible]
    ids = [ids[index] for index in eligible if index < len(ids)]
    metadatas = [metadatas[index] for index in eligible if index < len(metadatas)]
    tokenized = [tokenize(text) for text in documents]
    count = len(tokenized)
    average_length = sum(map(len, tokenized)) / max(count, 1)
    document_frequency = {}
    for terms in tokenized:
        for term in set(terms):
            document_frequency[term] = document_frequency.get(term, 0) + 1

    scored = []
    k1, b = 1.5, 0.75
    for index, terms in enumerate(tokenized):
        metadata = metadatas[index] if index < len(metadatas) else {}
        metadata = metadata or {}
        frequencies = {}
        for term in terms:
            frequencies[term] = frequencies.get(term, 0) + 1
        length = len(terms)
        score = 0.0
        for term in query_terms:
            frequency = frequencies.get(term, 0)
            if not frequency:
                continue
            df = document_frequency.get(term, 0)
            inverse_frequency = math.log(1 + (count - df + 0.5) / (df + 0.5))
            denominator = frequency + k1 * (1 - b + b * length / max(average_length, 1))
            score += inverse_frequency * frequency * (k1 + 1) / denominator
        if score > 0:
            scored.append((score, index, metadata))

    if not scored:
        return []
    maximum = max(score for score, _, _ in scored)
    candidates = []
    for score, index, metadata in scored:
        normalized_score = score / maximum
        candidates.append({
            "id": ids[index] if index < len(ids) else f"bm25-{index}",
            "content": str(documents[index] or ""),
            "metadata": metadata,
            "score": normalized_score,
            "base_relevance_score": 0.0,
            "semantic_score": 0.0,
            "lexical_score": normalized_score,
            "bm25_score": normalized_score,
            "content_keyword_score": keyword_score(query, str(documents[index] or "")),
            "preferred": False,
            "ranking_boost": 0.0,
        })
    return candidates


def merge_retrieval_candidates(*candidate_sets: list[dict]) -> list[dict]:
    """Union semantic and lexical results while retaining both score signals."""
    merged = {}
    for candidates in candidate_sets:
        for candidate in candidates or []:
            key = str(candidate.get("id") or "")
            if not key:
                continue
            current = merged.get(key)
            if current is None:
                merged[key] = dict(candidate)
                continue
            for field in ("lexical_score", "bm25_score", "content_keyword_score"):
                current[field] = max(
                    float(current.get(field) or 0.0),
                    float(candidate.get(field) or 0.0),
                )
            if not current.get("semantic_score") and candidate.get("semantic_score"):
                current["semantic_score"] = candidate["semantic_score"]
                current["base_relevance_score"] = candidate.get("base_relevance_score", 0.0)
    return list(merged.values())


def _searched_sources(
    semantic_metadatas: list[dict],
    lexical_metadatas: list[dict],
) -> list[dict]:
    """Return sources represented in the semantic results or BM25 scope."""
    sources = {}
    for metadata in [*semantic_metadatas, *lexical_metadatas]:
        if not isinstance(metadata, dict):
            continue
        filename = metadata.get("filename") or metadata.get("title")
        url = metadata.get("url") or metadata.get("source_url")
        source_type = metadata.get("source_type") or ("url" if url else "file")
        if source_type == "url":
            continue
        source_id = metadata.get("source_id")
        identity = (
            str(source_id)
            if source_id
            else str(url).strip().rstrip("/").casefold()
            if url
            else str(filename).strip().casefold()
            if filename
            else ""
        )
        if not identity:
            continue
        sources.setdefault(
            identity,
            {
                "filename": str(filename or url or "Unknown source"),
                "source_id": source_id,
                "source_type": source_type,
                "url": url,
                "document_type": metadata.get("document_type"),
            },
        )
    return list(sources.values())


def normalize_query(
    query: str,
) -> str:
    if not query:
        return ""

    return re.sub(
        r"\s+",
        " ",
        str(query).strip(),
    )


# ============================================================
# DEFINITION DETECTION
# ============================================================

def extract_definition_topic(
    query: str,
) -> str | None:
    normalized = normalize_query(query)

    if not normalized:
        return None

    for pattern in DEFINITION_QUERY_PATTERNS:
        match = re.match(
            pattern,
            normalized,
            flags=re.IGNORECASE,
        )

        if not match:
            continue

        topic = match.group(
            1
        ).strip(
            " \t\r\n?.!,;:"
        )

        topic = re.sub(
            r"^(?:(?:the\s+)?(?:concept|term|notion)\s+of\s+|(?:a|an|the)\s+)+",
            "",
            topic,
            flags=re.IGNORECASE,
        ).strip()

        if (
            topic
            and not re.fullmatch(
                r"(?:section|chapter|point|part|topic)\s+\d+(?:\.\d+)*",
                topic,
                flags=re.IGNORECASE,
            )
            and topic.casefold()
            not in {
                "it",
                "this",
                "that",
                "these",
                "those",
            }
        ):
            return topic

    return None


def is_definition_query(
    query: str,
) -> bool:
    return (
        extract_definition_topic(query)
        is not None
    )


def definition_evidence_score(
    topic: str,
    text: str,
) -> float:
    topic_tokens = tokenize(
        topic
    )

    if not topic_tokens or not text:
        return 0.0

    topic_pattern = (
        r"\b"
        + r"[\s-]+".join(
            re.escape(token)
            for token in topic_tokens
        )
        + r"s?\b"
    )

    topic_match_pattern = re.compile(
        topic_pattern,
        re.IGNORECASE,
    )

    evidence = 0.0

    sentences = re.split(
        r"(?<=[.!?])\s+|\n+",
        text,
    )

    for sentence in sentences:
        for match in topic_match_pattern.finditer(
            sentence
        ):
            following = sentence[
                match.end():
            ].lstrip(
                " \t,;:-"
            )

            predicate = (
                DEFINITION_PREDICATE.match(
                    following
                )
            )

            if not predicate:
                continue

            predicate_text = (
                predicate.group(0).lower()
            )

            if re.match(
                r"^(?:is|are)\s+(?:an?\s+)?(?:(?:important|key|major|essential)\s+)?(?:component|part|aspect|element)\s+of\b",
                following,
                flags=re.IGNORECASE,
            ):
                evidence = max(
                    evidence,
                    0.10,
                )

            elif re.match(
                r"^(?:is|are|was|were|means|refers?\s+to|stands?\s+for|denotes?|represents?|defines?|signifies?|consists?\s+of)\b",
                following,
                flags=re.IGNORECASE,
            ):
                evidence = max(
                    evidence,
                    0.95,
                )

            else:
                evidence = max(
                    evidence,
                    0.72
                    if predicate_text
                    else 0.0,
                )

    topic_compact = "".join(
        topic_tokens
    ).upper()

    topic_acronym = (
        topic_compact[:-1]
        if topic_compact.endswith("S")
        else topic_compact
    )

    acronym_pattern = re.compile(
        r"(?P<expansion>\b[A-Za-z][A-Za-z-]*(?:\s+[A-Za-z][A-Za-z-]*){1,5})"
        r"\s*\(\s*(?P<acronym>[A-Z][A-Z0-9-]{1,9})(?P<plural>s?)\s*\)",
    )

    for match in acronym_pattern.finditer(
        text
    ):
        expansion_tokens = tokenize(
            match.group(
                "expansion"
            )
        )

        initials = "".join(
            token[0].upper()
            for token in expansion_tokens
            if token
        )

        acronym = match.group(
            "acronym"
        ).upper()

        if not (
            acronym == topic_acronym
            or initials == topic_acronym
        ):
            continue

        following = text[
            match.end():
        ].lstrip(
            " \t,;:-"
        )

        predicate = (
            DEFINITION_PREDICATE.match(
                following
            )
        )

        evidence = max(
            evidence,
            0.95 if predicate else 0.15,
        )

    return evidence


# ============================================================
# SOURCE / METADATA HELPERS
# ============================================================

def get_source_key(
    metadata: dict,
    chunk_id: str | None = None,
) -> str:
    if not metadata:
        return chunk_id or ""

    for key in (
        "source_id",
        "document_id",
        "file_id",
        "filename",
        "source",
        "url",
    ):
        value = metadata.get(
            key
        )

        if value:
            return str(
                value
            )

    return chunk_id or ""


def get_source_display_name(
    metadata: dict,
    fallback: str = "",
) -> str:
    if not metadata:
        return fallback

    for key in (
        "filename",
        "source",
        "url",
    ):
        value = metadata.get(
            key
        )

        if value:
            return str(
                value
            )

    return fallback


def get_normalized_source_key(
    metadata: dict,
    chunk_id: str | None = None,
) -> str:
    """Return a stable document identity for grouping and deduplication."""
    if metadata:
        source_id = (
            metadata.get("source_id")
            or metadata.get("document_id")
            or metadata.get("file_id")
        )
        if source_id:
            return str(source_id).casefold()

        source_url = metadata.get("url") or metadata.get("source_url")
        if source_url:
            return str(source_url).strip().rstrip("/").casefold()

    display = get_source_display_name(metadata, fallback=get_source_key(metadata, chunk_id))
    if not display:
        return get_source_key(metadata, chunk_id) or ""
    normalized = normalize_source_name(display)
    return normalized or get_source_key(metadata, chunk_id) or ""


def get_metadata_file_type(
    metadata: dict,
) -> str:
    if not metadata:
        return ""

    value = (
        metadata.get(
            "file_type"
        )
        or metadata.get(
            "extension"
        )
        or ""
    )

    value = str(
        value
    ).lower().strip()

    if value.startswith("."):
        value = value[1:]

    return value


def get_document_type(
    metadata: dict,
) -> str:
    if not metadata:
        return "other"

    value = metadata.get(
        "document_type"
    )

    if value:
        return str(
            value
        ).lower().strip()

    return "other"


def is_resume_metadata(
    metadata: dict,
) -> bool:
    if not metadata:
        return False

    document_type = get_document_type(
        metadata
    )

    if document_type in RESUME_DOCUMENT_TYPES:
        return True

    if document_type not in {
        "",
        "other",
    }:
        return False

    filename = str(
        metadata.get(
            "filename",
            "",
        )
    )

    filename = re.sub(
        r"([a-z])([A-Z])",
        r"\1 \2",
        filename,
    )

    filename = re.sub(
        r"[_-]+",
        " ",
        filename,
    ).lower()

    filename_without_extension = (
        Path(filename).stem
        if filename
        else ""
    )

    resume_patterns = [
        r"\bresume\b",
        r"resume$",
        r"\bcv\b",
        r"\bcurriculum[_\-\s]?vitae\b",
    ]

    return any(
        re.search(
            pattern,
            filename_without_extension,
        )
        for pattern in resume_patterns
    )


# ============================================================
# RESUME DISCOVERY
# ============================================================

def is_resume_discovery_query(
    query: str,
) -> bool:
    normalized = normalize_query(
        query
    ).lower()

    if not normalized:
        return False

    words = set(
        tokenize(normalized)
    )

    if not words.intersection(
        DOCUMENT_DISCOVERY_TERMS
    ):
        return False

    if words.intersection(
        RESUME_CONTENT_TERMS
    ):
        return False

    return bool(
        words.intersection(
            DOCUMENT_DISCOVERY_ACTIONS
        )
        or normalized.startswith(
            "what resumes"
        )
        or normalized.startswith(
            "which resumes"
        )
        or normalized.startswith(
            "list resumes"
        )
        or normalized.startswith(
            "show resumes"
        )
        or normalized.startswith(
            "what are resumes"
        )
        or normalized.startswith(
            "what resume"
        )
        or normalized.startswith(
            "which resume"
        )
    )


def is_resume_content_query(
    query: str,
) -> bool:
    normalized = normalize_query(
        query
    ).lower()

    if not normalized:
        return False

    words = set(
        tokenize(normalized)
    )

    has_resume_reference = bool(
        words.intersection(
            DOCUMENT_DISCOVERY_TERMS
        )
        or re.search(
            r"\b[a-z][a-z0-9-]{2,}['’]s\b",
            normalized,
        )
    )

    if not has_resume_reference:
        return False

    return bool(
        words.intersection(
            RESUME_CONTENT_TERMS
        )
        or words.intersection(
            COMPARISON_WORDS
        )
        or "in which resume" in normalized
        or "which resume has" in normalized
        or "which resume contains" in normalized
        or "resume is" in normalized
        or "resumes have" in normalized
        or "resumes contain" in normalized
    )


# ============================================================
# SOURCE NAME NORMALIZATION
# ============================================================

def normalize_source_name(
    value: str,
) -> str:
    if not value:
        return ""

    value = str(
        value
    )

    value = re.sub(
        r"([a-z])([A-Z])",
        r"\1 \2",
        value,
    )

    value = re.sub(
        r"\.(pdf|docx|doc|txt|csv|xlsx|pptx)$",
        "",
        value,
        flags=re.IGNORECASE,
    )

    value = re.sub(
        r"\([^)]*\)|\[[^]]*\]",
        " ",
        value,
    )

    value = value.lower()

    value = value.replace(
        "_",
        " ",
    )

    value = value.replace(
        "-",
        " ",
    )

    value = re.sub(
        r"\b(?:resumes?|cvs?|curriculum|vitae)\b",
        " ",
        value,
    )

    tokens = [
        token
        for token in value.split()
        if not token.isdigit()
        and not re.fullmatch(
            r"20\d{2,}",
            token,
        )
        and token not in {
            "final",
            "latest",
            "updated",
            "copy",
            "version",
        }
    ]

    value = " ".join(
        tokens
    )

    value = re.sub(
        r"\s+",
        " ",
        value,
    )

    return value.strip()


def source_name_matches_query(
    query: str,
    source_name: str,
) -> bool:
    if not query or not source_name:
        return False

    normalized_query = normalize_source_name(
        query
    )

    normalized_source = normalize_source_name(
        source_name
    )

    if not normalized_source:
        return False

    if normalized_source in normalized_query:
        return True

    possessive_names = re.findall(
        r"\b([a-z][a-z0-9-]{2,})['’]s\b",
        str(query).lower(),
    )

    source_tokens = set(
        tokenize(normalized_source)
    )

    if any(
        name in source_tokens
        or any(
            token.startswith(name)
            for token in source_tokens
        )
        for name in possessive_names
    ):
        return True

    query_tokens = set(
        tokenize(normalized_query)
    )

    if not source_tokens:
        return False

    matched = source_tokens.intersection(
        query_tokens
    )

    return len(matched) == len(
        source_tokens
    )


def detect_named_sources(
    query: str,
    raw_results,
) -> list[str]:
    if not raw_results:
        return []

    metadatas = raw_results.get(
        "metadatas",
        [],
    )

    discovered = {}

    for metadata_group in metadatas:

        if isinstance(
            metadata_group,
            list,
        ):
            metadata_items = (
                metadata_group
            )
        else:
            metadata_items = [
                metadata_group
            ]

        for metadata in metadata_items:

            if not isinstance(
                metadata,
                dict,
            ):
                continue

            filename = str(
                metadata.get(
                    "filename",
                    "",
                )
            )

            source = get_source_key(
                metadata
            )

            display = (
                filename
                or source
            )

            if not display:
                continue

            normalized = normalize_source_name(
                display
            )

            if not normalized:
                continue

            if source_name_matches_query(
                query,
                display,
            ):
                discovered.setdefault(
                    normalized,
                    display,
                )

    return list(
        discovered.values()
    )


def get_resume_query_subject_terms(
    query: str,
    raw_results,
) -> set[str]:
    query_terms = set(
        tokenize(query)
    )

    named_source_terms = {
        token
        for source_name in detect_named_sources(
            query,
            raw_results,
        )
        for token in tokenize(
            normalize_source_name(
                source_name
            )
        )
    }

    return query_terms.difference(
        RESUME_QUERY_INTENT_WORDS
    ).difference(
        named_source_terms
    )


# ============================================================
# FILE TYPE DETECTION
# ============================================================

def detect_requested_file_type(
    query: str,
) -> str | None:
    normalized = normalize_query(
        query
    ).lower()

    if not normalized:
        return None

    extensions = {
        "pdf": "pdf",
        "pdfs": "pdf",
        "docx": "docx",
        "word": "docx",
        "txt": "txt",
        "text": "txt",
        "csv": "csv",
        "excel": "xlsx",
        "xlsx": "xlsx",
        "powerpoint": "pptx",
        "pptx": "pptx",
    }

    words = set(
        tokenize(normalized)
    )

    for word, file_type in extensions.items():
        if word in words:
            return file_type

    return None


# ============================================================
# ALL SOURCE / DOCUMENT DISCOVERY
# ============================================================

def is_all_sources_query(
    query: str,
) -> bool:
    normalized = normalize_query(
        query
    ).lower()

    if not normalized:
        return False

    if normalized in ALL_SOURCE_PHRASES:
        return True

    words = set(
        tokenize(normalized)
    )

    source_terms = {
        "documents",
        "document",
        "files",
        "file",
        "sources",
        "source",
    }

    if not words.intersection(
        source_terms
    ):
        return False

    if words.intersection(
        SOURCE_DISCOVERY_ACTIONS
    ):
        return not words.intersection(
            SOURCE_CONTENT_TERMS
            - {
                "what",
                "which",
            }
        )

    normalized_words = (
        f" {normalized.strip(' .?!')} "
    )

    return any(
        phrase in normalized_words
        for phrase in (
            " what files do i have ",
            " what documents do i have ",
            " what sources do i have ",
            " what files are available ",
            " what documents are available ",
            " what files are in my ",
            " what documents are in my ",
            " what do i have ",
            " what have i uploaded ",
            " what are my ",
            " what is in my ",
            " which do i have ",
            " which are my ",
            " are there any ",
        )
    )


def is_comparison_query(
    query: str,
) -> bool:
    words = set(
        tokenize(query)
    )

    return bool(
        words.intersection(
            COMPARISON_WORDS
        )
    )


# ============================================================
# SOURCE FILTER DETECTION
# ============================================================

def detect_source_filter(
    query: str,
    raw_results,
) -> dict | None:
    normalized_query = normalize_query(query).casefold()
    named_sources = [
        source_name
        for source_name in detect_named_sources(query, raw_results)
        if (
            str(source_name).casefold() in normalized_query
            and bool(
                re.search(
                    r"\.(?:pdf|docx?|txt|csv|xlsx|pptx)\b",
                    normalized_query,
                )
            )
            or re.search(
                rf"\b(?:in|from|within|according\s+to|based\s+on)\s+(?:the\s+)?{re.escape(normalize_source_name(source_name))}\b",
                normalize_source_name(query),
                flags=re.IGNORECASE,
            )
        )
    ]

    if len(named_sources) >= 2:
        return {
            "type": "filenames",
            "filenames": named_sources,
        }

    if len(named_sources) == 1:
        return {
            "type": "filename",
            "filename": named_sources[0],
        }

    file_type = detect_requested_file_type(
        query
    )

    if file_type:
        return {
            "type": "file_type",
            "file_type": file_type,
        }

    normalized = normalize_query(
        query
    ).lower()

    if (
        "url" in normalized
        or "website" in normalized
        or "web page" in normalized
        or "webpage" in normalized
    ):
        return {
            "type": "url",
        }

    return None


def source_matches_filter(
    metadata: dict,
    source_filter: dict | None,
) -> bool:
    if not source_filter:
        return True

    filter_type = source_filter.get("type")
    if filter_type == "sources":
        source_id = str(metadata.get("source_id") or "")
        filename = str(metadata.get("filename") or "").casefold()
        url = str(metadata.get("url") or "").casefold()
        for source in source_filter.get("sources", []):
            if not isinstance(source, dict):
                continue
            allowed_id = str(source.get("source_id") or "")
            allowed_filename = str(source.get("filename") or "").casefold()
            allowed_url = str(source.get("url") or "").casefold()
            if allowed_id and allowed_id == source_id:
                return True
            if allowed_filename and allowed_filename == filename:
                return True
            if allowed_url and allowed_url == url:
                return True
        return False
    if filter_type == "filename":
        return source_name_matches_query(
            source_filter.get("filename", ""),
            str(metadata.get("filename", "")),
        )
    if filter_type == "filenames":
        return any(
            source_matches_filter(
                metadata,
                {"type": "filename", "filename": filename},
            )
            for filename in source_filter.get("filenames", [])
        )
    if filter_type == "file_type":
        return get_metadata_file_type(metadata) == source_filter.get("file_type")
    if filter_type == "url":
        return str(metadata.get("source_type", "")).lower() == "url"
    return True


def detect_requested_section(query: str) -> str | None:
    text = normalize_query(query).lower()
    for pattern in SECTION_QUERY_PATTERNS:
        match = re.search(pattern, text)
        if match:
            return match.group(1)
    match = re.search(
        r"\b(?:point|item|step)\s+([0-9]+(?:\.[0-9]+)*)\b",
        text,
    )
    return match.group(1) if match else None


def expand_parent_section(
    user_id: str,
    requested_section: str,
    candidates: list[dict],
    source_filter: dict | None = None,
    limit: int | None = 24,
) -> list[dict]:
    if not requested_section or not candidates:
        return candidates

    relevant_candidates = [
        candidate
        for candidate in candidates
        if source_matches_filter(
            candidate.get("metadata", {}), source_filter
        )
    ]
    # Normalize source keys so expansion matches regardless of minor
    # metadata differences across chunks from the same file.
    matched_sources = {
        get_normalized_source_key(candidate.get("metadata", {}), candidate.get("id", ""))
        for candidate in relevant_candidates
    }
    if not matched_sources:
        return candidates

    try:
        chunks = get_all_user_chunks(user_id)
    except Exception as error:
        print(f"Section expansion warning: {error}")
        return candidates

    ids = chunks.get("ids", [])
    documents = chunks.get("documents", [])
    metadatas = chunks.get("metadatas", [])
    existing_ids = {candidate.get("id") for candidate in candidates}
    expanded = list(relevant_candidates)
    escaped_section = re.escape(requested_section)
    section_pattern = re.compile(
        rf"(?m)^\s*{escaped_section}(?:\s|[.):\-])"
    )

    for index, chunk_id in enumerate(ids):
        if chunk_id in existing_ids or index >= len(documents) or index >= len(metadatas):
            continue
        text = str(documents[index] or "")
        metadata = metadatas[index] or {}
        if not section_pattern.search(text):
            continue
        if not source_matches_filter(metadata, source_filter):
            continue
        if get_normalized_source_key(metadata, chunk_id) not in matched_sources:
            continue
        expanded.append({
            "id": chunk_id,
            "content": text,
            "metadata": metadata,
            "score": 0.0,
            "base_relevance_score": 0.0,
            "semantic_score": 0.0,
            "lexical_score": 0.0,
            "content_keyword_score": 0.0,
            "preferred": False,
            "ranking_boost": 0.0,
            "section_expanded": True,
        })
        existing_ids.add(chunk_id)
        if limit is not None and len(expanded) >= limit:
            break
    return expanded


def get_user_file_metadata(user_id: str) -> list[dict]:
    return list(documents_collection.find(
        {"user_id": user_id},
        {"_id": 0},
    ))


def source_metadata_filter(metadata: dict) -> dict | None:
    source_id = metadata.get("source_id")
    if source_id:
        return {"source_id": str(source_id)}
    filename = metadata.get("filename")
    if filename:
        return {"filename": str(filename)}
    url = metadata.get("url")
    if url:
        return {"url": str(url)}
    return None


def source_matches_preference(metadata: dict, preferred_sources) -> bool:
    if not preferred_sources:
        return False
    for source in preferred_sources:
        if isinstance(source, dict):
            source = source.get("filename") or source.get("source") or source.get("url")
        if source and source_name_matches_query(
            str(source),
            str(metadata.get("filename") or metadata.get("url") or ""),
        ):
            return True
    return False


def apply_preferred_sources(
    candidates: list[dict],
    preferred_sources: list | None = None,
) -> list[dict]:
    if not preferred_sources:
        return candidates
    for candidate in candidates:
        if source_matches_preference(
            candidate.get("metadata", {}), preferred_sources
        ):
            candidate["preferred"] = True
    return candidates


def filter_resume_query_candidates(
    query: str,
    candidates: list[dict],
) -> list[dict]:
    if not is_resume_content_query(query):
        return candidates
    resume_candidates = filter_resume_candidates(candidates)
    return resume_candidates


def filter_resume_candidates(candidates: list[dict]) -> list[dict]:
    return [
        candidate
        for candidate in candidates
        if is_resume_metadata(candidate.get("metadata", {}))
    ]


def discover_resumes(
    user_id: str,
    limit: int | None = None,
) -> list[dict]:
    try:
        documents = get_user_file_metadata(user_id)
    except Exception as error:
        raise RuntimeError(
            f"Could not load the user's document metadata for resume discovery: {error}"
        ) from error

    resumes = [
        metadata
        for metadata in documents
        if is_resume_metadata(metadata)
    ]

    legacy_documents = [
        metadata
        for metadata in documents
        if get_document_type(metadata) in {"", "other"}
        and not is_resume_metadata(metadata)
        and str(metadata.get("source_type", "")).lower() != "url"
        and not metadata.get("source_url")
        and not metadata.get("url")
    ]
    if legacy_documents:
        try:
            chunks = get_all_user_chunks(user_id)
        except Exception as error:
            raise RuntimeError(
                f"Could not inspect indexed content for legacy resume detection: {error}"
            ) from error

        grouped_chunks: dict[tuple[str, str], list[dict]] = {}
        for text, chunk_metadata in zip(
            chunks.get("documents", []),
            chunks.get("metadatas", []),
        ):
            chunk_metadata = chunk_metadata or {}
            source_id = chunk_metadata.get("source_id")
            filename = str(chunk_metadata.get("filename") or "").casefold()
            page = {"text": str(text or "")}

            if source_id:
                grouped_chunks.setdefault(
                    ("source_id", str(source_id)),
                    [],
                ).append(page)
            if filename:
                grouped_chunks.setdefault(
                    ("filename", filename),
                    [],
                ).append(page)

        for metadata in legacy_documents:
            source_id = metadata.get("source_id")
            filename = str(metadata.get("filename") or "").casefold()
            pages = (
                grouped_chunks.get(("source_id", str(source_id)), [])
                if source_id
                else []
            )
            if not pages and filename:
                pages = grouped_chunks.get(("filename", filename), [])
            if not pages:
                continue

            document_type, confidence = classify_document(
                str(metadata.get("filename") or ""),
                pages,
            )
            if (
                document_type in RESUME_DOCUMENT_TYPES
                and confidence >= 0.6
            ):
                resumes.append(
                    {
                        **metadata,
                        "document_type": document_type,
                        "document_type_confidence": confidence,
                    }
                )

    return resumes if limit is None else resumes[:limit]


def build_candidates(
    query: str,
    raw_results: dict,
    source_filter: dict | None = None,
) -> list[dict]:
    ids_groups = raw_results.get("ids", [])
    documents_groups = raw_results.get("documents", [])
    metadata_groups = raw_results.get("metadatas", [])
    distance_groups = raw_results.get("distances", [])
    ids = ids_groups[0] if ids_groups and isinstance(ids_groups[0], list) else ids_groups
    documents = documents_groups[0] if documents_groups and isinstance(documents_groups[0], list) else documents_groups
    metadatas = metadata_groups[0] if metadata_groups and isinstance(metadata_groups[0], list) else metadata_groups
    distances = distance_groups[0] if distance_groups and isinstance(distance_groups[0], list) else distance_groups
    candidates = []
    for index, chunk_id in enumerate(ids):
        if index >= len(documents) or index >= len(metadatas):
            continue
        metadata = metadatas[index] or {}
        if not source_matches_filter(metadata, source_filter):
            continue
        try:
            distance = float(distances[index]) if index < len(distances) else 1.0
        except (TypeError, ValueError):
            distance = 1.0
        semantic_score = max(0.0, min(1.0, 1.0 - distance / 2.0))
        text = str(documents[index] or "")
        lexical = keyword_score(query, text)
        query_terms = set(tokenize(query))
        content_terms = set(tokenize(text))
        content_keyword = (
            len(query_terms.intersection(content_terms)) / len(query_terms)
            if query_terms else 0.0
        )
        candidates.append({
            "id": chunk_id,
            "content": text,
            "metadata": metadata,
            "score": semantic_score,
            "base_relevance_score": semantic_score,
            "semantic_score": semantic_score,
            "lexical_score": lexical,
            "content_keyword_score": content_keyword,
            "preferred": False,
            "ranking_boost": 0.0,
        })
    return candidates


def merge_semantic_results(*result_sets: dict) -> dict:
    merged = {
        "ids": [],
        "documents": [],
        "metadatas": [],
        "distances": [],
    }
    seen_ids = set()

    for result in result_sets:
        if not result:
            continue
        rows = {}
        for key in merged:
            values = result.get(key, [])
            if values and isinstance(values[0], list):
                values = values[0]
            rows[key] = values or []

        for index, chunk_id in enumerate(rows["ids"]):
            if chunk_id in seen_ids:
                continue
            seen_ids.add(chunk_id)
            merged["ids"].append(chunk_id)
            for key in ("documents", "metadatas", "distances"):
                values = rows[key]
                merged[key].append(values[index] if index < len(values) else None)

    return {key: [values] for key, values in merged.items()}


def rerank_candidates(
    query: str,
    candidates: list[dict],
) -> list[dict]:
    if not candidates:
        return []
    started_at = time.perf_counter()
    try:
        scores = get_reranker().predict(
            [(query, item.get("content", "")) for item in candidates],
            batch_size=32,
            show_progress_bar=False,
        )
        raw_scores = [float(score) for score in scores]
        scores_are_probabilities = all(
            0.0 <= score <= 1.0
            for score in raw_scores
        )

        for index, raw_score in enumerate(raw_scores):
            candidates[index]["rerank_score"] = raw_score
            candidates[index]["normalized_rerank_score"] = (
                raw_score
                if scores_are_probabilities
                else 1.0 / (1.0 + math.exp(-max(-60.0, min(60.0, raw_score))))
            )
    except Exception as error:
        print(f"Reranker warning: {error}")
    finally:
        logger.info(
            "RAG reranking completed: candidates=%d elapsed_seconds=%.3f",
            len(candidates),
            time.perf_counter() - started_at,
        )
    return sorted(
        candidates,
        key=lambda item: (
            item.get("normalized_rerank_score", item.get("semantic_score", 0.0)),
            item.get("semantic_score", 0.0),
        ),
        reverse=True,
    )


def select_rerank_candidates(
    candidates: list[dict],
    per_source_limit: int = RERANK_CANDIDATES_PER_SOURCE,
) -> list[dict]:
    """Keep strong semantic candidates from every source before cross-encoding."""
    if not candidates:
        return []

    started_at = time.perf_counter()
    deduplicated = deduplicate_candidates(candidates)
    grouped = group_by_source(deduplicated)
    selected = []
    for source_candidates in grouped.values():
        ranked = sorted(
            source_candidates,
            key=lambda candidate: (
                float(candidate.get("semantic_score", 0.0) or 0.0),
                float(candidate.get("lexical_score", 0.0) or 0.0),
            ),
            reverse=True,
        )
        selected.extend(ranked[:per_source_limit])
    logger.info(
        "RAG rerank candidate selection: input_chunks=%d deduplicated_chunks=%d "
        "selected_chunks=%d source_count=%d elapsed_seconds=%.3f",
        len(candidates),
        len(deduplicated),
        len(selected),
        len(grouped),
        time.perf_counter() - started_at,
    )
    return selected


def select_definition_candidates(
    candidates: list[dict],
    topic: str,
    limit: int | None = None,
) -> list[dict]:
    topic_terms = set(tokenize(topic))
    for candidate in candidates:
        text_terms = set(tokenize(candidate.get("content", "")))
        evidence = len(topic_terms.intersection(text_terms)) / max(1, len(topic_terms))
        candidate["definition_evidence_score"] = evidence
    candidates.sort(
        key=lambda item: (
            0.65 * float(item.get("semantic_score", 0.0))
            + 0.35 * float(item.get("definition_evidence_score", 0.0))
        ),
        reverse=True,
    )
    return candidates if limit is None else candidates[:limit]


# ============================================================
# SOURCE GROUPING
# ============================================================

def group_by_source(
    candidates: list[dict],
) -> dict[str, list[dict]]:
    groups = {}

    for candidate in candidates:
        metadata = candidate.get(
            "metadata",
            {},
        )

        # Use a normalized source key so minor metadata differences
        # (e.g. filename vs source, extension differences) don't cause
        # the same source to be represented multiple times.
        source_key = get_normalized_source_key(
            metadata,
            candidate.get("id", ""),
        )

        if not source_key:
            source_key = "__unknown_source__"

        groups.setdefault(source_key, []).append(candidate)

    return groups


def get_candidate_relevance(
    candidate: dict,
) -> float:
    value = candidate.get("final_relevance_score")
    if value is None:
        value = calculate_final_relevance(candidate)
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


# ============================================================
# FINAL RELEVANCE SCORE
# ============================================================

def calculate_final_relevance(
    candidate: dict,
) -> float:
    """
    Calculate a practical final relevance score after
    semantic retrieval and cross-encoder reranking.

    This is intentionally independent of any specific topic
    such as LLM, Python, RAG, etc.

    Components:
        semantic       -> vector similarity
        reranker       -> cross encoder relevance
        lexical        -> query/text overlap
        content match  -> meaningful query term overlap
        definition     -> definition evidence when available
    """

    semantic = float(
        candidate.get(
            "semantic_score",
            candidate.get(
                "base_relevance_score",
                0.0,
            ),
        )
        or 0.0
    )

    rerank = float(
        candidate.get(
            "normalized_rerank_score",
            0.0,
        )
        or 0.0
    )

    lexical = float(
        candidate.get(
            "lexical_score",
            0.0,
        )
        or 0.0
    )

    content_keyword = float(
        candidate.get(
            "content_keyword_score",
            lexical,
        )
        or 0.0
    )

    definition_evidence = float(
        candidate.get(
            "definition_evidence_score",
            0.0,
        )
        or 0.0
    )

    # Clamp every component.
    semantic = max(
        0.0,
        min(
            1.0,
            semantic,
        ),
    )

    rerank = max(
        0.0,
        min(
            1.0,
            rerank,
        ),
    )

    lexical = max(
        0.0,
        min(
            1.0,
            lexical,
        ),
    )

    content_keyword = max(
        0.0,
        min(
            1.0,
            content_keyword,
        ),
    )

    definition_evidence = max(
        0.0,
        min(
            1.0,
            definition_evidence,
        ),
    )

    if candidate.get("normalized_rerank_score") is not None:
        final_score = (
            0.55 * semantic
            + 0.30 * rerank
            + 0.10 * content_keyword
            + 0.05 * lexical
        )
    else:
        final_score = (
            0.70 * semantic
            + 0.20 * content_keyword
            + 0.10 * lexical
        )

    # Definition evidence can strengthen an actual
    # definition chunk, but it must not create relevance
    # by itself.
    if definition_evidence > 0:
        final_score = (
            0.85 * final_score
            + 0.15 * definition_evidence
        )

    return max(
        0.0,
        min(
            1.0,
            final_score,
        ),
    )


def apply_final_relevance_score(
    candidates: list[dict],
) -> list[dict]:
    """
    Attach final_relevance_score to every candidate.
    """

    for candidate in candidates:

        final_score = (
            calculate_final_relevance(
                candidate
            )
        )

        candidate[
            "final_relevance_score"
        ] = final_score

        candidate["final_ranking_score"] = final_score

    return candidates


def apply_relevance_threshold(
    candidates: list[dict],
    minimum: float | None = None,
) -> list[dict]:
    """Compatibility wrapper for query-relative source relevance selection."""
    return filter_relevant_sources(candidates)


# ============================================================
# RELEVANT SOURCE FILTER
# ============================================================

def filter_relevant_sources(
    candidates: list[dict],
    minimum: float | None = None,
) -> list[dict]:
    if not candidates:
        return []

    groups = group_by_source(
        candidates
    )

    ranked_groups = sorted(
        (
            (
                max(map(get_candidate_relevance, source_candidates)),
                source_key,
            )
            for source_key, source_candidates in groups.items()
            if source_candidates
        ),
        reverse=True,
    )
    if len(ranked_groups) < 2:
        return candidates

    scores = [score for score, _ in ranked_groups]
    if len(ranked_groups) == 2:
        source_spreads = [
            max(map(get_candidate_relevance, source_candidates))
            - min(map(get_candidate_relevance, source_candidates))
            for source_candidates in groups.values()
            if len(source_candidates) > 1
        ]
        if len(source_spreads) != len(ranked_groups):
            return candidates
        typical_source_spread = sorted(source_spreads)[
            len(source_spreads) // 2
        ]
        if scores[0] - scores[1] <= typical_source_spread * 2.0:
            return candidates
        qualifying_source_keys = {ranked_groups[0][1]}
        return [
            candidate
            for candidate in candidates
            if get_normalized_source_key(
                candidate.get("metadata", {}),
                candidate.get("id", ""),
            ) in qualifying_source_keys
        ]


    gaps = [
        scores[index] - scores[index + 1]
        for index in range(len(scores) - 1)
    ]
    largest_gap_index = max(
        range(len(gaps)),
        key=gaps.__getitem__,
    )
    largest_gap = gaps[largest_gap_index]
    remaining_gaps = [
        gap
        for index, gap in enumerate(gaps)
        if index != largest_gap_index
    ]
    typical_gap = sorted(remaining_gaps)[
        len(remaining_gaps) // 2
    ] if remaining_gaps else 0.0
    distribution_gap = (
        (scores[0] - scores[-1]) / len(scores)
    )

    # Keep the full evidence set unless source scores show a
    # distinct lower-relevance group for this query.
    if largest_gap <= max(
        typical_gap * 2.0,
        distribution_gap * 2.0,
    ):
        return candidates

    qualifying_source_keys = {
        source_key
        for _, source_key in ranked_groups[:largest_gap_index + 1]
    }
    return [
        candidate
        for candidate in candidates
        if get_normalized_source_key(
            candidate.get("metadata", {}),
            candidate.get("id", ""),
        ) in qualifying_source_keys
    ]


# ============================================================
# SOURCE DIVERSIFICATION
# ============================================================

def diversify_sources(
    candidates: list[dict],
    limit: int | None = 12,
    max_chunks_per_source: int | None = 3,
) -> list[dict]:
    """
    Select multiple relevant sources instead of allowing
    one source to dominate the final context.

    First pass:
        Best chunk from every relevant source.

    Second pass:
        Additional chunks from those sources.

    This is important for questions such as:

        "Compare Anis and Safeek resumes"

    because both sources can survive into the final context.
    """

    if not candidates:
        return []

    groups = group_by_source(
        candidates
    )

    ranked_groups = []

    for (
        source_key,
        source_candidates,
    ) in groups.items():

        if not source_candidates:
            continue

        source_candidates.sort(
            key=get_candidate_relevance,
            reverse=True,
        )

        best = source_candidates[
            0
        ]

        ranked_groups.append(
            (
                get_candidate_relevance(
                    best
                ),
                source_key,
                source_candidates,
            )
        )

    ranked_groups.sort(
        key=lambda item: item[0],
        reverse=True,
    )

    selected = []

    selected_ids = set()

    # --------------------------------------------------------
    # PASS 1
    # One strongest chunk from each source.
    # --------------------------------------------------------

    for (
        _score,
        _source_key,
        source_candidates,
    ) in ranked_groups:

        if limit is not None and len(selected) >= limit:
            break

        best = source_candidates[
            0
        ]

        candidate_id = best.get(
            "id"
        )

        if candidate_id in selected_ids:
            continue

        selected.append(
            best
        )

        if candidate_id:
            selected_ids.add(
                candidate_id
            )

    # --------------------------------------------------------
    # PASS 2
    # Add more chunks from each source, up to the configured
    # per-source maximum.
    # --------------------------------------------------------

    source_chunk_limit = max(
        (len(source_candidates) for _, _, source_candidates in ranked_groups),
        default=1,
    )
    if max_chunks_per_source is not None:
        source_chunk_limit = min(
            source_chunk_limit,
            max_chunks_per_source,
        )

    for chunk_index in range(1, source_chunk_limit):

        if limit is not None and len(selected) >= limit:
            break

        for (
            _score,
            _source_key,
            source_candidates,
        ) in ranked_groups:

            if limit is not None and len(selected) >= limit:
                break

            if chunk_index >= len(
                source_candidates
            ):
                continue

            candidate = source_candidates[
                chunk_index
            ]

            candidate_id = candidate.get(
                "id"
            )

            if candidate_id in selected_ids:
                continue

            selected.append(
                candidate
            )

            if candidate_id:
                selected_ids.add(
                    candidate_id
                )

    return selected if limit is None else selected[:limit]


# ============================================================
# FINAL SORT
# ============================================================

def sort_final_candidates(
    candidates: list[dict],
) -> list[dict]:
    if not candidates:
        return []

    return sorted(
        candidates,
        key=lambda candidate: (
            get_candidate_relevance(candidate),
            bool(candidate.get("preferred", False)),
            float(candidate.get("semantic_score", 0.0) or 0.0),
        ),
        reverse=True,
    )


# ============================================================
# PREFERRED SOURCE BOOST
# ============================================================

def apply_preferred_source_boost(
    candidates: list[dict],
    preferred_sources,
    boost: float = 0.02,
) -> list[dict]:

    if not candidates or not preferred_sources:
        return candidates

    for candidate in candidates:

        metadata = candidate.get(
            "metadata",
            {},
        )

        if source_matches_preference(
            metadata,
            preferred_sources,
        ):
            candidate["preferred"] = True
            candidate["ranking_boost"] = boost

    return candidates


# ============================================================
# DUPLICATE REMOVAL
# ============================================================

def deduplicate_candidates(
    candidates: list[dict],
) -> list[dict]:

    if not candidates:
        return []

    seen_ids = set()
    seen_content = set()

    result = []

    for candidate in candidates:

        candidate_id = candidate.get(
            "id"
        )

        content = re.sub(
            r"\s+",
            " ",
            str(
                candidate.get(
                    "content",
                    "",
                )
            ),
        ).strip().casefold()

        if candidate_id:
            if candidate_id in seen_ids:
                continue

            seen_ids.add(
                candidate_id
            )

        if content:
            content_key = (
                            get_normalized_source_key(
                    candidate.get(
                        "metadata",
                        {},
                    ),
                    "",
                ),
                content,
            )

            if content_key in seen_content:
                continue

            seen_content.add(
                content_key
            )

        result.append(
            candidate
        )

    return result


# ============================================================
# CLEANUP FINAL CANDIDATES
# ============================================================

def cleanup_candidates(
    candidates: list[dict],
    limit: int = 12,
) -> list[dict]:

    if not candidates:
        return []

    candidates = deduplicate_candidates(
        candidates
    )

    candidates = sort_final_candidates(
        candidates
    )

    return candidates if limit is None else candidates[:limit]


# ============================================================
# DOCUMENT DISCOVERY
# ============================================================

def discover_all_documents(
    user_id: str,
    limit: int | None = None,
) -> list[dict]:

    try:
        documents = get_user_file_metadata(
            user_id
        )
    except Exception as error:
        print(
            f"Document discovery error: {error}"
        )
        return []

    results = []
    seen = set()

    for metadata in documents:

        filename = metadata.get(
            "filename"
        )

        if not filename:
            continue

        source_key = get_source_key(
            metadata,
            filename,
        )

        normalized = get_normalized_source_key(
            metadata,
            filename,
        )

        if normalized in seen:
            continue

        seen.add(
            normalized
        )

        results.append(
            {
                "id": str(
                    metadata.get(
                        "source_id"
                    )
                    or filename
                ),
                "content": (
                    "Document: "
                    + str(
                        filename
                    )
                ),
                "metadata": metadata,
                "score": 1.0,
                "base_relevance_score": 1.0,
                "semantic_score": 1.0,
                "lexical_score": 1.0,
                "document_discovery": True,
                "document_type": get_document_type(
                    metadata
                ),
                "source": get_source_display_name(
                    metadata,
                    source_key,
                ),
                "filename": filename,
            }
        )

        if limit is not None and len(results) >= limit:
            break

    return results


def hybrid_retrieve(
    user_id: str,
    query: str,
    limit: int | None = 8,
    file_type: str | None = None,
    preferred_sources: list | None = None,
    attached_sources: list[dict] | None = None,
    retrieval_metadata: dict | None = None,
) -> list[dict]:
    if retrieval_metadata is not None:
        retrieval_metadata["searched_files"] = []
    if not user_id or not query.strip():
        return []

    if is_resume_discovery_query(query):
        return discover_resumes(user_id=user_id, limit=limit)

    if is_all_sources_query(query):
        return discover_all_documents(user_id=user_id, limit=limit)

    definition_topic = extract_definition_topic(query)
    requested_file_type = file_type or detect_requested_file_type(query)
    candidate_limit = None
    resume_query = is_resume_content_query(query)
    resume_metadata = []
    explicit_document_reference = bool(
        re.search(r"\.(?:pdf|docx?|txt|csv|xlsx|pptx)\b", query, re.IGNORECASE)
    )
    requested_documents = []
    if explicit_document_reference:
        # Match named files against this user's document catalog before any
        # vector or lexical search. A filename mention is a source boundary.
        requested_documents = [
            document
            for document in get_user_file_metadata(user_id)
            if document.get("filename")
            and str(document["filename"]).casefold() in query.casefold()
        ]
        if not requested_documents:
            logger.info(
                "RAG source restriction matched no user documents; retrieval skipped."
            )
            return []
    strict_sources = (
        list(attached_sources or [])
        or requested_documents
        or list(preferred_sources or [])
    )
    if attached_sources and requested_documents:
        strict_sources = [
            item
            for item in requested_documents
            if any(
                (
                    item.get("source_id")
                    and item.get("source_id") == attached.get("source_id")
                )
                or (
                    item.get("filename")
                    and attached.get("filename")
                    and str(item["filename"]).casefold()
                    == str(attached["filename"]).casefold()
                )
                for attached in attached_sources
            )
        ]
        if not strict_sources:
            logger.info(
                "RAG source restriction has no overlap between named and attached documents."
            )
            return []

    try:
        source_filters = [
            source_metadata_filter(source)
            for source in strict_sources
            if isinstance(source, dict)
        ]
        source_filters = [item for item in source_filters if item]
        if strict_sources and not source_filters:
            logger.info("RAG source restriction lacks an indexed source reference.")
            return []
        if not source_filters and resume_query:
            resume_metadata = discover_resumes(user_id)
            if not resume_metadata:
                return []
            named_resumes = detect_named_sources(
                query,
                {"metadatas": [resume_metadata]},
            )
            if named_resumes:
                resume_metadata = [
                    metadata
                    for metadata in resume_metadata
                    if any(
                        source_name_matches_query(
                            name,
                            str(metadata.get("filename", "")),
                        )
                        for name in named_resumes
                    )
                ]
            source_filters = [
                source_metadata_filter(metadata)
                for metadata in resume_metadata
            ]
            source_filters = [item for item in source_filters if item]
        elif not source_filters and preferred_sources:
            source_filters = [
                source_metadata_filter(source)
                for source in preferred_sources
                if isinstance(source, dict)
            ]
            source_filters = [item for item in source_filters if item]

        semantic_started_at = time.perf_counter()
        if source_filters:
            raw_results = search_semantic_by_sources(
                user_id=user_id,
                query=query,
                source_filters=source_filters,
                limit=candidate_limit,
            )
        else:
            raw_results = search_semantic(
                user_id=user_id,
                query=query,
                limit=candidate_limit,
                file_type=requested_file_type,
            )
        logger.info(
            "RAG semantic retrieval completed: restricted=%s sources=%d chunks=%d elapsed_seconds=%.3f",
            bool(strict_sources or source_filters),
            len(source_filters),
            len((raw_results or {}).get("ids", [[]])[0] if (raw_results or {}).get("ids") and isinstance((raw_results or {}).get("ids")[0], list) else (raw_results or {}).get("ids", [])),
            time.perf_counter() - semantic_started_at,
        )

        # Attachments are a hard, owner-validated allowlist (already checked
        # by the chat route). Never merge them with unrestricted corpus hits.
    except Exception as error:
        raise RuntimeError(
            f"Semantic retrieval failed for the active Chroma index: {error}"
        ) from error

    try:
        lexical_started_at = time.perf_counter()
        if strict_sources:
            lexical_chunks = get_all_user_chunks(
                user_id=user_id,
                file_type=requested_file_type,
                source_filters=source_filters,
            )
        else:
            lexical_chunks = get_all_user_chunks(
                user_id=user_id,
                file_type=requested_file_type,
            )
        logger.info(
            "RAG lexical index loaded: restricted=%s chunks=%d elapsed_seconds=%.3f",
            bool(strict_sources),
            len(lexical_chunks.get("ids", []) or []),
            time.perf_counter() - lexical_started_at,
        )
    except Exception as error:
        raise RuntimeError(
            f"Lexical retrieval failed for the active Chroma index: {error}"
        ) from error
    source_catalog = dict(raw_results or {})
    existing_metadata = source_catalog.get("metadatas", []) or []
    if existing_metadata and isinstance(existing_metadata[0], list):
        existing_metadata = [item for group in existing_metadata for item in group]
    source_catalog["metadatas"] = [
        *existing_metadata,
        *(lexical_chunks.get("metadatas", []) or []),
    ]
    source_filter = (
        {"type": "sources", "sources": strict_sources}
        if strict_sources
        else detect_source_filter(query, source_catalog)
    )
    semantic_candidate_started_at = time.perf_counter()
    semantic_candidates = build_candidates(
        query=query,
        raw_results=raw_results,
        source_filter=source_filter,
    )
    logger.info(
        "RAG semantic candidates prepared: candidates=%d elapsed_seconds=%.3f",
        len(semantic_candidates),
        time.perf_counter() - semantic_candidate_started_at,
    )
    bm25_started_at = time.perf_counter()
    lexical_candidates = bm25_candidates(
        query=query,
        chunks=lexical_chunks,
        source_filter=source_filter,
    )
    logger.info(
        "RAG BM25 scoring completed: indexed_chunks=%d candidates=%d elapsed_seconds=%.3f",
        len(lexical_chunks.get("ids", []) or []),
        len(lexical_candidates),
        time.perf_counter() - bm25_started_at,
    )
    candidates = merge_retrieval_candidates(
        semantic_candidates,
        lexical_candidates,
    )
    semantic_metadatas = raw_results.get("metadatas", []) if raw_results else []
    if semantic_metadatas and isinstance(semantic_metadatas[0], list):
        semantic_metadatas = [
            metadata
            for group in semantic_metadatas
            for metadata in group
        ]
    if strict_sources:
        semantic_metadatas = [
            metadata
            for metadata in semantic_metadatas
            if isinstance(metadata, dict)
            and source_matches_filter(metadata, source_filter)
        ]
    lexical_metadatas = [
        metadata
        for metadata in (lexical_chunks.get("metadatas", []) or [])
        if isinstance(metadata, dict)
        and source_matches_filter(metadata, source_filter)
    ]
    if retrieval_metadata is not None:
        retrieval_metadata["searched_files"] = _searched_sources(
            semantic_metadatas,
            lexical_metadatas,
        )
    if not candidates:
        return []

    if resume_query:
        resume_source_ids = {
            str(metadata.get("source_id"))
            for metadata in resume_metadata
            if metadata.get("source_id")
        }
        resume_filenames = {
            str(metadata.get("filename")).casefold()
            for metadata in resume_metadata
            if metadata.get("filename")
        }
        candidates = [
            candidate
            for candidate in candidates
            if str(
                candidate.get("metadata", {}).get("source_type", "")
            ).lower() != "url"
            and (
                str(
                    candidate.get("metadata", {}).get("source_id", "")
                ) in resume_source_ids
                or str(
                    candidate.get("metadata", {}).get("filename", "")
                ).casefold() in resume_filenames
            )
        ]
    else:
        candidates = filter_resume_query_candidates(
            query=query,
            candidates=candidates,
        )

    if not candidates:
        return []

    # --------------------------------------------------------
    # DEFINITION MODE
    # --------------------------------------------------------
    #
    # For:
    #   What is LLM?
    #   Define RAG
    #   What does LangChain mean?
    #
    # We need actual explanatory chunks, not just chunks
    # which happen to mention the word.
    # --------------------------------------------------------

    if definition_topic:

        candidates = select_definition_candidates(
            candidates=candidates,
            topic=definition_topic,
            limit=None,
        )

        if not candidates:
            return []

    # --------------------------------------------------------
    # SECTION / CHAPTER EXPANSION
    # --------------------------------------------------------

    requested_section = detect_requested_section(
        query
    )

    if requested_section:

        candidates = expand_parent_section(
            user_id=user_id,
            requested_section=requested_section,
            candidates=candidates,
            source_filter=source_filter,
            limit=(
                max(limit * 3, 12)
                if limit is not None
                else None
            ),
        )

    if not candidates:
        return []

    # --------------------------------------------------------
    # PREFERRED SOURCE BOOST
    # --------------------------------------------------------

    candidates = apply_preferred_sources(
        candidates=candidates,
        preferred_sources=[
            *(preferred_sources or []),
            *(attached_sources or []),
        ],
    )

    # Keep semantic leaders from each allowed source before cross-encoding.
    # Named and attached source boundaries are applied before this point.
    candidates = select_rerank_candidates(candidates)

    candidates = rerank_candidates(
        query=query,
        candidates=candidates,
    )

    if not candidates:
        return []

    # --------------------------------------------------------
    # DEFINITION FINAL SCORING
    # --------------------------------------------------------

    if definition_topic:

        for candidate in candidates:

            evidence = definition_evidence_score(
                definition_topic,
                str(
                    candidate.get(
                        "content",
                        "",
                    )
                ),
            )

            candidate[
                "definition_evidence_score"
            ] = evidence

            normalized_rerank = float(
                candidate.get(
                    "normalized_rerank_score",
                    0.0,
                )
                or 0.0
            )

            semantic_score = float(
                candidate.get(
                    "semantic_score",
                    candidate.get(
                        "base_relevance_score",
                        0.0,
                    ),
                )
                or 0.0
            )

            # Definition queries give some extra weight to
            # actual definition evidence.
            candidate[
                "definition_relevance_score"
            ] = (
                0.45 * semantic_score
                + 0.25 * normalized_rerank
                + 0.30 * evidence
            )

    # --------------------------------------------------------
    # FINAL RELEVANCE SCORE
    # --------------------------------------------------------

    candidates = apply_final_relevance_score(
        candidates
    )

    # Use the query's source-score distribution to exclude a
    # distinct lower-relevance group without a fixed score cutoff.
    if not resume_query:
        candidates = filter_relevant_sources(
            candidates=candidates,
        )

    if not candidates:
        return []

    # --------------------------------------------------------
    # PREFERRED SOURCE BOOST
    # --------------------------------------------------------

    candidates = apply_preferred_source_boost(
        candidates=candidates,
        preferred_sources=preferred_sources,
    )

    candidates = apply_preferred_sources(
        candidates=candidates,
        preferred_sources=preferred_sources,
    )

    # --------------------------------------------------------
    # FINAL SCORE AGAIN
    # --------------------------------------------------------
    #
    # Preferred-source boost can slightly change ranking.
    # Recalculate final ranking but DO NOT allow the boost to
    # manufacture relevance from an irrelevant document.
    # --------------------------------------------------------

    for candidate in candidates:

        base_final_score = float(
            candidate.get(
                "final_relevance_score",
                0.0,
            )
            or 0.0
        )

        ranking_boost = float(
            candidate.get(
                "ranking_boost",
                0.0,
            )
            or 0.0
        )

        candidate["final_ranking_score"] = base_final_score

    # --------------------------------------------------------
    # MULTI-SOURCE DIVERSIFICATION
    # --------------------------------------------------------
    #
    # Prevent one document from taking every slot.
    #
    # Example:
    #
    # Resume A -> 3 chunks
    # Resume B -> 3 chunks
    # Resume C -> 2 chunks
    #
    # instead of:
    #
    # Resume A -> 8 chunks
    # --------------------------------------------------------

    candidates = diversify_sources(
        candidates=candidates,
        limit=limit,
        max_chunks_per_source=None,
    )

    if not candidates:
        return []

    # --------------------------------------------------------
    # FINAL SORT
    # --------------------------------------------------------

    candidates = sort_final_candidates(
        candidates
    )

    # --------------------------------------------------------
    # FINAL CLEANUP
    # --------------------------------------------------------

    candidates = cleanup_candidates(
        candidates=candidates,
        limit=limit,
    )

    return candidates if limit is None else candidates[:limit]


# ============================================================
# SIMPLE RETRIEVAL WRAPPER
# ============================================================

def retrieve_documents(
    user_id: str,
    query: str,
    limit: int = 8,
    file_type: str | None = None,
    preferred_sources: list | None = None,
) -> list[dict]:
    """
    Public retrieval helper.

    All normal document-grounded questions should come
    through hybrid_retrieve().
    """

    return hybrid_retrieve(
        user_id=user_id,
        query=query,
        limit=limit,
        file_type=file_type,
        preferred_sources=preferred_sources,
    )


# ============================================================
# SEMANTIC RETRIEVAL ALIAS
# ============================================================

def semantic_retrieve(
    user_id: str,
    query: str,
    limit: int = 8,
    file_type: str | None = None,
) -> list[dict]:

    return hybrid_retrieve(
        user_id=user_id,
        query=query,
        limit=limit,
        file_type=file_type,
    )


# ============================================================
# SOURCE-SPECIFIC RETRIEVAL
# ============================================================

def retrieve_from_sources(
    user_id: str,
    query: str,
    source_filters: list[dict],
    limit: int = 8,
) -> list[dict]:

    if not source_filters:
        return []

    try:
        raw_results = search_semantic_by_sources(
            user_id=user_id,
            query=query,
            source_filters=source_filters,
            limit=None,
        )
    except Exception as error:
        print(
            f"Source-specific retrieval error: {error}"
        )
        return []

    if not raw_results:
        return []

    candidates = build_candidates(
        query=query,
        raw_results=raw_results,
        source_filter=None,
    )

    if not candidates:
        return []

    candidates = select_rerank_candidates(candidates)
    candidates = rerank_candidates(
        query=query,
        candidates=candidates,
    )

    if not candidates:
        return []

    candidates = apply_final_relevance_score(
        candidates
    )

    candidates = apply_relevance_threshold(
        candidates=candidates,
    )

    if not candidates:
        return []

    candidates = filter_relevant_sources(
        candidates=candidates,
    )

    if not candidates:
        return []

    candidates = diversify_sources(
        candidates=candidates,
        limit=limit,
        max_chunks_per_source=None,
    )

    candidates = sort_final_candidates(
        candidates
    )

    return cleanup_candidates(
        candidates=candidates,
        limit=limit,
    )


# ============================================================
# SINGLE SOURCE RETRIEVAL
# ============================================================

def retrieve_from_source(
    user_id: str,
    query: str,
    source_name: str,
    limit: int = 8,
) -> list[dict]:

    if not source_name:
        return []

    source_filter = {
        "type": "filename",
        "filename": source_name,
    }

    try:
        raw_results = search_semantic(
            user_id=user_id,
            query=query,
            limit=None,
        )
    except Exception as error:
        print(
            f"Single source retrieval error: {error}"
        )
        return []

    if not raw_results:
        return []

    candidates = build_candidates(
        query=query,
        raw_results=raw_results,
        source_filter=source_filter,
    )

    if not candidates:
        return []

    candidates = select_rerank_candidates(candidates)
    candidates = rerank_candidates(
        query=query,
        candidates=candidates,
    )

    candidates = apply_final_relevance_score(
        candidates
    )

    candidates = apply_relevance_threshold(
        candidates=candidates,
    )

    if not candidates:
        return []

    candidates = sort_final_candidates(
        candidates
    )

    return cleanup_candidates(
        candidates=candidates,
        limit=limit,
    )


# ============================================================
# RESUME-ONLY RETRIEVAL
# ============================================================

def retrieve_resume_content(
    user_id: str,
    query: str,
    limit: int = 8,
) -> list[dict]:

    try:
        documents = get_user_file_metadata(
            user_id
        )
    except Exception as error:
        print(
            f"Resume metadata error: {error}"
        )
        return []

    resume_documents = [
        metadata
        for metadata in documents
        if is_resume_metadata(
            metadata
        )
    ]

    if not resume_documents:
        return []

    source_filters = []

    for metadata in resume_documents:

        source_filter = source_metadata_filter(
            metadata
        )

        if source_filter:
            source_filters.append(
                source_filter
            )

    if not source_filters:
        return []

    return retrieve_from_sources(
        user_id=user_id,
        query=query,
        source_filters=source_filters,
        limit=limit,
    )


# ============================================================
# DOCUMENT TYPE RETRIEVAL
# ============================================================

def retrieve_by_document_type(
    user_id: str,
    query: str,
    document_type: str,
    limit: int = 8,
) -> list[dict]:

    if not document_type:
        return []

    try:
        documents = get_user_file_metadata(
            user_id
        )
    except Exception as error:
        print(
            f"Document type metadata error: {error}"
        )
        return []

    matching_documents = [
        metadata
        for metadata in documents
        if get_document_type(
            metadata
        ) == str(
            document_type
        ).lower().strip()
    ]

    if not matching_documents:
        return []

    source_filters = []

    for metadata in matching_documents:

        source_filter = source_metadata_filter(
            metadata
        )

        if source_filter:
            source_filters.append(
                source_filter
            )

    return retrieve_from_sources(
        user_id=user_id,
        query=query,
        source_filters=source_filters,
        limit=limit,
    )


# ============================================================
# DOCUMENT DISCOVERY HELPERS
# ============================================================

def list_user_documents(
    user_id: str,
    limit: int | None = None,
) -> list[dict]:

    return discover_all_documents(
        user_id=user_id,
        limit=limit,
    )


def list_user_resumes(
    user_id: str,
    limit: int = 20,
) -> list[dict]:

    return discover_resumes(
        user_id=user_id,
        limit=limit,
    )


# ============================================================
# RELEVANCE DEBUGGING
# ============================================================

def explain_candidate_score(
    candidate: dict,
) -> dict:

    return {
        "semantic_score": round(
            float(
                candidate.get(
                    "semantic_score",
                    0.0,
                )
                or 0.0
            ),
            4,
        ),
        "lexical_score": round(
            float(
                candidate.get(
                    "lexical_score",
                    0.0,
                )
                or 0.0
            ),
            4,
        ),
        "content_keyword_score": round(
            float(
                candidate.get(
                    "content_keyword_score",
                    0.0,
                )
                or 0.0
            ),
            4,
        ),
        "rerank_score": round(
            float(
                candidate.get(
                    "rerank_score",
                    0.0,
                )
                or 0.0
            ),
            4,
        ),
        "normalized_rerank_score": round(
            float(
                candidate.get(
                    "normalized_rerank_score",
                    0.0,
                )
                or 0.0
            ),
            4,
        ),
        "definition_evidence_score": round(
            float(
                candidate.get(
                    "definition_evidence_score",
                    0.0,
                )
                or 0.0
            ),
            4,
        ),
        "final_relevance_score": round(
            float(
                candidate.get(
                    "final_relevance_score",
                    0.0,
                )
                or 0.0
            ),
            4,
        ),
        "final_ranking_score": round(
            float(
                candidate.get(
                    "final_ranking_score",
                    0.0,
                )
                or 0.0
            ),
            4,
        ),
        "preferred": bool(
            candidate.get(
                "preferred",
                False,
            )
        ),
    }


# ============================================================
# SEARCH DOCUMENTS
# ============================================================

def search_documents(
    user_id: str,
    query: str,
    limit: int = 8,
    file_type: str | None = None,
    preferred_sources: list | None = None,
) -> list[dict]:

    return hybrid_retrieve(
        user_id=user_id,
        query=query,
        limit=limit,
        file_type=file_type,
        preferred_sources=preferred_sources,
    )


# ============================================================
# SOURCE SUMMARY
# ============================================================

def build_source_summary(
    candidates: list[dict],
) -> list[dict]:

    if not candidates:
        return []

    groups = group_by_source(
        candidates
    )

    sources = []

    for (
        source_key,
        source_candidates,
    ) in groups.items():

        if not source_candidates:
            continue

        # Use FINAL relevance instead of the old raw
        # semantic/base score.
        best = max(
            source_candidates,
            key=get_candidate_relevance,
        )

        metadata = best.get(
            "metadata",
            {},
        )

        final_score = float(
            best.get(
                "final_relevance_score",
                best.get(
                    "final_ranking_score",
                    best.get(
                        "base_relevance_score",
                        best.get(
                            "score",
                            0.0,
                        ),
                    ),
                ),
            )
            or 0.0
        )

        sources.append(
            {
                "source": get_source_display_name(
                    metadata,
                    source_key,
                ),
                "filename": metadata.get(
                    "filename",
                    get_source_display_name(
                        metadata,
                        source_key,
                    ),
                ),
                "document_type": get_document_type(
                    metadata
                ),
                "relevance_score": round(
                    max(
                        0.0,
                        min(
                            1.0,
                            final_score,
                        ),
                    ),
                    4,
                ),
                "chunk_count": len(
                    source_candidates
                ),
            }
        )

    sources.sort(
        key=lambda item: item.get(
            "relevance_score",
            0.0,
        ),
        reverse=True,
    )

    return sources


# ============================================================
# RETRIEVED SOURCE NAMES
# ============================================================

def get_retrieved_source_names(
    candidates: list[dict],
) -> list[str]:

    if not candidates:
        return []

    names = []
    seen = set()

    for candidate in candidates:

        # Safety check:
        # Do not expose weak/irrelevant sources here.
        final_score = float(
            candidate.get(
                "final_relevance_score",
                candidate.get(
                    "base_relevance_score",
                    0.0,
                ),
            )
            or 0.0
        )

        metadata = candidate.get(
            "metadata",
            {},
        )

        source = get_source_display_name(
            metadata,
            candidate.get(
                "id",
                "",
            ),
        )

        normalized = normalize_source_name(
            source
        )

        if not normalized:
            continue

        if normalized in seen:
            continue

        seen.add(
            normalized
        )

        names.append(
            source
        )

    return names


# ============================================================
# RESUME SOURCE NAMES
# ============================================================

def get_resume_source_names(
    user_id: str,
) -> list[str]:

    resumes = discover_resumes(
        user_id=user_id,
    )

    names = []
    seen = set()

    for resume in resumes:

        source = (
            resume.get(
                "filename"
            )
            or resume.get(
                "source"
            )
        )

        if not source:
            continue

        normalized = normalize_source_name(
            source
        )

        if not normalized:
            continue

        if normalized in seen:
            continue

        seen.add(
            normalized
        )

        names.append(
            source
        )

    return names


# ============================================================
# RETRIEVAL DEBUG INFORMATION
# ============================================================

def get_retrieval_debug_info(
    query: str,
    candidates: list[dict],
) -> dict:

    if not candidates:
        return {
            "query": query,
            "result_count": 0,
            "sources": [],
            "document_types": [],
            "relevance_selection": "query-relative source score distribution",
        }

    sources = []
    document_types = []

    seen_sources = set()
    seen_types = set()

    for candidate in candidates:

        metadata = candidate.get(
            "metadata",
            {},
        )

        final_score = float(
            candidate.get(
                "final_relevance_score",
                candidate.get(
                    "base_relevance_score",
                    0.0,
                ),
            )
            or 0.0
        )

        source = get_source_display_name(
            metadata,
            candidate.get(
                "id",
                "",
            ),
        )

        document_type = get_document_type(
            metadata
        )

        normalized_source = normalize_source_name(
            source
        )

        if (
            normalized_source
            and normalized_source
            not in seen_sources
        ):
            seen_sources.add(
                normalized_source
            )

            sources.append(
                {
                    "name": source,
                    "relevance_score": round(
                        final_score,
                        4,
                    ),
                }
            )

        if (
            document_type
            and document_type not in seen_types
        ):
            seen_types.add(
                document_type
            )

            document_types.append(
                document_type
            )

    sources.sort(
        key=lambda item: item.get(
            "relevance_score",
            0.0,
        ),
        reverse=True,
    )

    return {
        "query": query,
        "result_count": len(
            candidates
        ),
        "sources": sources,
        "document_types": document_types,
        "relevance_selection": "query-relative source score distribution",
    }


# ============================================================
# SCORE DEBUGGING
# ============================================================

def get_candidate_score_details(
    candidate: dict,
) -> dict:

    return {
        "semantic_score": round(
            float(
                candidate.get(
                    "semantic_score",
                    0.0,
                )
                or 0.0
            ),
            4,
        ),
        "lexical_score": round(
            float(
                candidate.get(
                    "lexical_score",
                    0.0,
                )
                or 0.0
            ),
            4,
        ),
        "content_keyword_score": round(
            float(
                candidate.get(
                    "content_keyword_score",
                    0.0,
                )
                or 0.0
            ),
            4,
        ),
        "rerank_score": round(
            float(
                candidate.get(
                    "rerank_score",
                    0.0,
                )
                or 0.0
            ),
            4,
        ),
        "normalized_rerank_score": round(
            float(
                candidate.get(
                    "normalized_rerank_score",
                    0.0,
                )
                or 0.0
            ),
            4,
        ),
        "definition_evidence_score": round(
            float(
                candidate.get(
                    "definition_evidence_score",
                    0.0,
                )
                or 0.0
            ),
            4,
        ),
        "final_relevance_score": round(
            float(
                candidate.get(
                    "final_relevance_score",
                    0.0,
                )
                or 0.0
            ),
            4,
        ),
        "final_ranking_score": round(
            float(
                candidate.get(
                    "final_ranking_score",
                    0.0,
                )
                or 0.0
            ),
            4,
        ),
        "preferred": bool(
            candidate.get(
                "preferred",
                False,
            )
        ),
    }


# ============================================================
# DEBUG RETRIEVAL
# ============================================================

def debug_retrieve(
    user_id: str,
    query: str,
    limit: int = 8,
) -> list[dict]:

    results = hybrid_retrieve(
        user_id=user_id,
        query=query,
        limit=limit,
    )

    debug_results = []

    for candidate in results:

        debug_results.append(
            {
                "id": candidate.get(
                    "id"
                ),
                "source": candidate.get(
                    "source"
                ),
                "filename": candidate.get(
                    "filename"
                ),
                "document_type": candidate.get(
                    "document_type"
                ),
                "scores": get_candidate_score_details(
                    candidate
                ),
                "content": candidate.get(
                    "content",
                    "",
                ),
            }
        )

    return debug_results


# ============================================================
# PUBLIC API
# ============================================================

__all__ = [
    # Main retrieval
    "hybrid_retrieve",
    "retrieve_documents",
    "search_documents",

    # Definition handling
    "extract_definition_topic",
    "is_definition_query",

    # Resume handling
    "discover_resumes",
    "get_resume_source_names",
    "is_resume_discovery_query",
    "is_resume_content_query",
    "filter_resume_candidates",

    # Document discovery
    "discover_all_documents",
    "list_user_documents",
    "list_user_resumes",

    # Source handling
    "build_source_summary",
    "get_retrieved_source_names",
    "detect_source_filter",
    "detect_requested_file_type",

    # Query modes
    "is_all_sources_query",
    "is_comparison_query",

    # Relevance
    "apply_relevance_threshold",
    "filter_relevant_sources",
    "calculate_final_relevance",
    "apply_final_relevance_score",

    # Debugging
    "get_retrieval_debug_info",
    "get_candidate_score_details",
    "debug_retrieve",
]
