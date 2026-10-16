import logging
import math
import re
import time

from app.database.mongodb import documents_collection
from app.rag.chain import (
    fit_generation_context,
    generate_answer,
)
from app.documents.document_service import list_user_documents
from app.rag.retriever import (
    discover_resumes,
    extract_definition_topic,
    hybrid_retrieve,
    is_all_sources_query,
    is_resume_discovery_query,
    normalize_source_name,
)

logger = logging.getLogger(__name__)

SOURCE_CARD_MIN_RELEVANCE = 0.35


def qualifying_source_card_chunks(results: list[dict]) -> list[dict]:
    """Keep retriever chunks scoring at least 35% on its normalized 0..1 scale."""
    qualifying = []
    for result in results:
        if not isinstance(result, dict):
            continue
        try:
            relevance = float(result.get("final_relevance_score"))
        except (TypeError, ValueError):
            continue
        if math.isfinite(relevance) and SOURCE_CARD_MIN_RELEVANCE <= relevance <= 1.0:
            qualifying.append(result)
    return qualifying


def build_context(
    results: list[dict],
) -> str:

    context_parts = []

    source_numbers = {}
    source_contents = {}

    next_source_number = 1

    for result in results:

        content = result.get("content")
        if not isinstance(content, str) or not content.strip():
            continue

        metadata = result.get(
            "metadata",
            {},
        )

        source_key = (
            metadata.get("source_id")
            or metadata.get("url")
            or metadata.get("source_url")
            or metadata.get("filename")
            or "unknown"
        )
        normalized_content = " ".join(content.split()).casefold()
        previous_contents = source_contents.setdefault(
            source_key,
            [],
        )
        if normalized_content in previous_contents:
            continue

        content_tokens = set(re.findall(r"\w+", normalized_content))
        if len(content_tokens) >= 12 and any(
            len(content_tokens & previous_tokens)
            / len(content_tokens | previous_tokens)
            >= 0.92
            for previous_tokens in previous_contents
            if isinstance(previous_tokens, set)
        ):
            continue
        previous_contents.append(
            content_tokens
            if len(content_tokens) >= 12
            else normalized_content
        )

        if source_key not in source_numbers:

            source_numbers[
                source_key
            ] = next_source_number

            next_source_number += 1

        source_number = source_numbers[
            source_key
        ]

        source_name = (
            metadata.get("filename")
            or metadata.get("title")
            or metadata.get("url")
            or metadata.get("source_url")
            or "Unknown source"
        )

        page = metadata.get(
            "page"
        )

        if page:

            source_label = (
                f"{source_name}, page {page}"
            )

        else:

            source_label = source_name

        section = metadata.get(
            "section"
        )

        section_title = metadata.get(
            "section_title"
        )

        hierarchy_label = ""

        if section:

            hierarchy_label = (
                f"\nSection: {section}"
            )

            if section_title:

                hierarchy_label += (
                    f" - {section_title}"
                )

        context_parts.append(
            f"[Source {source_number}: "
            f"{source_label}]"
            f"{hierarchy_label}\n"
            f"{content.strip()}"
        )

    return "\n\n".join(
        context_parts
    )


def _context_source_number_map(results: list[dict]) -> dict[str, int]:
    """Mirror build_context's first-usable-chunk source numbering."""
    source_numbers = {}
    for result in results:
        content = result.get("content")
        if not isinstance(content, str) or not content.strip():
            continue
        metadata = result.get("metadata", {})
        source_key = (
            metadata.get("source_id")
            or metadata.get("url")
            or metadata.get("source_url")
            or metadata.get("filename")
            or "unknown"
        )
        source_numbers.setdefault(source_key, len(source_numbers) + 1)
    return source_numbers


def _selected_context_sources(context: str) -> dict[int, dict]:
    """Read source, page, and section labels retained in fitted prompt context."""
    selected = {}
    matches = list(
        re.finditer(r"\[Source\s+(\d+):\s*([^\]]+)\]", context, re.IGNORECASE)
    )
    for index, match in enumerate(matches):
        label = match.group(2).strip()
        page_match = re.search(r",\s*page\s+(\d+)\s*$", label, re.IGNORECASE)
        filename = re.sub(r",\s*page\s+\d+\s*$", "", label, flags=re.IGNORECASE).strip()
        body_start = match.end()
        body_end = matches[index + 1].start() if index + 1 < len(matches) else len(context)
        body = context[body_start:body_end]
        section_match = re.search(r"^\s*Section:\s*([^\r\n]+)", body, re.IGNORECASE)
        selected.setdefault(int(match.group(1)), []).append({
            "filename": filename,
            "page": page_match.group(1) if page_match else None,
            "section": section_match.group(1).strip() if section_match else None,
        })
    return selected

