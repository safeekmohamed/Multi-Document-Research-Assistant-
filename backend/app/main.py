import logging
import os
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv

BACKEND_ENV_PATH = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(dotenv_path=BACKEND_ENV_PATH, override=False)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi

from app.database.mongodb import (
    check_mongodb_connection,
    initialize_database,
)

from app.routes.auth import (
    router as auth_router,
)

from app.routes.chat import (
    router as chat_router,
)

from app.routes.documents import (
    router as documents_router,
)

from app.routes.history import (
    router as history_router,
)

from app.routes.urls import (
    router as urls_router,
)

from app.routes.users import (
    router as users_router,
)

from app.routes.admin import (
    router as admin_router,
)

from app.routes.feedback import (
    router as feedback_router,
    admin_router as admin_feedback_router,
)

from app.llm.llm_model import llm_configuration_warning
from app.rag.model_runtime import warmup_rag_models

logger = logging.getLogger(__name__)
PRODUCTION_FRONTEND_ORIGIN = "https://multi-document-research-assistant.vercel.app"


def configured_frontend_origins(frontend_origin: str) -> list[str]:
    origin = frontend_origin.rstrip("/")
    origins = [PRODUCTION_FRONTEND_ORIGIN]
    if not origin:
        return origins

    if origin not in origins:
        origins.append(origin)
    parsed_origin = urlsplit(origin)
    hostname = (parsed_origin.hostname or "").lower()
    if hostname not in {"localhost", "127.0.0.1"}:
        return origins

    alternate_hostname = (
        "127.0.0.1"
        if hostname == "localhost"
        else "localhost"
    )
    port = f":{parsed_origin.port}" if parsed_origin.port else ""
    alternate_origin = (
        f"{parsed_origin.scheme}://{alternate_hostname}{port}"
    )
    if alternate_origin not in origins:
        origins.append(alternate_origin)
    return origins


@asynccontextmanager
async def lifespan(
    application: FastAPI,
):

    llm_status = llm_configuration_warning()
    if llm_status and llm_status.startswith("Configured"):
        logger.info(llm_status)
    else:
        logger.warning(llm_status)

    if os.getenv("RAG_MODEL_WARMUP_ON_STARTUP", "false").strip().lower() in {"1", "true", "yes", "on"}:
        try:
            await asyncio.to_thread(warmup_rag_models)
        except Exception:
            logger.exception(
                "RAG model warm-up failed; the first chat request may need to initialize the model."
            )

    try:

        initialize_database()

        print(
            "Database initialization complete."
        )

    except Exception as error:

        print(
            f"Database initialization warning: {error}"
        )

    yield

app = FastAPI(
    title="Multi-Document Research Assistant",
    description=(
        "AI platform for researching "
        "multiple documents and websites."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

def custom_openapi():

    if app.openapi_schema:

        return app.openapi_schema

    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )

    openapi_schema[
        "openapi"
    ] = "3.0.3"

    def fix_file_schemas(
        schema
    ):

        if isinstance(
            schema,
            dict,
        ):

            if (
                schema.get(
                    "type"
                )
                == "string"
                and schema.get(
                    "contentMediaType"
                )
                == "application/octet-stream"
            ):

                schema.pop(
                    "contentMediaType",
                    None,
                )

                schema[
                    "format"
                ] = "binary"

            for value in schema.values():

                fix_file_schemas(
                    value
                )

        elif isinstance(
            schema,
            list,
        ):

            for item in schema:

                fix_file_schemas(
                    item
                )

    fix_file_schemas(
        openapi_schema
    )

    app.openapi_schema = (
        openapi_schema
    )

    return app.openapi_schema

app.openapi = custom_openapi

app.add_middleware(
    CORSMiddleware,
    allow_origins=configured_frontend_origins(
        os.getenv("FRONTEND_ORIGIN", "")
    ),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=[
        "Content-Disposition",
        "X-Document-File-Type",
        "X-Document-Filename",
    ],
)

app.include_router(
    auth_router
)

app.include_router(
    users_router
)

app.include_router(
    documents_router
)

app.include_router(
    urls_router
)

app.include_router(
    chat_router
)

app.include_router(
    history_router
)

app.include_router(
    admin_router
)

app.include_router(
    feedback_router
)

app.include_router(
    admin_feedback_router
)

@app.get("/")
def root():

    return {
        "message": (
            "Multi-Document Research "
            "Assistant API is running"
        )
    }

@app.get("/health")
def health():

    mongodb_status = (
        "connected"
        if check_mongodb_connection()
        else "disconnected"
    )

    return {
        "status": "healthy",
        "mongodb": mongodb_status,
    }
