from functools import lru_cache

from langchain_groq import ChatGroq

from app.core.config import settings


@lru_cache(maxsize=1)
def get_llm():
    if not settings.GROQ_API_KEY:
        raise RuntimeError(
            "GROQ_API_KEY is not configured in .env"
        )

    return ChatGroq(
        model=settings.GROQ_MODEL,
        api_key=settings.GROQ_API_KEY,
        temperature=0.2,
    )