def create_citations(
    results: list[dict],
    context: str | None = None,
    user_id: str | None = None,
) -> list[dict]:

    grouped = {}
    source_ids = {
        str(result.get("metadata", {}).get("source_id"))
        for result in results
        if result.get("metadata", {}).get("source_id")
    }
    filenames = {
        str(result.get("metadata", {}).get("filename"))
        for result in results
        if result.get("metadata", {}).get("filename")
        and result.get("metadata", {}).get("source_type") != "url"
    }
    source_urls = {
        str(
            result.get("metadata", {}).get("url")
            or result.get("metadata", {}).get("source_url")
        )
        for result in results
        if result.get("metadata", {}).get("url")
        or result.get("metadata", {}).get("source_url")
    }
    document_ids = {}
    if user_id and (source_ids or filenames or source_urls):
        document_filters = []
        if source_ids:
            document_filters.append(
                {"source_id": {"$in": list(source_ids)}}
            )
        if filenames:
            document_filters.append(
                {"filename": {"$in": list(filenames)}}
            )
        if source_urls:
            document_filters.append(
                {"source_url": {"$in": list(source_urls)}}
            )

        documents = documents_collection.find(
            {
                "user_id": user_id,
                "$or": document_filters,
            },
            {
                "_id": 1,
                "source_id": 1,
                "filename": 1,
                "source_url": 1,
            },
        )
        filename_documents = {}
        url_documents = {}
        for document in documents:
            document_id = str(document["_id"])
            if document.get("source_id"):
                document_ids[str(document["source_id"])] = document_id
            if document.get("filename"):
                filename_documents.setdefault(
                    str(document["filename"]).casefold(),
                    [],
                ).append(document_id)
            if document.get("source_url"):
                url_documents.setdefault(
                    str(document["source_url"]).strip().rstrip("/").casefold(),
                    [],
                ).append(document_id)

        for result in results:
            metadata = result.get("metadata", {})
            url = metadata.get("url") or metadata.get("source_url")
            filename = metadata.get("filename")
            match_ids = (
                url_documents.get(str(url).strip().rstrip("/").casefold(), [])
                if url
                else filename_documents.get(str(filename).casefold(), [])
            )
            if len(match_ids) == 1:
                if filename:
                    document_ids.setdefault(
                        str(filename),
                        match_ids[0],
                    )
                if url:
                    document_ids.setdefault(
                        str(url).strip().rstrip("/").casefold(),
                        match_ids[0],
                    )

    context_sources = _selected_context_sources(context) if context is not None else None
    source_numbers = _context_source_number_map(results)

    for result in results:
        metadata = result.get("metadata", {})
        filename = metadata.get("filename") or metadata.get("title")
        url = metadata.get("url") or metadata.get("source_url")
        source_type = metadata.get("source_type") or (
            "url" if url else "file"
        )
        name = (filename or metadata.get("title") or url or "").strip()
        if context_sources is not None:
            source_number = source_numbers.get(
                metadata.get("source_id")
                or metadata.get("url")
                or metadata.get("source_url")
                or metadata.get("filename")
                or "unknown"
            )
            selected_sources = context_sources.get(source_number, [])
            metadata_section = str(
                metadata.get("section_title") or metadata.get("section") or ""
            ).casefold()
            if not any(
                selected_source["filename"].casefold() == name.casefold()
                and (
                    selected_source["page"] is None
                    or str(metadata.get("page")) == selected_source["page"]
                )
                and (
                    selected_source["section"] is None
                    or metadata_section
                    in {
                        part.strip().casefold()
                        for part in selected_source["section"].split(" - ")
                    }
                )
                for selected_source in selected_sources
            ):
                continue

        try:
            relevance = float(result.get("final_relevance_score"))
        except (TypeError, ValueError):
            relevance = None
        if not name:
            continue

        source_key = (
            str(metadata.get("source_id") or "")
            or (url or "").strip().rstrip("/").casefold()
            or name.casefold()
        )
        current = grouped.get(source_key)
        if current is None:
            grouped[source_key] = {
                "filename": name,
                "type": metadata.get("document_type") or source_type,
                "page": metadata.get("page"),
                "section": metadata.get("section_title") or metadata.get("section"),
                "pages": [],
                "sections": [],
                "url": url,
                "source_id": metadata.get("source_id"),
                "document_id": (
                    document_ids.get(str(metadata.get("source_id")))
                    or document_ids.get(name)
                    or document_ids.get(
                        str(url).strip().rstrip("/").casefold()
                        if url
                        else ""
                    )
                    or metadata.get("document_id")
                ),
                "source_type": source_type,
                "document_type": metadata.get("document_type"),
                "relevance": relevance,
                "relevance_percentage": (
                    round(max(0.0, min(1.0, relevance)) * 100, 1)
                    if relevance is not None
                    else None
                ),
                "snippets": [],
            }
        elif relevance is not None and (
            current["relevance"] is None
            or relevance > current["relevance"]
        ):
            current["relevance"] = relevance
            current["relevance_percentage"] = round(
                max(0.0, min(1.0, relevance)) * 100,
                1,
            )

        citation = grouped[source_key]
        page = metadata.get("page")
        section = metadata.get("section_title") or metadata.get("section")
        if page not in (None, 0, "0") and page not in citation["pages"]:
            citation["pages"].append(page)
        if section and section not in citation["sections"]:
            citation["sections"].append(section)

        snippet_text = " ".join(
            str(result.get("content") or "").split()
        )
        if snippet_text:
            snippet = {
                "page": page,
                "section": section,
                "text": snippet_text[:360],
                "relevance": relevance,
                "relevance_percentage": (
                    round(max(0.0, min(1.0, relevance)) * 100, 1)
                    if relevance is not None
                    else None
                ),
            }
            snippet_identity = (
                str(page or ""),
                str(section or "").casefold(),
                snippet["text"].casefold(),
            )
            if not any(
                (
                    str(existing.get("page") or ""),
                    str(existing.get("section") or "").casefold(),
                    str(existing.get("text") or "").casefold(),
                ) == snippet_identity
                for existing in citation["snippets"]
            ):
                citation["snippets"].append(snippet)

    citations = list(grouped.values())
    citations.sort(
        key=lambda citation: citation["relevance"] or 0.0,
        reverse=True,
    )
    for index, citation in enumerate(citations, start=1):
        citation["pages"].sort(
            key=lambda page: (isinstance(page, str), str(page))
        )
        citation["sections"].sort()
        citation["snippets"].sort(
            key=lambda snippet: (
                str(snippet.get("page") or ""),
                str(snippet.get("section") or "").casefold(),
            )
        )
        if citation["pages"]:
            citation["page"] = citation["pages"][0]
        if citation["sections"]:
            citation["section"] = citation["sections"][0]
        citation["source_number"] = index

    return citations


