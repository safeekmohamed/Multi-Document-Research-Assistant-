import logging
import os
import time
from functools import lru_cache
from uuid import uuid4

import chromadb
from dotenv import load_dotenv

from app.embeddings.embedding_model import create_embeddings


load_dotenv()

logger = logging.getLogger(__name__)


COLLECTION_NAME = "research_chunks"
EMBEDDING_BATCH_SIZE = 8


def _create_query_embedding(query: str) -> list[float]:
    started_at = time.perf_counter()
    embedding = create_embeddings([query])[0]
    logger.info(
        "Query embedding completed: elapsed_seconds=%.3f",
        time.perf_counter() - started_at,
    )
    return embedding


@lru_cache(maxsize=1)
def get_chroma_client():

    return chromadb.PersistentClient(
        path=os.getenv(
            "CHROMA_PATH",
            "./chroma_data",
        )
    )


@lru_cache(maxsize=1)
def get_chroma_collection():

    client = get_chroma_client()

    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={
            "hnsw:space": "cosine"
        },
    )


def add_chunks(
    user_id: str,
    chunks: list[str],
    metadatas: list[dict],
) -> list[str]:

    if not chunks:
        return []

    if len(chunks) != len(metadatas):
        raise ValueError(
            "Chunks and metadata length must match"
        )

    collection = get_chroma_collection()

    ids = [
        str(uuid4())
        for _ in chunks
    ]

    added_ids = []
    try:
        for start in range(0, len(chunks), EMBEDDING_BATCH_SIZE):
            end = start + EMBEDDING_BATCH_SIZE
            batch_chunks = chunks[start:end]
            batch_ids = ids[start:end]
            batch_metadatas = [
                {"user_id": user_id, **metadata}
                for metadata in metadatas[start:end]
            ]
            batch_embeddings = create_embeddings(
                batch_chunks,
                batch_size=EMBEDDING_BATCH_SIZE,
            )
            # Track IDs before adding so a failed Chroma write can clean up
            # any IDs from a partially completed batch as well.
            added_ids.extend(batch_ids)
            collection.add(
                ids=batch_ids,
                documents=batch_chunks,
                embeddings=batch_embeddings,
                metadatas=batch_metadatas,
            )
            del batch_embeddings
    except Exception:
        if added_ids:
            try:
                collection.delete(ids=added_ids)
            except Exception:
                logger.exception("Failed to roll back a partial chunk batch")
        raise

    return ids


def search_semantic(
    user_id: str,
    query: str,
    limit: int | None = 30,
    file_type: str | None = None,
    where_filter: dict | None = None,
):

    collection = get_chroma_collection()

    query_embedding = _create_query_embedding(query)

    where_conditions = [
        {
            "user_id": user_id
        }
    ]

    if file_type:

        where_conditions.append(
            {
                "file_type": (
                    file_type
                    .lower()
                    .lstrip(".")
                )
            }
        )

    if where_filter:
        where_conditions.append(
            where_filter
        )

    if len(where_conditions) == 1:

        where = where_conditions[0]

    else:

        where = {
            "$and": where_conditions
        }

    if limit is None:
        count_started_at = time.perf_counter()
        result_limit = len(collection.get(where=where, include=[]).get("ids", []))
        logger.info(
            "Chroma filtered chunk count completed: elapsed_seconds=%.3f",
            time.perf_counter() - count_started_at,
        )
    else:
        result_limit = limit
    if result_limit == 0:
        return {
            "ids": [[]],
            "documents": [[]],
            "metadatas": [[]],
            "distances": [[]],
        }

    started_at = time.perf_counter()
    result = collection.query(
        query_embeddings=[query_embedding],
        n_results=result_limit,
        where=where,
        include=["documents", "metadatas", "distances"],
    )
    logger.info(
        "Chroma semantic search completed: requested_chunks=%d elapsed_seconds=%.3f",
        result_limit,
        time.perf_counter() - started_at,
    )
    return result


def get_all_user_chunks(
    user_id: str,
    file_type: str | None = None,
    source_filters: list[dict] | None = None,
):
    """
    Get stored chunks belonging to the current user, optionally restricted
    to the requested file type and source allowlist.
    """

    collection = get_chroma_collection()

    where_conditions = [
        {
            "user_id": user_id
        }
    ]

    if file_type:

        where_conditions.append(
            {
                "file_type": (
                    file_type
                    .lower()
                    .lstrip(".")
                )
            }
        )

    if source_filters:
        source_conditions = [
            item for item in source_filters if isinstance(item, dict) and item
        ]
        if not source_conditions:
            return {"ids": [], "documents": [], "metadatas": []}
        where_conditions.append(
            source_conditions[0]
            if len(source_conditions) == 1
            else {"$or": source_conditions}
        )

    if len(where_conditions) == 1:

        where = where_conditions[0]

    else:

        where = {
            "$and": where_conditions
        }

    return collection.get(
        where=where,
        include=[
            "documents",
            "metadatas",
        ],
    )


def delete_source(
    user_id: str,
    source_type: str,
    source_value: str,
    source_id: str | None = None,
):

    collection = get_chroma_collection()

    conditions = [
        {
            "user_id": user_id
        },
        {
            "source_type": source_type
        },
    ]

    if source_id:

        conditions.append(
            {
                "source_id": source_id
            }
        )

    elif source_type == "file":

        conditions.append(
            {
                "filename": source_value
            }
        )

    elif source_type == "url":

        conditions.append(
            {
                "url": source_value
            }
        )

    else:

        raise ValueError(
            "Unsupported source type"
        )

    if len(conditions) == 1:

        where = conditions[0]

    else:

        where = {
            "$and": conditions
        }

    collection.delete(
        where=where
    )


def search_semantic_by_sources(
    user_id: str,
    query: str,
    source_filters: list[dict],
    limit: int | None = 30,
):
    """Search each explicitly named source independently with one query embedding."""
    if not source_filters:
        return {
            "ids": [],
            "documents": [],
            "metadatas": [],
            "distances": [],
        }

    collection = get_chroma_collection()
    query_embedding = _create_query_embedding(query)
    combined = {
        "ids": [],
        "documents": [],
        "metadatas": [],
        "distances": [],
    }
    seen_ids = set()
    for source_filter in source_filters:
        where = {
            "$and": [
                {"user_id": user_id},
                source_filter,
            ]
        }
        count_started_at = time.perf_counter()
        source_count = len(collection.get(where=where, include=[]).get("ids", []))
        logger.info(
            "Chroma source chunk count completed: elapsed_seconds=%.3f",
            time.perf_counter() - count_started_at,
        )
        if source_count == 0:
            continue
        per_source_limit = (
            source_count
            if limit is None
            else min(limit, source_count)
        )
        query_started_at = time.perf_counter()
        result = collection.query(
            query_embeddings=[query_embedding],
            n_results=per_source_limit,
            where=where,
            include=[
                "documents",
                "metadatas",
                "distances",
            ],
        )
        logger.debug(
            "Chroma source search completed: elapsed_seconds=%.3f",
            time.perf_counter() - query_started_at,
        )

        rows = {}
        for key in combined:
            values = result.get(key, [[]])
            rows[key] = (
                values[0]
                if values and isinstance(values[0], list)
                else values
            )

        for index, chunk_id in enumerate(
            rows["ids"]
        ):
            if chunk_id in seen_ids:
                continue
            seen_ids.add(chunk_id)
            for key in combined:
                values = rows[key]
                if index < len(values):
                    combined[key].append(
                        values[index]
                    )

    return combined
