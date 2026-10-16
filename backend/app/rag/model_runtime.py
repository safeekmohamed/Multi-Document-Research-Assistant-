import logging
import time

from app.embeddings.embedding_model import get_embedding_model
from app.rag.retriever import get_reranker


logger = logging.getLogger(__name__)
_warmup_error: str | None = None


def get_model_warmup_error() -> str | None:
    return _warmup_error


def warmup_rag_models() -> None:
    """Load cached Hugging Face models before the first chat request."""
    global _warmup_error
    _warmup_error = None
    for component, loader in (
        ("embedding", get_embedding_model),
        ("reranker", get_reranker),
    ):
        started_at = time.perf_counter()
        try:
            loader()
        except Exception as error:
            _warmup_error = (
                f"The {component} model did not initialize during backend startup. "
                "Check the backend log and model cache/network, then restart the backend."
            )
            logger.exception(
                "RAG model warm-up failed: component=%s elapsed_seconds=%.3f",
                component,
                time.perf_counter() - started_at,
            )
            raise RuntimeError(_warmup_error) from error
        logger.info(
            "RAG model warm-up completed: component=%s elapsed_seconds=%.3f",
            component,
            time.perf_counter() - started_at,
        )