def filter_displayed_sources(
    citations: list[dict],
) -> list[dict]:
    """Keep unique valid citations for chunks retained in answer context."""
    displayed = []
    seen = set()

    for citation in citations:
        if not isinstance(citation, dict):
            continue

        filename = str(citation.get("filename") or "").strip()
        source_type = str(citation.get("source_type") or "").casefold()
        source_id = str(citation.get("source_id") or "").strip()
        url = str(citation.get("url") or "").strip()
        if (
            not filename
            or filename.casefold() == "no matching source"
            or source_type not in {"file", "url"}
        ):
            continue

        try:
            relevance = float(citation.get("relevance"))
        except (TypeError, ValueError):
            relevance = None
        if relevance is not None and (
            not math.isfinite(relevance)
            or not 0.0 <= relevance <= 1.0
        ):
            continue

        identity = source_id or (
            url.rstrip("/").casefold()
            if source_type == "url" and url
            else filename.casefold()
        )
        if not identity or identity in seen:
            continue

        seen.add(identity)
        displayed.append(citation)

    return displayed


def get_previous_sources(
    conversation_history: list[dict] | None,
) -> list[dict]:

    if not conversation_history:
        return []

    for message in reversed(
        conversation_history
    ):

        if message.get("role") != "assistant":
            continue

        citations = message.get(
            "citations",
            [],
        )

        if not citations:
            return []

        sources = []

        seen = set()

        for citation in citations:
            if citation.get("source_type") not in {"file", "url"}:
                continue

            source = {
                "filename": citation.get(
                    "filename"
                ),
                "url": citation.get(
                    "url"
                ),
                "source_id": citation.get(
                    "source_id"
                ),
            }

            key = (
                source.get("source_id")
                or source.get("url")
                or source.get("filename")
            )

            if not key:
                continue

            if key in seen:
                continue

            seen.add(key)

            sources.append(
                source
            )

        if sources:
            return sources

        return []

    return []

def get_latest_user_question(
    conversation_history: list[dict] | None,
) -> str:

    if not conversation_history:
        return ""

    for message in reversed(
        conversation_history
    ):

        if (
            message.get("role")
            != "user"
        ):
            continue

        content = message.get(
            "content",
            "",
        )

        if content:

            return str(
                content
            ).strip()

    return ""


