from app.rag.chain import generate_answer
from app.rag.retriever import hybrid_retrieve


def build_context(
    results: list[dict],
) -> str:
    context_parts = []

    for index, result in enumerate(
        results,
        start=1,
    ):
        metadata = result.get(
            "metadata",
            {},
        )

        source_name = (
            metadata.get("filename")
            or metadata.get("url")
            or "Unknown source"
        )

        page = metadata.get("page")

        source_label = (
            f"{source_name}"
            if page is None
            else f"{source_name}, page {page}"
        )

        context_parts.append(
            f"[Source {index}: {source_label}]\n"
            f"{result['content']}"
        )

    return "\n\n".join(
        context_parts
    )


def create_citations(
    results: list[dict],
) -> list[dict]:
    """
    Create unique source cards.

    The same PDF or URL is shown only once.
    Page numbers are intentionally not returned.
    """

    citations = []

    seen_sources = set()

    for result in results:
        metadata = result.get(
            "metadata",
            {},
        )

        filename = metadata.get(
            "filename"
        )

        url = metadata.get(
            "url"
        )

        source_type = metadata.get(
            "source_type"
        )

        if source_type == "file" and filename:
            source_key = (
                "file",
                filename,
            )

            if source_key in seen_sources:
                continue

            seen_sources.add(
                source_key
            )

            citations.append(
                {
                    "source_number": len(citations) + 1,
                    "filename": filename,
                    "page": None,
                    "url": None,
                    "source_type": "file",
                }
            )


        elif source_type == "url" and url:
            source_key = (
                "url",
                url,
            )

            if source_key in seen_sources:
                continue

            seen_sources.add(
                source_key
            )

            citations.append(
                {
                    "source_number": len(citations) + 1,
                    "filename": metadata.get(
                        "title"
                    ) or metadata.get(
                        "filename"
                    ) or url,
                    "page": None,
                    "url": url,
                    "source_type": "url",
                }
            )

  

        else:
            source_name = (
                filename
                or url
                or "Unknown source"
            )

            source_key = (
                "unknown",
                source_name,
            )

            if source_key in seen_sources:
                continue

            seen_sources.add(
                source_key
            )

            citations.append(
                {
                    "source_number": len(citations) + 1,
                    "filename": (
                        filename
                        or source_name
                    ),
                    "page": None,
                    "url": url,
                    "source_type": source_type,
                }
            )

    return citations


def answer_question(
    user_id: str,
    question: str,
):
    
    results = hybrid_retrieve(
        user_id=user_id,
        query=question,
        limit=8,
    )

    if not results:
        return {
            "answer": (
                "I could not find relevant information "
                "in your uploaded sources."
            ),
            "citations": [],
        }

 
    context = build_context(
        results
    )

  
    answer = generate_answer(
        question=question,
        context=context,
    )

  
    citations = create_citations(
        results
    )

    return {
        "answer": answer,
        "citations": citations,
    }