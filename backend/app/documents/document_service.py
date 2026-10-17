import os
import re
import logging
import tempfile
import time
import zipfile

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import cloudinary
import cloudinary.uploader

from bson import ObjectId
from dotenv import load_dotenv

from app.database.mongodb import documents_collection
from app.documents.loader import load_document
from app.documents.splitter import split_document_pages

from app.rag.vector_store import (
    add_chunks,
    delete_source,
)


load_dotenv()


# =========================================================
# CONSTANTS
# =========================================================

ALLOWED_EXTENSIONS = {
    ".pdf",
    ".docx",
    ".txt",
    ".csv",
    ".xlsx",
    ".pptx",
}

CLOUDINARY_FOLDER = "multi-document-research"
logger = logging.getLogger(__name__)
MAX_DOCUMENT_TEXT_CHARACTERS = 5_000_000
MAX_DOCUMENT_CHUNKS = 5_000
MAX_OFFICE_ARCHIVE_EXPANDED_BYTES = 32 * 1024 * 1024
MAX_OFFICE_ARCHIVE_ENTRIES = 10_000


def validate_office_archive_size(file_path: str | Path, extension: str) -> None:
    if extension not in {".docx", ".xlsx", ".pptx"}:
        return

    try:
        with zipfile.ZipFile(file_path) as archive:
            entries = archive.infolist()
            expanded_size = sum(entry.file_size for entry in entries)
    except zipfile.BadZipFile as error:
        raise ValueError("The uploaded Office document is not a valid archive") from error

    if len(entries) > MAX_OFFICE_ARCHIVE_ENTRIES:
        raise ValueError(
            "The document contains too many embedded parts to process safely"
        )
    if expanded_size > MAX_OFFICE_ARCHIVE_EXPANDED_BYTES:
        raise ValueError(
            "The expanded Office document exceeds the 32 MB processing limit"
        )


# =========================================================
# CLOUDINARY CONFIGURATION
# =========================================================

cloudinary.config(
    cloud_name=os.getenv(
        "CLOUDINARY_CLOUD_NAME"
    ),
    api_key=os.getenv(
        "CLOUDINARY_API_KEY"
    ),
    api_secret=os.getenv(
        "CLOUDINARY_API_SECRET"
    ),
)


# =========================================================
# DOCUMENT TYPE CLASSIFICATION
# =========================================================
#
# We classify the document ONCE during upload.
#
# Examples:
#
# resume
# report
# research_paper
# assignment
# presentation
# spreadsheet
# text_document
# other
#
# This value is stored in:
#
# 1. MongoDB
# 2. ChromaDB metadata
#
# Retrieval can then use document_type as a hard filter.
# =========================================================


DOCUMENT_TYPE_RULES = {
    "resume": {
        "strong": [
            "resume",
            "curriculum vitae",
            "curriculum-vitae",
            "professional summary",
            "career objective",
            "work experience",
            "professional experience",
            "employment history",
            "education",
            "technical skills",
            "skills",
            "projects",
            "certifications",
            "certification",
            "internship",
            "internships",
            "linkedin",
            "github",
            "contact",
            "phone",
            "email",
        ],
        "section_headers": [
            "education",
            "experience",
            "work experience",
            "professional experience",
            "skills",
            "technical skills",
            "projects",
            "certifications",
            "achievements",
            "languages",
            "internship",
            "internships",
            "objective",
            "summary",
        ],
    },
    "research_paper": {
        "strong": [
            "abstract",
            "keywords",
            "introduction",
            "methodology",
            "literature review",
            "results",
            "discussion",
            "conclusion",
            "references",
            "doi",
        ],
        "section_headers": [
            "abstract",
            "introduction",
            "methodology",
            "literature review",
            "results",
            "discussion",
            "conclusion",
            "references",
        ],
    },
    "assignment": {
        "strong": [
            "assignment",
            "submitted by",
            "submitted to",
            "roll number",
            "register number",
            "department",
            "academic year",
            "course",
            "subject",
            "question",
            "answer",
        ],
        "section_headers": [
            "assignment",
            "introduction",
            "objective",
            "question",
            "answer",
            "conclusion",
        ],
    },
    "report": {
        "strong": [
            "report",
            "executive summary",
            "findings",
            "recommendations",
            "analysis",
            "conclusion",
            "appendix",
        ],
        "section_headers": [
            "executive summary",
            "introduction",
            "analysis",
            "findings",
            "recommendations",
            "conclusion",
            "appendix",
        ],
    },
}


# =========================================================
# TEXT NORMALIZATION
# =========================================================