def query_mentions_previous_source(
    question: str,
    conversation_history: list[dict] | None,
) -> bool:
    query_words = set(
        re.findall(
            r"[a-z0-9]+",
            normalize_source_name(question),
        )
    )
    if not query_words:
        return False

    for source in get_previous_sources(conversation_history):
        source_name = source.get("filename") or source.get("url") or ""
        source_words = set(
            re.findall(
                r"[a-z0-9]+",
                normalize_source_name(source_name),
            )
        )
        if any(
            source_word in query_words
            or any(
                len(query_word) >= 4
                and source_word.startswith(query_word)
                for query_word in query_words
            )
            for source_word in source_words
        ):
            return True

    return False


def is_resume_detail_follow_up(
    question: str,
    conversation_history: list[dict] | None,
) -> bool:
    if not conversation_history:
        return False

    detail_terms = {
        "education",
        "qualification",
        "qualifications",
        "experience",
        "skills",
        "projects",
        "certifications",
        "internships",
    }
    if not set(re.findall(r"[a-z]+", question.lower())).intersection(detail_terms):
        return False

    has_explicit_person = bool(
        re.search(
            r"\b[a-z][a-z0-9-]{2,}['’]s\b",
            question.lower(),
        )
    )
    if has_explicit_person and not query_mentions_previous_source(
        question,
        conversation_history,
    ):
        return False

    source_names = " ".join(
        str(source.get("filename") or "")
        for source in get_previous_sources(conversation_history)
    )
    return bool(
        re.search(r"resume|cv|curriculum|vitae", source_names, re.IGNORECASE)
    )

def extract_requested_section(
    question: str,
) -> str | None:
    """
    Detect:

        Explain point 2
        Explain point 2.1
        Explain section 3
        Explain topic 4
        Explain 2nd point
        Explain 3rd section
        Point 2
        Section 2.3
    """

    if not question:
        return None

    q = " ".join(
        question.lower().split()
    )

    patterns = [
        re.compile(
            r"\b(?:point|section|topic|item|part)"
            r"\s+(\d+(?:\.\d+)*)\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\b(?:explain|describe|elaborate|"
            r"expand|discuss)"
            r"\s+(\d+(?:\.\d+)*)\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\b(\d+)(?:st|nd|rd|th)"
            r"\s+(?:point|section|topic|item|part)\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\b(?:point|section|topic|item)"
            r"\s*(?:no\.?|number)\s*"
            r"(\d+(?:\.\d+)*)\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\b(?:point|section|topic|item)"
            r"\s+number\s+"
            r"(\d+(?:\.\d+)*)\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\b(\d+(?:\.\d+)*)\s+"
            r"(?:point|points|section|sections)\b",
            re.IGNORECASE,
        ),
    ]

    for pattern in patterns:

        match = pattern.search(
            q
        )

        if match:

            return match.group(
                1
            )

    return None


def get_latest_assistant_answer(
    conversation_history: list[dict] | None,
) -> str:
    for message in reversed(conversation_history or []):
        if message.get("role") == "assistant":
            return str(message.get("content", "")).strip()
    return ""


def parse_numbered_answer_points(
    answer: str,
) -> list[dict]:
    if not answer:
        return []

    points = []
    current = None
    point_pattern = re.compile(
        r"^\s*(?:#{1,6}\s*)?(?:[-*]\s*)?(?:\*\*)?"
        r"(\d{1,2}(?:\.\d+)*)(?:\*\*)?[.)]\s*(.+?)\s*$"
    )
    labeled_point_pattern = re.compile(
        r"^\s*(?:#{1,6}\s*)?(?:[-*]\s*)?(?:\*\*)?point\s+"
        r"(\d{1,2}(?:\.\d+)*)(?:\*\*)?\s*[:.)-]\s*(.+?)\s*$",
        re.IGNORECASE,
    )

    def finish_point():
        if current:
            summary = " ".join(current["text"]).strip()
            points.append(
                {
                    "number": current["number"],
                    "text": summary[:700],
                }
            )

    for line in answer.splitlines():
        match = point_pattern.match(line)
        if not match:
            match = labeled_point_pattern.match(line)
        if match:
            finish_point()
            number = match.group(1)
            text = match.group(2).strip()
            text = re.sub(r"\*\*|__|`", "", text).strip()
            current = {"number": number, "text": [text]}
        elif current and line.strip():
            continuation = re.sub(r"\*\*|__|`", "", line.strip())
            current["text"].append(continuation)
    finish_point()
    return points


