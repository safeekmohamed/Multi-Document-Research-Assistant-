import os
from pathlib import Path

import requests
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq
from langchain_ollama import ChatOllama
from app.core.model_cache import synchronized_lru_cache


BACKEND_ENV_PATH = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(dotenv_path=BACKEND_ENV_PATH, override=False)

GEMINI_MODEL = "gemini-3.8-flash"
DEFAULT_LLM_PROVIDER = "ollama"
DEFAULT_OLLAMA_MODEL = "llama3.2:latest"
DEFAULT_OLLAMA_BASE_URL = "http://127.0.0.1:11434"
DEFAULT_OLLAMA_REQUEST_TIMEOUT_SECONDS = 180.0
DEFAULT_OLLAMA_KEEP_ALIVE = "30m"


def _status_code(error: Exception) -> int | None:
    for candidate in (
        getattr(error, "code", None),
        getattr(error, "status_code", None),
        getattr(getattr(error, "response", None), "status_code", None),
    ):
        if isinstance(candidate, int):
            return candidate

        value = getattr(candidate, "value", None)
        if isinstance(value, int):
            return value

    return None


def gemini_error_message(error: Exception) -> str | None:
    detail = str(error).strip()
    normalized_detail = detail.casefold()
    status_code = _status_code(error)

    if (
        ("model" in normalized_detail)
        and any(
            phrase in normalized_detail
            for phrase in (
                "not found",
                "not supported",
                "unsupported",
                "not available",
                "does not exist",
            )
        )
    ):
        category = (
            f"Gemini model {GEMINI_MODEL!r} is unavailable or unsupported "
            "for this API project."
        )
    elif (
        status_code in (401, 403)
        or "api_key_invalid" in normalized_detail
        or "invalid api key" in normalized_detail
        or "api key not valid" in normalized_detail
    ):
        category = (
            "Gemini API authentication or permission failed. "
            "Check that GEMINI_API_KEY is valid and has Gemini API access."
        )
    elif status_code == 429 or "resource_exhausted" in normalized_detail:
        if "quota" in normalized_detail:
            category = (
                "Gemini API quota is exhausted. Check this project's "
                "quota and reset time in Google AI Studio."
            )
        else:
            category = (
                "Gemini rate limit was reached. Check this project's RPM, "
                "TPM, and RPD limits in Google AI Studio before retrying."
            )
    elif status_code == 413 or (
        status_code == 400
        and any(
            phrase in normalized_detail
            for phrase in (
                "context window",
                "input token",
                "token count",
                "prompt is too long",
                "too many tokens",
                "maximum number of tokens",
            )
        )
    ):
        category = (
            "Gemini rejected the request because it exceeds the model's "
            "context window. The Gemini integration did not truncate the "
            "request."
        )
    else:
        return None

    if detail:
        return f"{category} Provider error: {detail}"
    return category


def get_gemini_api_key() -> str:
    """Read the configured key without logging or exposing it to callers."""
    return os.getenv("GEMINI_API_KEY", "").strip()


def is_gemini_configured() -> bool:
    return bool(get_gemini_api_key())


def get_llm_provider() -> str:
    return os.getenv("LLM_PROVIDER", DEFAULT_LLM_PROVIDER).strip().lower()


