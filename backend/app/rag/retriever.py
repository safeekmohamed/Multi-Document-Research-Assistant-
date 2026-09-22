import re
from functools import lru_cache

from sentence_transformers import CrossEncoder

from app.rag.vector_store import (
    get_user_chunks,
    search_semantic,
)


@lru_cache(maxsize=1)
def get_reranker():
    return CrossEncoder(
        "cross-encoder/ms-marco-MiniLM-L6-v2"
    )


def keyword_score(query: str, text: str) -> float:
    query_words = set(
        re.findall(
            r"\b[a-zA-Z0-9]+\b",
            query.lower(),
        )
    )

    text_words = re.findall(
        r"\b[a-zA-Z0-9]+\b",
        text.lower(),
    )

    if not query_words or not text_words:
        return 0.0

    matches = sum(
        1
        for word in text_words
        if word in query_words
    )

    return min(
        matches / max(len(query_words), 1),
        1.0,
    )


def detect_source_filter(
    query: str,
    metadatas: list[dict],
):
    query_lower = query.lower()

    filenames = set()

    for metadata in metadatas:
        filename = metadata.get("filename")

        if filename:
            filenames.add(filename)

   

    for filename in filenames:
        if filename.lower() in query_lower:
            return {
                "type": "filename",
                "filename": filename,
            }

   
    compare_words = [
        "compare",
        "comparison",
        "difference",
        "differences",
        "similarities",
        "similarity",
        "both",
        "between",
    ]

    if any(
        word in query_lower
        for word in compare_words
    ):
        return {
            "type": "both",
        }

    url_words = [
        "website",
        "webpage",
        "web page",
        "url",
        "site",
        "online",
    ]

    if any(
        word in query_lower
        for word in url_words
    ):
        return {
            "type": "url",
        }


    file_words = [
        "pdf",
        "file",
        "document",
        "uploaded file",
        "uploaded document",
        "my pdf",
        "my file",
        "my document",
    ]

    if any(
        word in query_lower
        for word in file_words
    ):
        return {
            "type": "file",
        }

    return None


def source_matches_filter(
    metadata: dict,
    source_filter: dict | None,
) -> bool:

    if not source_filter:
        return True

    filter_type = source_filter.get("type")


    if filter_type == "filename":
        return (
            metadata.get("filename")
            == source_filter.get("filename")
        )

    if filter_type == "both":
        return True

   

    if filter_type == "url":
        return (
            metadata.get("source_type")
            == "url"
        )


    if filter_type == "file":
        return (
            metadata.get("source_type")
            == "file"
        )

    return True


def rerank_candidates(
    query: str,
    candidates: list[dict],
) -> list[dict]:

    if not candidates:
        return []

    candidates = candidates[:20]

    try:
        reranker = get_reranker()

        pairs = [
            [
                query,
                item["content"],
            ]
            for item in candidates
        ]

        rerank_scores = reranker.predict(
            pairs
        )

        for index, score in enumerate(
            rerank_scores
        ):
            candidates[index][
                "rerank_score"
            ] = float(score)

        candidates.sort(
            key=lambda item: item.get(
                "rerank_score",
                item.get("score", 0.0),
            ),
            reverse=True,
        )

    except Exception as error:
        print(
            f"Reranker warning: {error}"
        )

        candidates.sort(
            key=lambda item: item.get(
                "score",
                0.0,
            ),
            reverse=True,
        )

    return candidates


def build_candidates(
    query,
    ids,
    documents,
    metadatas,
    distances,
    all_ids,
    all_documents,
    all_metadatas,
    source_filter,
):

    candidates = {}



    for index, chunk_id in enumerate(ids):

        text = documents[index]
        metadata = metadatas[index]

        if not source_matches_filter(
            metadata,
            source_filter,
        ):
            continue

        distance = distances[index]

        semantic_score = max(
            0.0,
            1.0 - float(distance),
        )

        lexical_score = keyword_score(
            query,
            text,
        )

        combined_score = (
            0.7 * semantic_score
            + 0.3 * lexical_score
        )

        candidates[chunk_id] = {
            "id": chunk_id,
            "content": text,
            "metadata": metadata,
            "score": combined_score,
        }


    for index, chunk_id in enumerate(
        all_ids
    ):

        text = all_documents[index]
        metadata = all_metadatas[index]

        if not source_matches_filter(
            metadata,
            source_filter,
        ):
            continue

        lexical_score = keyword_score(
            query,
            text,
        )

        if lexical_score <= 0:
            continue

        if chunk_id in candidates:

            candidates[chunk_id]["score"] = max(
                candidates[chunk_id]["score"],
                0.3 * lexical_score,
            )

        else:

            candidates[chunk_id] = {
                "id": chunk_id,
                "content": text,
                "metadata": metadata,
                "score": 0.3 * lexical_score,
            }

    ranked = sorted(
        candidates.values(),
        key=lambda item: item["score"],
        reverse=True,
    )

    return ranked