def get_numbered_point_request(
    question: str,
    conversation_history: list[dict] | None,
) -> dict | None:
    normalized = " ".join(question.lower().split())
    points = parse_numbered_answer_points(
        get_latest_assistant_answer(conversation_history)
    )

    if re.search(
        r"\b(?:all\s+(?:(?:of\s+)?the\s+)?(?:points|items|ones)"
        r"|all\s+of\s+(?:them|those)"
        r"|explain\s+all\s+of\s+them)\b",
        normalized,
    ):
        return {"type": "all", "points": points}

    ordinal_numbers = {
        "first": 1,
        "1st": 1,
        "second": 2,
        "2nd": 2,
        "third": 3,
        "3rd": 3,
        "fourth": 4,
        "4th": 4,
        "fifth": 5,
        "5th": 5,
        "sixth": 6,
        "6th": 6,
        "seventh": 7,
        "7th": 7,
        "eighth": 8,
        "8th": 8,
        "ninth": 9,
        "9th": 9,
        "tenth": 10,
        "10th": 10,
    }

    if re.search(r"\b(?:last|final)\s+(?:point|one|item)\b", normalized):
        if points:
            return {"type": "single", "number": points[-1]["number"]}

    ordinal_match = re.search(
        r"\b(first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|"
        r"\d+(?:st|nd|rd|th))\s+(?:point|one|item)\b",
        normalized,
    )
    if ordinal_match:
        number = ordinal_numbers.get(ordinal_match.group(1))
        if number:
            return {"type": "single", "number": str(number)}

    point_match = re.search(
        r"\b(?:point|item)\s*(?:number\s*|no\.?\s*)?"
        r"(\d{1,2}(?:\.\d+)*)\b",
        normalized,
    )
    if point_match:
        return {"type": "single", "number": point_match.group(1)}

    reversed_point_match = re.search(
        r"\b(\d{1,2}(?:\.\d+)*)\s+(?:points?|items?)\b",
        normalized,
    )
    if reversed_point_match:
        return {
            "type": "single",
            "number": reversed_point_match.group(1),
        }

    number_match = re.search(
        r"\bnumber\s+(\d{1,2})\b",
        normalized,
    )
    if number_match and re.search(
        r"\b(?:explain|elaborate|summari[sz]e|details?|about|important)\b",
        normalized,
    ):
        return {"type": "single", "number": number_match.group(1)}

    if re.search(r"\bnext\s+(?:point|one|item)\b", normalized):
        for message in reversed(conversation_history or []):
            if message.get("role") != "user":
                continue
            previous = get_numbered_point_request(
                str(message.get("content", "")),
                [],
            )
            if previous and previous.get("type") == "single":
                next_number = str(int(previous["number"]) + 1)
                return {"type": "single", "number": next_number}

    return None

def is_follow_up_question(
    question: str,
    conversation_history: list[dict] | None,
) -> bool:

    if not conversation_history:
        return False

    q = " ".join(
        question.lower().split()
    )

    if not q:
        return False

    requested_section = (
        extract_requested_section(
            question
        )
    )

    if requested_section:

        return True

    if get_numbered_point_request(
        question,
        conversation_history,
    ):
        return True

    follow_up_phrases = {
        "tell me more",
        "explain more",
        "explain further",
        "explain it",
        "explain this",
        "explain that",
        "elaborate",
        "elaborate more",
        "in more detail",
        "more details",
        "more about it",
        "more about this",
        "more about that",
        "what does it mean",
        "what does this mean",
        "why is that",
        "why is this",
        "how does it work",
        "how does this work",
        "describe it",
        "describe this",
        "expand on that",
        "expand on this",
        "go deeper",
        "continue",
        "continue with",
        "second topic",
        "first topic",
        "third topic",
        "second point",
        "first point",
        "third point",
        "that point",
        "that topic",
        "this point",
        "this topic",
        "previous answer",
        "previous point",
        "previous topic",
        "above answer",
        "above point",
        "what about",
        "which one",
        "which of them",
        "which of those",
        "the previous one",
        "the above",
    }

    if any(
        phrase in q
        for phrase in follow_up_phrases
    ):

        return True

    words = set(
        re.findall(
            r"\b[a-zA-Z]+\b",
            q,
        )
    )

    reference_words = {
        "it",
        "this",
        "that",
        "they",
        "them",
        "these",
        "those",
        "its",
        "their",
        "he",
        "him",
        "his",
        "she",
        "her",
        "here",
        "one",
        "ones",
        "above",
        "previous",
    }

    if (
        words.intersection(
            reference_words
        )
        and len(words) <= 14
    ):

        return True

    if query_mentions_previous_source(
        question,
        conversation_history,
    ) or is_resume_detail_follow_up(
        question,
        conversation_history,
    ):
        return True

    if re.search(r"\bthere\b", q) and not re.search(
        r"\b(?:is|are|was|were)\s+there\b",
        q,
    ):
        return True

    short_followups = {
        "why?",
        "how?",
        "what about it?",
        "what about this?",
        "what about that?",
        "and why?",
        "and how?",
        "can you explain?",
        "what else?",
    }

    return (
        q in short_followups
    )

