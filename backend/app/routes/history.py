from bson import ObjectId
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
)

from app.auth.jwt import (
    get_current_user,
)
from app.database.mongodb import (
    conversations_collection,
    messages_collection,
)


router = APIRouter(
    prefix="/history",
    tags=["Chat History"],
)


@router.get("/conversations")
def get_conversations(
    current_user: dict = Depends(
        get_current_user
    ),
):
    user_id = str(
        current_user["_id"]
    )

    conversations = (
        conversations_collection.find(
            {
                "user_id": user_id
            }
        )
        .sort(
            "created_at",
            -1,
        )
    )

    return {
        "conversations": [
            {
                "id": str(
                    conversation["_id"]
                ),
                "title": conversation.get(
                    "title",
                    "New Conversation",
                ),
                "created_at": (
                    conversation[
                        "created_at"
                    ].isoformat()
                ),
            }
            for conversation in conversations
        ]
    }


@router.get(
    "/conversations/{conversation_id}"
)
def get_conversation_messages(
    conversation_id: str,
    current_user: dict = Depends(
        get_current_user
    ),
):
    if not ObjectId.is_valid(
        conversation_id
    ):
        raise HTTPException(
            status_code=400,
            detail="Invalid conversation ID",
        )

    user_id = str(
        current_user["_id"]
    )

    conversation = (
        conversations_collection.find_one(
            {
                "_id": ObjectId(
                    conversation_id
                ),
                "user_id": user_id,
            }
        )
    )

    if not conversation:
        raise HTTPException(
            status_code=404,
            detail="Conversation not found",
        )

    messages = (
        messages_collection.find(
            {
                "conversation_id": conversation_id,
                "user_id": user_id,
            }
        )
        .sort(
            "created_at",
            1,
        )
    )

    return {
        "conversation": {
            "id": conversation_id,
            "title": conversation.get(
                "title",
                "New Conversation",
            ),
        },
        "messages": [
            {
                "id": str(
                    message["_id"]
                ),
                "role": message.get(
                    "role",
                    "",
                ),
                "content": message.get(
                    "content",
                    "",
                ),
                "citations": message.get(
                    "citations",
                    [],
                ),
                "sources": message.get(
                    "sources",
                    message.get("citations", []),
                ),
                "searched_files": message.get(
                    "searched_files",
                    [],
                ),
                "source_attribution_version": message.get(
                    "source_attribution_version",
                ),
                "attachments": message.get(
                    "attachments",
                    [],
                ),
                "created_at": (
                    message[
                        "created_at"
                    ].isoformat()
                ),
            }
            for message in messages
        ],
    }


@router.delete(
    "/conversations/{conversation_id}"
)
def delete_conversation(
    conversation_id: str,
    current_user: dict = Depends(
        get_current_user
    ),
):
    if not ObjectId.is_valid(
        conversation_id
    ):
        raise HTTPException(
            status_code=400,
            detail="Invalid conversation ID",
        )

    user_id = str(
        current_user["_id"]
    )

    result = conversations_collection.delete_one(
        {
            "_id": ObjectId(conversation_id),
            "user_id": user_id,
        }
    )

    if result.deleted_count == 0:
        raise HTTPException(
            status_code=404,
            detail="Conversation not found",
        )

    messages_collection.delete_many(
        {
            "conversation_id": conversation_id,
            "user_id": user_id,
        }
    )

    return {
        "message": "Conversation deleted successfully",
        "conversation_id": conversation_id,
    }