def get_ollama_model() -> str:
    return os.getenv("OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL).strip()


def get_ollama_base_url() -> str:
    return os.getenv("OLLAMA_BASE_URL", DEFAULT_OLLAMA_BASE_URL).strip().rstrip("/")


def get_ollama_request_timeout() -> float:
    raw_timeout = os.getenv(
        "OLLAMA_REQUEST_TIMEOUT_SECONDS",
        str(DEFAULT_OLLAMA_REQUEST_TIMEOUT_SECONDS),
    ).strip()
    try:
        timeout = float(raw_timeout)
    except ValueError as error:
        raise RuntimeError("OLLAMA_REQUEST_TIMEOUT_SECONDS must be a positive number.") from error
    if timeout <= 0:
        raise RuntimeError("OLLAMA_REQUEST_TIMEOUT_SECONDS must be a positive number.")
    return timeout


def get_ollama_keep_alive() -> str:
    return os.getenv("OLLAMA_KEEP_ALIVE", DEFAULT_OLLAMA_KEEP_ALIVE).strip()


def validate_ollama_configuration() -> None:
    base_url = get_ollama_base_url()
    model_name = get_ollama_model()
    if not model_name:
        raise RuntimeError("OLLAMA_MODEL is empty. Set it to an installed Ollama model in backend/.env.")
    try:
        response = requests.get(f"{base_url}/api/tags", timeout=3)
        response.raise_for_status()
        payload = response.json()
        models = payload.get("models", [])
        installed_names = {
            str(model.get("name") or model.get("model") or "")
            for model in models
            if isinstance(model, dict)
        }
    except (requests.RequestException, ValueError, AttributeError) as error:
        raise RuntimeError(
            f"Ollama is not reachable at {base_url}. Start the Ollama service and verify its local API, then retry."
        ) from error

    model_matches = model_name in installed_names
    if ":" not in model_name:
        model_matches = model_matches or f"{model_name}:latest" in installed_names
    if not model_matches:
        raise RuntimeError(
            f"Ollama model {model_name!r} is not installed at {base_url}. "
            f"After choosing the intended model, install it with: ollama pull {model_name}"
        )


def validate_llm_configuration() -> str:
    provider = get_llm_provider()
    if provider == "ollama":
        validate_ollama_configuration()
    elif provider == "gemini":
        if not is_gemini_configured():
            raise RuntimeError("GEMINI_API_KEY is not configured. Set it in backend/.env.")
    elif provider == "groq":
        if not os.getenv("GROQ_API_KEY", "").strip():
            raise RuntimeError("GROQ_API_KEY is not configured. Set it in backend/.env.")
    else:
        raise RuntimeError(
            f"Unsupported LLM_PROVIDER {provider!r}. Choose one of: ollama, gemini, groq."
        )
    return provider


def llm_configuration_warning() -> str | None:
    try:
        provider = validate_llm_configuration()
    except RuntimeError as error:
        return str(error)
    model = {
        "ollama": get_ollama_model(),
        "gemini": GEMINI_MODEL,
        "groq": os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile").strip(),
    }[provider]
    return f"Configured LLM provider: {provider}; model: {model}."


def llm_error_message(error: Exception) -> str | None:
    provider = get_llm_provider()
    detail = str(error).strip()
    normalized = detail.casefold()
    if provider == "gemini":
        return gemini_error_message(error)
    if provider == "ollama":
        if any(term in normalized for term in ("connection refused", "connecterror", "failed to connect", "connection error")):
            return f"Ollama could not be reached at {get_ollama_base_url()}. Verify that the service is running."
        if "timeout" in normalized or "timed out" in normalized:
            return (
                f"Ollama did not finish the request within "
                f"{get_ollama_request_timeout():g} seconds. Check local model load and generation time."
            )
        if "not found" in normalized and "model" in normalized:
            return f"Ollama model {get_ollama_model()!r} is unavailable. Install it with: ollama pull {get_ollama_model()}"
        return f"Ollama request failed for model {get_ollama_model()!r}: {detail}" if detail else "Ollama request failed."
    if provider == "groq" and _status_code(error) in (401, 403):
        return "Groq API authentication or permission failed. Check GROQ_API_KEY and project access."
    return None


@synchronized_lru_cache(maxsize=1)
def get_llm():
    provider = validate_llm_configuration()
    if provider == "ollama":
        return ChatOllama(
            model=get_ollama_model(),
            base_url=get_ollama_base_url(),
            temperature=0.2,
            streaming=False,
            keep_alive=get_ollama_keep_alive(),
            sync_client_kwargs={"timeout": get_ollama_request_timeout()},
            async_client_kwargs={"timeout": get_ollama_request_timeout()},
        )
    if provider == "gemini":
        return ChatGoogleGenerativeAI(
            model=GEMINI_MODEL,
            api_key=get_gemini_api_key(),
            temperature=0.2,
            streaming=False,
        )
    return ChatGroq(
        model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile").strip(),
        api_key=os.getenv("GROQ_API_KEY", "").strip(),
        temperature=0.2,
    )