def build_retrieval_query(
    question: str,
    conversation_history: list[dict] | None,
    follow_up: bool,
) -> str:
    """Resolve a follow-up into a focused query without concatenating history."""

    question = question.strip()

    if not follow_up:
        return question

    if not conversation_history:
        return question

    requested_section = (
        extract_requested_section(
            question
        )
    )

    previous_question = get_latest_user_question(
        conversation_history
    )
    sources = get_previous_sources(
        conversation_history
    )
    source_names = []
    for source in sources:
        name = source.get("filename") or source.get("url")
        if name and name not in source_names:
            source_names.append(str(name))

    point_request = get_numbered_point_request(
        question,
        conversation_history,
    )
    if point_request:
        points = point_request.get("points") or parse_numbered_answer_points(
            get_latest_assistant_answer(conversation_history)
        )
        if point_request["type"] == "all":
            point_summaries = "; ".join(
                point["text"]
                for point in points
            )
            if point_summaries:
                resolved = (
                    "Requested task: explain all ideas listed in the latest "
                    "assistant answer. Ideas to support: "
                    + point_summaries
                )
                if previous_question:
                    resolved += f" Topic from the preceding user question: {previous_question}."
                if source_names:
                    resolved += " Relevant sources: " + "; ".join(source_names) + "."
                return resolved

        elif point_request["type"] == "single":
            requested_number = point_request["number"]
            selected_point = next(
                (
                    point
                    for point in points
                    if point["number"] == requested_number
                ),
                None,
            )
            if selected_point:
                resolved = (
                    "Requested task: explain only the following idea from "
                    "the latest assistant answer. Retrieve supporting "
                    "evidence for it: "
                    f"{selected_point['text']}"
                )
                if previous_question:
                    resolved += (
                        " Topic from the preceding user question: "
                        f"{previous_question}."
                    )
                if source_names:
                    resolved += " Relevant sources: " + "; ".join(source_names) + "."
                return resolved

    if requested_section:
        if previous_question:
            resolved = (
                f"{question} In the context of the previous question: "
                f"{previous_question}. Requested section or point: "
                f"{requested_section}."
            )
            if source_names:
                resolved += " Relevant source(s): " + "; ".join(source_names) + "."
            return resolved
        return question

    latest_answer = get_latest_assistant_answer(
        conversation_history
    )
    if latest_answer:
        answer_context = latest_answer[:1600]
        if len(latest_answer) > len(answer_context):
            answer_context = answer_context.rsplit(" ", 1)[0]
        resolved = (
            f"Previous topic: {previous_question}\n"
            f"Current follow-up request: {question}\n"
            f"Relevant context from the latest assistant answer: "
            f"{answer_context}"
        )
        if source_names:
            resolved += "\nRelevant previously used sources: " + "; ".join(
                source_names
            )
        return resolved

    topic = extract_definition_topic(
        previous_question
    ) if previous_question else None

    rewritten = question
    if topic:
        rewritten = re.sub(
            r"\b(?:its|their)\s+([\w-]+)",
            lambda match: f"{match.group(1)} of {topic}",
            rewritten,
            flags=re.IGNORECASE,
        )
        rewritten = re.sub(
            r"\b(?:it|this|that)\b",
            topic,
            rewritten,
            flags=re.IGNORECASE,
        )
    rewritten = re.sub(
        r"\b(?:his|her)\s+([\w-]+)",
        r"\1",
        rewritten,
        flags=re.IGNORECASE,
    )
    rewritten = re.sub(
        r"\b(?:he|him|she)\b",
        "",
        rewritten,
        flags=re.IGNORECASE,
    )
    rewritten = re.sub(
        r"\b(?:there|here)\b",
        "",
        rewritten,
        flags=re.IGNORECASE,
    )

    if source_names:
        if len(source_names) == 1:
            rewritten = re.sub(
                r"\b(?:there|here)\b",
                "",
                rewritten,
                flags=re.IGNORECASE,
            ).strip()
            if not query_mentions_previous_source(
                rewritten,
                conversation_history,
            ):
                rewritten = f"{rewritten.rstrip(' ?.')} in {source_names[0]}"
        else:
            rewritten += (
                " Compare only these relevant sources from the previous "
                "comparison: "
                + "; ".join(source_names)
                + "."
            )

    elif topic and topic.casefold() not in rewritten.casefold():
        rewritten += f" Topic: {topic}."

    return rewritten


