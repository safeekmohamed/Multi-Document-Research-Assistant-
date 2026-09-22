from functools import lru_cache
from uuid import uuid4

import chromadb

from app.core.config import settings
from app.embeddings.embedding_model import (
    create_embeddings,
)


@lru_cache(maxsize=1)
def get_chroma_client():
    return chromadb.PersistentClient(
        path=settings.CHROMA_PATH
    )


@lru_cache(maxsize=1)
def get_chroma_collection():
    client = get_chroma_client()

    return client.get_or_create_collection(
        name="research_chunks",
        metadata={
            "hnsw:space": "cosine"
        },
    )


def add_chunks(
    user_id: str,
    chunks: list[str],
    metadatas: list[dict],
):
    if not chunks:
        return []

    collection = get_chroma_collection()

    embeddings = create_embeddings(chunks)

    ids = [
        str(uuid4())
        for _ in chunks
    ]

    final_metadatas = []

    for metadata in metadatas:
        final_metadata = {
            "user_id": user_id,
            **metadata,
        }

        final_metadatas.append(
            final_metadata
        )

    collection.add(
        ids=ids,
        documents=chunks,
        embeddings=embeddings,
        metadatas=final_metadatas,
    )

    return ids


def search_semantic(
    user_id: str,
    query: str,
    limit: int = 20,
):
    collection = get_chroma_collection()

    query_embedding = create_embeddings(
        [query]
    )[0]

    result = collection.query(
        query_embeddings=[query_embedding],
        n_results=limit,
        where={
            "user_id": user_id
        },
        include=[
            "documents",
            "metadatas",
            "distances",
        ],
    )

    return result


def get_user_chunks(user_id: str):
    collection = get_chroma_collection()

    return collection.get(
        where={
            "user_id": user_id
        },
        include=[
            "documents",
            "metadatas",
        ],
    )
def delete_source(
    user_id: str,
    source_type: str,
    source_value: str,
):
    collection = get_chroma_collection()

    if source_type == "file":
        where = {
            "$and": [
                {"user_id": user_id},
                {"source_type": "file"},
                {"filename": source_value},
            ]
        }

    elif source_type == "url":
        where = {
            "$and": [
                {"user_id": user_id},
                {"source_type": "url"},
                {"url": source_value},
            ]
        }

    else:
        raise ValueError(
            "Unsupported source type"
        )

    collection.delete(
        where=where
    )