import logging
import time
from datetime import datetime, timezone

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException

from app.auth.jwt import get_current_user
from app.database.mongodb import (
    conversations_collection,
    documents_collection,
    messages_collection,
)
from app.rag.rag_service import answer_question
from app.rag.model_runtime import get_model_warmup_error
from app.schemas.chat import ChatRequest


router = APIRouter(
    prefix="/chat",
    tags=["Research Chat"],
)

logger = logging.getLogger(__name__)


@router.post("/")
def chat(
    data: ChatRequest,
    current_user: dict = Depends(
        get_current_user
    ),
):
    request_started_at = time.perf_counter()
    model_warmup_error = get_model_warmup_error()
    if model_warmup_error:
        logger.error("Rejecting chat because startup model warm-up failed.")
        raise HTTPException(status_code=503, detail=model_warmup_error)

    user_id = str(
        current_user["_id"]
    )

    attachment_ids = list(dict.fromkeys(data.attachment_document_ids))
    attachment_documents = []
    if attachment_ids:
        if any(not ObjectId.is_valid(value) for value in attachment_ids):
            raise HTTPException(
                status_code=400,
                detail="An attachment reference is invalid",
            )

        attachment_documents = list(
            documents_collection.find(
                {
                    "_id": {"$in": [ObjectId(value) for value in attachment_ids]},
                    "user_id": user_id,
                },
                {
                    "_id": 1,
                    "source_id": 1,
                    "filename": 1,
                    "source_type": 1,
                    "source_url": 1,
                    "document_type": 1,
                },
            )
        )
        if len(attachment_documents) != len(attachment_ids):
            raise HTTPException(
                status_code=404,
                detail="One or more attachments are unavailable",
            )

    attached_sources = [
        {
            "source_id": document.get("source_id"),
            "filename": document.get("filename"),
            "source_type": document.get("source_type", "file"),
            "url": document.get("source_url"),
            "document_type": document.get("document_type"),
        }
        for document in attachment_documents
    ]
    attachment_summaries = [
        {
            "document_id": str(document["_id"]),
            "filename": document.get("filename") or "Document",
            "source_type": document.get("source_type", "file"),
        }
        for document in attachment_documents
    ]

    conversation_id = data.conversation_id

    if conversation_id:

        if not ObjectId.is_valid(
            conversation_id
        ):
            raise HTTPException(
                status_code=400,
                detail="Invalid conversation ID",
            )

        conversation = conversations_collection.find_one(
            {
                "_id": ObjectId(
                    conversation_id
                ),
                "user_id": user_id,
            }
        )

        if not conversation:
            raise HTTPException(
                status_code=404,
                detail="Conversation not found",
            )

    else:

        result = conversations_collection.insert_one(
            {
                "user_id": user_id,
                "title": data.question[:80],
                "created_at": datetime.now(
                    timezone.utc
                ),
            }
        )

        conversation_id = str(
            result.inserted_id
        )

    previous_messages = list(
        messages_collection.find(
            {
                "conversation_id": conversation_id,
                "user_id": user_id,
            },
            {
                "_id": 0,
                "role": 1,
                "content": 1,
                "citations": 1,
                "attachments": 1,
                "created_at": 1,
            },
        )
        .sort(
            "created_at",
            -1,
        )
        .limit(20)
    )
    previous_messages.reverse()

    messages_collection.insert_one(
        {
            "conversation_id": conversation_id,
            "user_id": user_id,
            "role": "user",
            "content": data.question,
            "attachments": attachment_summaries,
            "created_at": datetime.now(
                timezone.utc
            ),
        }
    )

    try:

        result = answer_question(
            user_id=user_id,
            question=data.question,
            conversation_history=previous_messages,
            attached_sources=attached_sources,
        )

    except Exception as error:
        logger.exception(
            "Chat request failed after %.3f seconds",
            time.perf_counter() - request_started_at,
        )

        raise HTTPException(
            status_code=500,
            detail=(
                f"RAG processing failed: "
                f"{error}"
            ),
        )

    messages_collection.insert_one(
        {
            "conversation_id": conversation_id,
            "user_id": user_id,
            "role": "assistant",
            "content": result["answer"],
            "citations": result["citations"],
            "sources": result.get("sources", result["citations"]),
            "searched_files": result.get("searched_files", []),
            "source_attribution_version": 1,
            "created_at": datetime.now(
                timezone.utc
            ),
        }
    )

    logger.info(
        "Chat request completed: total_seconds=%.3f citation_count=%d",
        time.perf_counter() - request_started_at,
        len(result.get("citations", [])),
    )

    return {
        "conversation_id": conversation_id,
        "question": data.question,
        "answer": result["answer"],
        "citations": result["citations"],
        "sources": result.get("sources", result["citations"]),
        "searched_files": result.get("searched_files", []),
        "source_attribution_version": 1,
        "attachments": attachment_summaries,
    }
