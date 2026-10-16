import logging
import time

from app.embeddings.embedding_model import get_embedding_model


logger = logging.getLogger(__name__)
_warmup_error: str | None = None


def get_model_warmup_error() -> str | None:
    return _warmup_error


def warmup_rag_models() -> None:
    """Warm only embeddings; defer the larger reranker to first use."""
    global _warmup_error
    _warmup_error = None
    for component, loader in (("embedding", get_embedding_model),):
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
