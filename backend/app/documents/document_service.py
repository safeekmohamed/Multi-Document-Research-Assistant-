from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from bson import ObjectId

from app.core.config import settings
from app.database.mongodb import (
    documents_collection,
)
from app.documents.loader import (
    load_document,
)
from app.documents.splitter import (
    split_document_pages,
)
from app.rag.vector_store import (
    add_chunks,
    delete_source,
)


ALLOWED_EXTENSIONS = {
    ".pdf",
    ".docx",
    ".txt",
}


def save_uploaded_file(
    filename: str,
    content: bytes,
):
    upload_directory = Path(
        settings.UPLOAD_PATH
    )

    upload_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    extension = Path(
        filename
    ).suffix.lower()

    if extension not in ALLOWED_EXTENSIONS:
        raise ValueError(
            "Only PDF, DOCX and TXT files are supported"
        )

    stored_filename = (
        f"{uuid4()}{extension}"
    )

    file_path = (
        upload_directory
        / stored_filename
    )

    file_path.write_bytes(content)

    return file_path


def process_uploaded_document(
    user_id: str,
    filename: str,
    content: bytes,
):
    file_path = save_uploaded_file(
        filename,
        content,
    )

    pages = load_document(
        str(file_path)
    )

    chunks = split_document_pages(
        pages
    )

    if not chunks:
        raise ValueError(
            "No readable text was found in the document"
        )

    texts = [
        chunk["text"]
        for chunk in chunks
    ]

    metadatas = []

    for chunk in chunks:
        metadatas.append(
            {
                "filename": filename,
                "page": (
                    chunk["page"]
                    if chunk["page"] is not None
                    else 0
                ),
                "source_type": "file",
            }
        )

    vector_ids = add_chunks(
        user_id=user_id,
        chunks=texts,
        metadatas=metadatas,
    )

    document = {
        "user_id": user_id,
        "filename": filename,
        "file_type": Path(
            filename
        ).suffix.lower().replace(
            ".",
            "",
        ),
        "source_type": "file",
        "source_url": None,
        "stored_path": str(
            file_path
        ),
        "chunk_count": len(
            vector_ids
        ),
        "created_at": datetime.now(
            timezone.utc
        ),
    }

    result = documents_collection.insert_one(
        document
    )

    return {
        "id": str(result.inserted_id),
        "filename": filename,
        "file_type": document[
            "file_type"
        ],
        "source_type": "file",
        "source_url": None,
        "chunk_count": len(
            vector_ids
        ),
    }


def list_user_documents(
    user_id: str,
):
    documents = documents_collection.find(
        {
            "user_id": user_id
        }
    ).sort(
        "created_at",
        -1,
    )

    return [
        {
            "id": str(document["_id"]),
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
        }
        for document in documents
    ]


def delete_user_document(
    user_id: str,
    document_id: str,
):
    if not ObjectId.is_valid(
        document_id
    ):
        raise ValueError(
            "Invalid document ID"
        )

    document = documents_collection.find_one(
        {
            "_id": ObjectId(document_id),
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

    if source_type == "file":
        filename = document.get(
            "filename",
            "",
        )

        delete_source(
            user_id=user_id,
            source_type="file",
            source_value=filename,
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
            )

    stored_path = document.get(
        "stored_path"
    )

    if stored_path:
        file_path = Path(
            stored_path
        )

        if file_path.exists():
            file_path.unlink()

    documents_collection.delete_one(
        {
            "_id": ObjectId(document_id),
            "user_id": user_id,
        }
    )

    return document
    if not ObjectId.is_valid(
        document_id
    ):
        raise ValueError(
            "Invalid document ID"
        )

    document = documents_collection.find_one(
        {
            "_id": ObjectId(document_id),
            "user_id": user_id,
        }
    )

    if not document:
        raise ValueError(
            "Document not found"
        )

    stored_path = document.get(
        "stored_path"
    )

    if stored_path:
        file_path = Path(
            stored_path
        )

        if file_path.exists():
            file_path.unlink()

    documents_collection.delete_one(
        {
            "_id": ObjectId(document_id),
            "user_id": user_id,
        }
    )

    return document