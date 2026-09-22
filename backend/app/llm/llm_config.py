from app.core.config import settings


def get_llm_config() -> dict:
    return {
        "model": settings.GROQ_MODEL,
        "api_key": settings.GROQ_API_KEY,
    }