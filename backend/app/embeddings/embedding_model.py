from functools import lru_cache

from sentence_transformers import SentenceTransformer

from app.core.config import settings


@lru_cache(maxsize=1)
def get_embedding_model():
    return SentenceTransformer(
        settings.EMBEDDING_MODEL
    )


def create_embeddings(
    texts: list[str],
) -> list[list[float]]:
    model = get_embedding_model()

    embeddings = model.encode(
        texts,
        normalize_embeddings=True,
    )

    return embeddings.tolist()