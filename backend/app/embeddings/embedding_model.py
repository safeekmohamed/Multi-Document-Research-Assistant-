import os
import logging
import time

from dotenv import load_dotenv
from app.core.model_cache import synchronized_lru_cache


load_dotenv()
logger = logging.getLogger(__name__)


@synchronized_lru_cache(maxsize=1)
def get_embedding_model():
    from sentence_transformers import SentenceTransformer

    model_name = os.getenv("EMBEDDING_MODEL")

    if not model_name:
        raise RuntimeError(
            "EMBEDDING_MODEL is not configured in .env"
        )

    started_at = time.perf_counter()
    logger.info("Loading embedding model: model=%s", model_name)
    try:
        model = SentenceTransformer(model_name)
    except Exception:
        logger.exception(
            "Embedding model initialization failed: model=%s elapsed_seconds=%.3f",
            model_name,
            time.perf_counter() - started_at,
        )
        raise
    logger.info(
        "Embedding model initialized: model=%s elapsed_seconds=%.3f",
        model_name,
        time.perf_counter() - started_at,
    )
    return model


def create_embeddings(
    texts: list[str],
) -> list[list[float]]:

    if not texts:
        return []

    model = get_embedding_model()

    embeddings = model.encode(
        texts,
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=False,
    )

    return embeddings.tolist()