def get_relevant_conversation_history(
    conversation_history: list[dict] | None,
    max_messages: int = 4,
) -> list[dict]:
    """Keep only the recent turns needed by the answer prompt."""
    if not conversation_history:
        return []

    recent = []
    for message in conversation_history[-max_messages:]:
        content = str(message.get("content", "")).strip()
        if not content:
            continue
        recent.append(
            {
                "role": message.get("role", ""),
                "content": content[-800:],
            }
        )
    return recent


def _can_answer_from_general_knowledge(
    question: str,
    follow_up: bool,
) -> bool:
    if follow_up or extract_requested_section(question):
        return False

    normalized = re.sub(r"\s+", " ", question.casefold()).strip()
    document_intent_terms = (
        "resume", "cv", "skill", "education", "experience", "author",
        "document", "file", "report", "source", "uploaded", "mentioned",
        "listed", "contained", "contains", "summarize", "summary",
        "compare", "common", "shared", "difference", "similarity",
        "point", "points", "conclusion", "this", "these", "those",
        "there", "here", "my ",
    )
    if any(term in normalized for term in document_intent_terms):
        return False

    if re.match(r"^who\s+is\s+(?!the\b|a\b|an\b|it\b|this\b|that\b)[^?]+", normalized):
        return False

    return bool(normalized)