def normalize_text(
    text: str,
) -> str:
    """
    Normalize text for document classification.
    """

    if not text:
        return ""

    text = str(text).lower()

    text = re.sub(
        r"[_\-]+",
        " ",
        text,
    )

    text = re.sub(
        r"[^a-z0-9@.+#\s]",
        " ",
        text,
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()


# =========================================================
# FILENAME NORMALIZATION
# =========================================================


def normalize_filename(
    filename: str,
) -> str:
    """
    Normalize filename without extension.

    Example:

    AnisFathimaResume (2).pdf

    becomes approximately:

    anis fathima resume
    """

    name = Path(
        filename
    ).stem

    name = re.sub(
        r"([a-z])([A-Z])",
        r"\1 \2",
        name,
    )

    name = re.sub(
        r"[_\-]+",
        " ",
        name,
    )

    name = re.sub(
        r"\(\d+\)",
        " ",
        name,
    )

    name = re.sub(
        r"\b(final|latest|new|updated|copy)\b",
        " ",
        name,
        flags=re.IGNORECASE,
    )

    name = re.sub(
        r"\s+",
        " ",
        name,
    )

    return name.strip().lower()


# =========================================================
# EXTRACT SAMPLE TEXT
# =========================================================


def build_classification_text(
    pages: list[dict],
    max_characters: int = 20000,
) -> str:
    """
    Combine enough extracted text for document classification.

    We do not need the complete document here.
    Classification only needs representative content.
    """

    if not pages:
        return ""

    parts = []

    current_length = 0

    for page in pages:

        if not isinstance(page, dict):
            continue

        text = page.get(
            "text",
            "",
        )

        if not text:
            continue

        remaining = (
            max_characters
            - current_length
        )

        if remaining <= 0:
            break

        text = str(text)[
            :remaining
        ]

        parts.append(text)

        current_length += len(text)

    return "\n".join(parts)


# =========================================================
# DOCUMENT TYPE CLASSIFIER
# =========================================================


def classify_document(
    filename: str,
    pages: list[dict],
) -> tuple[str, float]:
    """
    Classify a document using filename + extracted content.

    Returns:

        (
            document_type,
            confidence
        )

    Confidence is between 0 and 1.

    The classifier is intentionally deterministic so
    uploading a document does not require another LLM call.
    """

    filename_text = normalize_filename(
        filename
    )

    content_text = normalize_text(
        build_classification_text(
            pages
        )
    )

    combined_text = (
        f"{filename_text} "
        f"{content_text}"
    ).strip()

    if not combined_text:
        return (
            "other",
            0.0,
        )

    scores = {
        document_type: 0.0
        for document_type in DOCUMENT_TYPE_RULES
    }

    # -----------------------------------------------------
    # Filename signals
    # -----------------------------------------------------

    if any(
        term in filename_text
        for term in (
            "resume",
            "cv",
            "curriculum vitae",
        )
    ):
        scores["resume"] += 8.0

    if "assignment" in filename_text:
        scores["assignment"] += 7.0

    if any(
        term in filename_text
        for term in (
            "research",
            "paper",
            "journal",
        )
    ):
        scores["research_paper"] += 5.0

    if "report" in filename_text:
        scores["report"] += 5.0

    # -----------------------------------------------------
    # Content signals
    # -----------------------------------------------------

    for document_type, rules in (
        DOCUMENT_TYPE_RULES.items()
    ):

        for term in rules["strong"]:

            occurrences = content_text.count(
                term
            )

            if occurrences > 0:

                # Cap repeated words so a long document
                # does not win simply because one word
                # appears many times.
                scores[document_type] += min(
                    occurrences,
                    5,
                ) * 1.0

        for section in rules[
            "section_headers"
        ]:

            if re.search(
                rf"\b{re.escape(section)}\b",
                content_text,
            ):
                scores[document_type] += 2.0

    # -----------------------------------------------------
    # Resume-specific structural signals
    # -----------------------------------------------------

    resume_signals = 0

    if re.search(
        r"\b(?:phone|mobile|contact)\b",
        content_text,
    ):
        resume_signals += 1

    if re.search(
        r"\b(?:email|e-mail)\b",
        content_text,
    ):
        resume_signals += 1

    if re.search(
        r"\b(?:education|qualification)\b",
        content_text,
    ):
        resume_signals += 1

    if re.search(
        r"\b(?:skills|technical skills)\b",
        content_text,
    ):
        resume_signals += 1

    if re.search(
        r"\b(?:experience|work experience)\b",
        content_text,
    ):
        resume_signals += 1

    if re.search(
        r"\b(?:projects|project)\b",
        content_text,
    ):
        resume_signals += 1

    if re.search(
        r"\b(?:certification|certifications)\b",
        content_text,
    ):
        resume_signals += 1

    if resume_signals >= 3:
        scores["resume"] += 6.0

    elif resume_signals == 2:
        scores["resume"] += 3.0

    # -----------------------------------------------------
    # Research paper structural signals
    # -----------------------------------------------------

    research_signals = 0

    for term in (
        "abstract",
        "methodology",
        "literature review",
        "references",
        "doi",
        "results",
        "discussion",
    ):

        if term in content_text:
            research_signals += 1

    if research_signals >= 4:
        scores["research_paper"] += 6.0

    elif research_signals >= 2:
        scores["research_paper"] += 3.0

    # -----------------------------------------------------
    # Assignment structural signals
    # -----------------------------------------------------

    assignment_signals = 0

    for term in (
        "assignment",
        "submitted by",
        "submitted to",
        "question",
        "answer",
        "roll number",
        "register number",
    ):

        if term in content_text:
            assignment_signals += 1

    if assignment_signals >= 3:
        scores["assignment"] += 5.0

    elif assignment_signals >= 2:
        scores["assignment"] += 2.5

    # -----------------------------------------------------
    # Determine winner
    # -----------------------------------------------------

    ranked = sorted(
        scores.items(),
        key=lambda item: item[1],
        reverse=True,
    )

    best_type, best_score = ranked[0]

    second_score = (
        ranked[1][1]
        if len(ranked) > 1
        else 0.0
    )

    if best_score <= 0:
        return (
            "other",
            0.0,
        )

    # -----------------------------------------------------
    # Confidence
    # -----------------------------------------------------

    total_score = sum(
        scores.values()
    )

    if total_score > 0:
        confidence = (
            best_score / total_score
        )
    else:
        confidence = 0.0

    # Strong winner gets additional confidence.
    if (
        best_score >= 10
        and best_score > second_score * 1.25
    ):
        confidence = max(
            confidence,
            0.85,
        )

    elif (
        best_score >= 7
        and best_score > second_score * 1.15
    ):
        confidence = max(
            confidence,
            0.70,
        )

    confidence = min(
        max(
            confidence,
            0.0,
        ),
        1.0,
    )

    return (
        best_type,
        round(
            confidence,
            4,
        ),
    )


# =========================================================
# PROCESS UPLOADED DOCUMENT
# =========================================================


def process_uploaded_document(
    user_id: str,
    filename: str,
    content: bytes | None = None,
    *,
    file_path: str | Path | None = None,
):
    """
    Upload, extract, classify, chunk, embed and store
    a document.
    """

    extension = Path(
        filename
    ).suffix.lower()

    if extension not in ALLOWED_EXTENSIONS:
        raise ValueError(
            "Only PDF, DOCX, TXT, CSV, XLSX and PPTX files are supported"
        )

    if file_path is None and not content:
        raise ValueError(
            "Uploaded file is empty"
        )

    if file_path is not None and not Path(file_path).is_file():
        raise ValueError(
            "Uploaded file is empty"
        )

    source_id = uuid4().hex

    cloudinary_result = None
    vector_ids = []
    processing_stage = "cloudinary_upload"

    try:

        if file_path is not None:
            processing_stage = "document_validation"
            validate_office_archive_size(file_path, extension)
            processing_stage = "cloudinary_upload"

        # =================================================
        # 1. Upload original file to Cloudinary
        # =================================================

        original_filename = Path(
            filename
        ).name

        stage_started_at = time.perf_counter()
        logger.info("Document processing stage started: stage=%s", processing_stage)
        cloudinary_result = (
            cloudinary.uploader.upload(
                str(file_path) if file_path is not None else content,
                resource_type="raw",
                type="upload",
                folder=CLOUDINARY_FOLDER,
                asset_folder=CLOUDINARY_FOLDER,
                public_id=original_filename,
                overwrite=False,
            )
        )
        logger.info(
            "Document processing stage completed: stage=%s elapsed_seconds=%.3f",
            processing_stage,
            time.perf_counter() - stage_started_at,
        )

        cloudinary_url = (
            cloudinary_result.get(
                "secure_url"
            )
        )

        actual_public_id = (
            cloudinary_result.get(
                "public_id"
            )
            or original_filename
        )

        if not cloudinary_url:
            raise ValueError(
                "Cloudinary upload failed"
            )

        # =================================================
        # 2. Create temporary local file
        # =================================================

        temporary_path = Path(file_path) if file_path is not None else None
        owns_temporary_path = temporary_path is None

        try:
            if temporary_path is None:
                with tempfile.NamedTemporaryFile(
                    suffix=extension,
                    delete=False,
                ) as temporary_file:
                    temporary_file.write(content)
                    temporary_path = Path(temporary_file.name)

            # =================================================
            # 3. Extract document text
            # =================================================

            processing_stage = "document_extraction"
            stage_started_at = time.perf_counter()
            logger.info("Document processing stage started: stage=%s", processing_stage)
            if file_path is None:
                validate_office_archive_size(temporary_path, extension)
            pages = load_document(
                str(temporary_path)
            )
            logger.info(
                "Document processing stage completed: stage=%s page_count=%d elapsed_seconds=%.3f",
                processing_stage,
                len(pages),
                time.perf_counter() - stage_started_at,
            )

            if not pages:
                raise ValueError(
                    "No readable text was found in the document"
                )

            if (
                sum(len(page.get("text") or "") for page in pages)
                > MAX_DOCUMENT_TEXT_CHARACTERS
            ):
                raise ValueError(
                    "The extracted document text exceeds the 5 million character processing limit"
                )

            # =================================================
            # 4. CLASSIFY DOCUMENT
            # =================================================

            document_type, document_type_confidence = (
                classify_document(
                    filename=filename,
                    pages=pages,
                )
            )

            # =================================================
            # 5. Split document into hierarchy-aware chunks
            # =================================================

            chunks = split_document_pages(
                pages
            )

            if not chunks:
                raise ValueError(
                    "No readable text was found in the document"
                )

            if len(chunks) > MAX_DOCUMENT_CHUNKS:
                raise ValueError(
                    "The document exceeds the 5,000 chunk processing limit"
                )

            texts = [
                chunk["text"]
                for chunk in chunks
            ]

            # =================================================
            # 6. Create RAG metadata
            # =================================================

            metadatas = []

            for chunk in chunks:

                metadata = {
                    "source_id": source_id,
                    "filename": filename,
                    "file_type": extension.lstrip(
                        "."
                    ),
                    "page": (
                        chunk.get("page")
                        if chunk.get("page")
                        is not None
                        else 0
                    ),
                    "source_type": "file",

                    # NEW
                    "document_type": document_type,
                    "document_type_confidence": float(
                        document_type_confidence
                    ),
                }

                # =================================================
                # Section hierarchy metadata
                # =================================================

                section = chunk.get(
                    "section"
                )

                section_title = chunk.get(
                    "section_title"
                )

                parent_section = chunk.get(
                    "parent_section"
                )

                hierarchy_level = chunk.get(
                    "hierarchy_level",
                    0,
                )

                # ChromaDB metadata values must be
                # simple scalar values.

                if section is not None:

                    metadata[
                        "section"
                    ] = section

                if section_title is not None:

                    metadata[
                        "section_title"
                    ] = section_title

                if parent_section is not None:

                    metadata[
                        "parent_section"
                    ] = parent_section

                metadata[
                    "hierarchy_level"
                ] = int(
                    hierarchy_level
                )

                metadatas.append(
                    metadata
                )

            # =================================================
            # 7. Store chunks and embeddings
            # =================================================

            processing_stage = "embedding_and_vector_storage"
            stage_started_at = time.perf_counter()
            logger.info(
                "Document processing stage started: stage=%s chunks=%d",
                processing_stage,
                len(texts),
            )
            vector_ids = add_chunks(
                user_id=user_id,
                chunks=texts,
                metadatas=metadatas,
            )
            logger.info(
                "Document processing stage completed: stage=%s chunks=%d elapsed_seconds=%.3f",
                processing_stage,
                len(vector_ids),
                time.perf_counter() - stage_started_at,
            )
            del pages, chunks, texts, metadatas

        finally:

            if (
                owns_temporary_path
                and temporary_path is not None
                and temporary_path.exists()
            ):
                temporary_path.unlink()

        # =================================================
        # 8. Save document metadata to MongoDB
        # =================================================

        document = {
            "user_id": user_id,
            "source_id": source_id,
            "filename": filename,
            "file_type": extension.lstrip(
                "."
            ),
            "source_type": "file",
            "source_url": None,

            # NEW
            "document_type": document_type,
            "document_type_confidence": (
                document_type_confidence
            ),

            "cloudinary_url": cloudinary_url,
            "cloudinary_public_id": actual_public_id,
            "chunk_count": len(
                vector_ids
            ),
            "created_at": datetime.now(
                timezone.utc
            ),
        }

        processing_stage = "metadata_storage"
        stage_started_at = time.perf_counter()
        result = documents_collection.insert_one(
            document
        )
        logger.info(
            "Document processing stage completed: stage=%s elapsed_seconds=%.3f",
            processing_stage,
            time.perf_counter() - stage_started_at,
        )

        return {
            "id": str(
                result.inserted_id
            ),
            "filename": filename,
            "file_type": document[
                "file_type"
            ],
            "source_type": "file",
            "source_url": None,

            # NEW
            "document_type": document_type,
            "document_type_confidence": (
                document_type_confidence
            ),

            "cloudinary_url": cloudinary_url,
            "cloudinary_public_id": (
                actual_public_id
            ),
            "chunk_count": len(
                vector_ids
            ),
        }

    except Exception as error:
        logger.error(
            "Document processing failed: stage=%s error_type=%s",
            processing_stage,
            type(error).__name__,
        )

        # =================================================
        # Rollback vector data
        # =================================================

        if vector_ids:

            try:

                delete_source(
                    user_id=user_id,
                    source_type="file",
                    source_value=filename,
                    source_id=source_id,
                )

            except Exception as cleanup_error:

                logger.warning(
                    "Vector cleanup failed: error_type=%s",
                    type(cleanup_error).__name__,
                )

        # =================================================
        # Rollback Cloudinary upload
        # =================================================

        if cloudinary_result:

            try:

                public_id = (
                    cloudinary_result.get(
                        "public_id"
                    )
                )

                if public_id:

                    cloudinary.uploader.destroy(
                        public_id,
                        resource_type="raw",
                    )

            except Exception as cleanup_error:

                logger.warning(
                    "Cloudinary cleanup failed: error_type=%s",
                    type(cleanup_error).__name__,
                )

        raise


# =========================================================
# LIST USER DOCUMENTS
# =========================================================


def list_user_documents(
    user_id: str,
):
    """
    Return all documents belonging to the user.
    """

    documents = (
        documents_collection.find(
            {
                "user_id": user_id
            }
        )
        .sort(
            "created_at",
            -1,
        )
    )

    return [
        {
            "id": str(
                document["_id"]
            ),
            "filename": document.get(
                "filename",
                "",
            ),
            "file_type": document.get(
                "file_type",
                "",
            ),
            "source_type": document.get(
                "source_type",
                "file",
            ),
            "source_url": document.get(
                "source_url"
            ),

            # NEW
            "document_type": document.get(
                "document_type",
                "other",
            ),
            "document_type_confidence": document.get(
                "document_type_confidence",
                0.0,
            ),

            "cloudinary_url": document.get(
                "cloudinary_url"
            ),
            "cloudinary_public_id": document.get(
                "cloudinary_public_id"
            ),
        }
        for document in documents
    ]


# =========================================================
# DELETE USER DOCUMENT
# =========================================================


def delete_user_document(
    user_id: str,
    document_id: str,
):
    """
    Delete document from:

    - ChromaDB
    - Cloudinary
    - MongoDB
    """

    if not ObjectId.is_valid(
        document_id
    ):
        raise ValueError(
            "Invalid document ID"
        )

    document = documents_collection.find_one(
        {
            "_id": ObjectId(
                document_id
            ),
            "user_id": user_id,
        }
    )

    if not document:
        raise ValueError(
            "Document not found"
        )

    source_type = document.get(
        "source_type",
        "file",
    )

    # =================================================
    # Delete vectors
    # =================================================

    if source_type == "file":

        filename = document.get(
            "filename",
            "",
        )

        delete_source(
            user_id=user_id,
            source_type="file",
            source_value=filename,
            source_id=document.get("source_id"),
        )

    elif source_type == "url":

        source_url = document.get(
            "source_url"
        )

        if source_url:

            delete_source(
                user_id=user_id,
                source_type="url",
                source_value=source_url,
                source_id=document.get("source_id"),
            )

    # =================================================
    # Delete file from Cloudinary
    # =================================================

    cloudinary_public_id = document.get(
        "cloudinary_public_id"
    )

    if cloudinary_public_id:

        cloudinary.uploader.destroy(
            cloudinary_public_id,
            resource_type="raw",
        )

    # =================================================
    # Delete document metadata from MongoDB
    # =================================================

    documents_collection.delete_one(
        {
            "_id": ObjectId(
                document_id
            ),
            "user_id": user_id,
        }
    )

    return document
