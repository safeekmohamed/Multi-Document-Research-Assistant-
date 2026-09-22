from datetime import datetime, timezone

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException

from app.auth.jwt import get_current_user
from app.database.mongodb import (
    conversations_collection,
    messages_collection,
)
from app.rag.rag_service import answer_question
from app.schemas.chat import ChatRequest


router = APIRouter(
    prefix="/chat",
    tags=["Research Chat"],
)


@router.post("/")
def chat(
    data: ChatRequest,
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["_id"])

    # ==================================================
    # Check whether this is an existing conversation
    # ==================================================

    conversation_id = data.conversation_id

    if conversation_id:

        if not ObjectId.is_valid(conversation_id):
            raise HTTPException(
                status_code=400,
                detail="Invalid conversation ID",
            )

        conversation = conversations_collection.find_one(
            {
                "_id": ObjectId(conversation_id),
                "user_id": user_id,
            }
        )

        if not conversation:
            raise HTTPException(
                status_code=404,
                detail="Conversation not found",
            )

    # ==================================================
    # No conversation ID means this is a NEW chat
    # ==================================================

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

    # ==================================================
    # Save user's question
    # ==================================================

    messages_collection.insert_one(
        {
            "conversation_id": conversation_id,
            "user_id": user_id,
            "role": "user",
            "content": data.question,
            "created_at": datetime.now(
                timezone.utc
            ),
        }
    )

    # ==================================================
    # Generate AI answer
    # ==================================================

    try:

        result = answer_question(
            user_id=user_id,
            question=data.question,
        )

    except Exception as error:

        raise HTTPException(
            status_code=500,
            detail=f"RAG processing failed: {error}",
        )

    # ==================================================
    # Save AI answer
    # ==================================================

    messages_collection.insert_one(
        {
            "conversation_id": conversation_id,
            "user_id": user_id,
            "role": "assistant",
            "content": result["answer"],
            "citations": result["citations"],
            "created_at": datetime.now(
                timezone.utc
            ),
        }
    )

    # ==================================================
    # Return conversation ID to frontend
    # ==================================================

    return {
        "conversation_id": conversation_id,
        "question": data.question,
        "answer": result["answer"],
        "citations": result["citations"],
    }