def answer_question(
    user_id: str,
    question: str,
    conversation_history: list[dict] | None = None,
    attached_sources: list[dict] | None = None,
):
    request_started_at = time.perf_counter()

    question = question.strip()

    if not question:

        return {
            "answer": (
                "Please enter a question."
            ),
            "citations": [],
        }

    conversation_history = (
        conversation_history or []
    )

    point_request = get_numbered_point_request(
        question,
        conversation_history,
    )
    if point_request:
        previous_points = point_request.get("points") or parse_numbered_answer_points(
            get_latest_assistant_answer(conversation_history)
        )
        if point_request["type"] == "all" and not previous_points:
            return {
                "answer": (
                    "I could not identify numbered points in the latest "
                    "answer. Could you tell me which part you would like "
                    "explained?"
                ),
                "citations": [],
            }
        if point_request["type"] == "single":
            requested_number = point_request["number"]
            if not any(
                point["number"] == requested_number
                for point in previous_points
            ):
                return {
                    "answer": (
                        f"I could not identify point {requested_number} in "
                        "the latest answer. Could you paste or describe the "
                        "point you mean?"
                    ),
                    "citations": [],
                }

    if (
        is_all_sources_query(question)
        and not is_resume_discovery_query(question)
    ):
        documents = list_user_documents(user_id)
        if not documents:
            return {
                "answer": "You do not have any documents or website sources yet.",
                "citations": [],
            }

        file_names = []
        website_names = []
        for document in documents:
            if document.get("source_type") == "url":
                name = (
                    document.get("filename")
                    or document.get("source_url")
                    or "Website source"
                )
                source_url = document.get("source_url")
                if source_url and source_url != name:
                    name = f"{name} — {source_url}"
                website_names.append(str(name))
            else:
                name = document.get("filename") or "Untitled document"
                file_type = document.get("file_type")
                if file_type:
                    name = f"{name} [{file_type}]"
                file_names.append(str(name))

        sections = ["Available sources:"]
        if file_names:
            sections.append(
                "Uploaded files:\n" + "\n".join(f"- {name}" for name in file_names)
            )
        if website_names:
            sections.append(
                "Website sources:\n" + "\n".join(f"- {name}" for name in website_names)
            )

        return {
            "answer": "\n\n".join(sections),
            "citations": [],
        }

    if is_resume_discovery_query(question):
        resumes = discover_resumes(user_id=user_id)
        if not resumes:
            return {
                "answer": "No resumes are available in your sources.",
                "citations": [],
            }
        names = [
            str(document.get("filename") or document.get("source") or "Resume")
            for document in resumes
        ]
        return {
            "answer": "Available resumes:\n" + "\n".join(f"- {name}" for name in names),
            "citations": [],
        }

    follow_up = (
        is_follow_up_question(
            question=question,
            conversation_history=(
                conversation_history
            ),
        )
    )

    requested_section = (
        extract_requested_section(
            question
        )
    )

    previous_sources = []

    if follow_up:

        previous_sources = (
            get_previous_sources(
                conversation_history
            )
        )

    retrieval_query = (
        build_retrieval_query(
            question=question,
            conversation_history=(
                conversation_history
            ),
            follow_up=follow_up,
        )
    )

    relevant_history = get_relevant_conversation_history(
        conversation_history
    )

    retrieval_started_at = time.perf_counter()
    retrieval_metadata = {}
    results = hybrid_retrieve(
        user_id=user_id,
        query=retrieval_query,
        limit=None,
        preferred_sources=(
            previous_sources
            if follow_up
            else None
        ),
        attached_sources=attached_sources,
        retrieval_metadata=retrieval_metadata,
    )
    searched_files = retrieval_metadata.get("searched_files", [])
    retrieval_seconds = time.perf_counter() - retrieval_started_at

    context_started_at = time.perf_counter()
    context = build_context(results) if results else ""
    context_build_seconds = time.perf_counter() - context_started_at

    if not context.strip():
        if re.search(
            r"\.(?:pdf|docx?|txt|csv|xlsx|pptx)\b",
            question,
            re.IGNORECASE,
        ):
            logger.info(
                "RAG source-restricted question produced no indexed context; general generation skipped."
            )
            return {
                "answer": (
                    "I could not find retrievable indexed content in the requested document. "
                    "Check that the document is available and indexed, then try again."
                ),
                "citations": [],
                "searched_files": searched_files,
            }
        if point_request:
            return {
                "answer": (
                    "I found the referenced item in the latest answer, "
                    "but your indexed sources do not provide enough detail "
                    "to explain it reliably. Could you share which part of "
                    "that item you would like clarified?"
                ),
                "citations": [],
                "searched_files": searched_files,
            }
        if not _can_answer_from_general_knowledge(question, follow_up):
            return {
                "answer": "I could not find relevant information in your available sources.",
                "citations": [],
                "searched_files": searched_files,
            }
        generation_started_at = time.perf_counter()
        try:
            answer = generate_answer(
                question=question,
                context="",
                conversation_history=relevant_history,
                allow_general_knowledge=True,
            )
        finally:
            logger.info(
                "RAG stages: retrieval_seconds=%.3f context_build_seconds=%.3f "
                "context_fit_seconds=0 generation_seconds=%.3f citation_seconds=0 "
                "total_seconds=%.3f candidate_chunks=%d source_count=0 context_characters=0",
                retrieval_seconds,
                context_build_seconds,
                time.perf_counter() - generation_started_at,
                time.perf_counter() - request_started_at,
                len(results),
            )
        return {
            "answer": (
                "This answer is based on general knowledge, not your uploaded sources.\n\n"
                + answer
            ),
            "citations": [],
            "searched_files": searched_files,
        }

    context_fit_started_at = time.perf_counter()
    model_question, context, prepared_history = fit_generation_context(
        question=retrieval_query,
        context=context,
        conversation_history=relevant_history,
    )
    context_fit_seconds = time.perf_counter() - context_fit_started_at

    generation_started_at = time.perf_counter()
    try:
        answer = generate_answer(
            question=model_question,
            context=context,
            conversation_history=relevant_history,
            prepared_history=prepared_history,
        )
    except Exception as error:
        logger.error(
            "RAG generation failed: error_type=%s elapsed_seconds=%.3f",
            type(error).__name__,
            time.perf_counter() - generation_started_at,
        )
        raise
    finally:
        generation_seconds = time.perf_counter() - generation_started_at

    citation_started_at = time.perf_counter()
    # Preserve all retriever-selected sources (already subject to the
    # retriever's relevance filtering and user/source restrictions). The
    # answer citations remain separately limited to final prompt context.
    retrieved_sources = create_citations(
        qualifying_source_card_chunks(results),
        user_id=user_id,
    )
    citations = filter_displayed_sources(
        create_citations(
            results,
            context=context,
            user_id=user_id,
        )
    )
    citation_seconds = time.perf_counter() - citation_started_at

    logger.info(
        "RAG stages: retrieval_seconds=%.3f context_build_seconds=%.3f "
        "context_fit_seconds=%.3f generation_seconds=%.3f citation_seconds=%.3f "
        "total_seconds=%.3f candidate_chunks=%d source_count=%d context_characters=%d",
        retrieval_seconds,
        context_build_seconds,
        context_fit_seconds,
        generation_seconds,
        citation_seconds,
        time.perf_counter() - request_started_at,
        len(results),
        len(
            {
                str(
                    result.get("metadata", {}).get("source_id")
                    or result.get("metadata", {}).get("filename")
                    or result.get("metadata", {}).get("url")
                    or result.get("id")
                )
                for result in results
            }
        ),
        len(context),
    )

    return {
        "answer": answer,
        "citations": citations,
        "sources": retrieved_sources,
        "searched_files": searched_files,
    }
