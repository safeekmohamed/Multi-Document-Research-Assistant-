from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi

from app.core.config import settings
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


@asynccontextmanager
async def lifespan(
    application: FastAPI,
):
    try:
        initialize_database()
        print("Database initialization complete.")
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

    # Use OpenAPI 3.0 format for better Swagger file-upload support.
    openapi_schema["openapi"] = "3.0.3"

    def fix_file_schemas(schema):
        if isinstance(schema, dict):
            if (
                schema.get("type") == "string"
                and schema.get("contentMediaType")
                == "application/octet-stream"
            ):
                schema.pop("contentMediaType", None)
                schema["format"] = "binary"

            for value in schema.values():
                fix_file_schemas(value)

        elif isinstance(schema, list):
            for item in schema:
                fix_file_schemas(item)

    fix_file_schemas(openapi_schema)

    app.openapi_schema = openapi_schema

    return app.openapi_schema


app.openapi = custom_openapi


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.FRONTEND_ORIGIN
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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


@app.get("/")
def root():
    return {
        "message": (
            "Multi-Document Research Assistant "
            "API is running"
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