def hybrid_retrieve(
    user_id: str,
    query: str,
    limit: int = 8,
):

    semantic_result = search_semantic(
        user_id,
        query,
        limit=40,
    )

    ids = semantic_result.get(
        "ids",
        [[]],
    )[0]

    documents = semantic_result.get(
        "documents",
        [[]],
    )[0]

    metadatas = semantic_result.get(
        "metadatas",
        [[]],
    )[0]

    distances = semantic_result.get(
        "distances",
        [[]],
    )[0]

    

    all_chunks = get_user_chunks(
        user_id
    )

    all_ids = all_chunks.get(
        "ids",
        [],
    )

    all_documents = all_chunks.get(
        "documents",
        [],
    )

    all_metadatas = all_chunks.get(
        "metadatas",
        [],
    )

  

    source_filter = detect_source_filter(
        query,
        all_metadatas,
    )

 
    if (
        source_filter
        and source_filter.get("type")
        == "both"
    ):

        all_candidates = build_candidates(
            query=query,
            ids=ids,
            documents=documents,
            metadatas=metadatas,
            distances=distances,
            all_ids=all_ids,
            all_documents=all_documents,
            all_metadatas=all_metadatas,
            source_filter=None,
        )

        file_candidates = [
            item
            for item in all_candidates
            if item["metadata"].get(
                "source_type"
            )
            == "file"
        ]

        url_candidates = [
            item
            for item in all_candidates
            if item["metadata"].get(
                "source_type"
            )
            == "url"
        ]

        file_candidates = file_candidates[:12]

        url_candidates = url_candidates[:12]

        file_candidates = rerank_candidates(
            query,
            file_candidates,
        )

        url_candidates = rerank_candidates(
            query,
            url_candidates,
        )

        per_source = max(
            1,
            limit // 2,
        )

        selected_files = (
            file_candidates[:per_source]
        )

        selected_urls = (
            url_candidates[:per_source]
        )

        combined = []

        max_length = max(
            len(selected_files),
            len(selected_urls),
        )

        for index in range(
            max_length
        ):

            if index < len(
                selected_files
            ):
                combined.append(
                    selected_files[index]
                )

            if index < len(
                selected_urls
            ):
                combined.append(
                    selected_urls[index]
                )

        if len(combined) < limit:

            remaining = [
                item
                for item in (
                    file_candidates
                    + url_candidates
                )
                if item not in combined
            ]

            combined.extend(
                remaining[
                    : limit - len(combined)
                ]
            )

        return combined[:limit]

 
    ranked = build_candidates(
        query=query,
        ids=ids,
        documents=documents,
        metadatas=metadatas,
        distances=distances,
        all_ids=all_ids,
        all_documents=all_documents,
        all_metadatas=all_metadatas,
        source_filter=source_filter,
    )

    if not ranked:
        return []

    ranked = rerank_candidates(
        query,
        ranked[:30],
    )


    selected = []

    selected_ids = set()

    source_counts = {}


    for item in ranked:

        metadata = item.get(
            "metadata",
            {},
        )

        source_name = (
            metadata.get("filename")
            or metadata.get("url")
            or "unknown"
        )

        count = source_counts.get(
            source_name,
            0,
        )

        if count >= 2:
            continue

        selected.append(item)

        selected_ids.add(
            item["id"]
        )

        source_counts[
            source_name
        ] = count + 1

        if len(selected) >= limit:
            break

    if len(selected) < limit:

        for item in ranked:

            if item["id"] in selected_ids:
                continue

            selected.append(item)

            selected_ids.add(
                item["id"]
            )

            if len(selected) >= limit:
                break

    return selected[:limit]