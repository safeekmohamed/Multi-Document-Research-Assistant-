from datetime import datetime, timezone

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException

from app.auth.jwt import get_current_admin, get_current_user
from app.database.mongodb import feedback_collection
from app.schemas.feedback import FeedbackCreateRequest


router = APIRouter(
    prefix="/feedback",
    tags=["Feedback"],
)

admin_router = APIRouter(
    prefix="/admin/feedback",
    tags=["Admin feedback"],
)


@router.post("/")
def submit_feedback(
    data: FeedbackCreateRequest,
    current_user: dict = Depends(get_current_user),
):
    now = datetime.now(timezone.utc)
    result = feedback_collection.insert_one(
        {
            "user_id": str(current_user["_id"]),
            "user_name": current_user.get("name", ""),
            "user_email": current_user.get("email", ""),
            "category": data.category,
            "message": data.message,
            "created_at": now,
            "is_read": False,
            "read_at": None,
        }
    )
    return {
        "message": "Thank you. Your feedback has been submitted.",
        "feedback_id": str(result.inserted_id),
    }


def serialize_feedback(feedback: dict) -> dict:
    created_at = feedback.get("created_at")
    read_at = feedback.get("read_at")
    return {
        "id": str(feedback["_id"]),
        "user_name": feedback.get("user_name", ""),
        "user_email": feedback.get("user_email", ""),
        "category": feedback.get("category", "general"),
        "message": feedback.get("message", ""),
        "created_at": created_at.isoformat() if created_at else None,
        "is_read": bool(feedback.get("is_read", False)),
        "read_at": read_at.isoformat() if read_at else None,
    }


@admin_router.get(
    "",
    dependencies=[Depends(get_current_admin)],
)
def get_admin_feedback(
    unread_only: bool = False,
    limit: int = 100,
):
    query = {"is_read": False} if unread_only else {}
    bounded_limit = max(1, min(limit, 200))
    feedback = feedback_collection.find(query).sort(
        "created_at",
        -1,
    ).limit(bounded_limit)
    return {
        "feedback": [serialize_feedback(item) for item in feedback]
    }


@admin_router.get(
    "/notifications",
    dependencies=[Depends(get_current_admin)],
)
def get_admin_feedback_notifications():
    unread_count = feedback_collection.count_documents(
        {"is_read": False}
    )
    recent_feedback = feedback_collection.find(
        {"is_read": False}
    ).sort(
        "created_at",
        -1,
    ).limit(10)
    return {
        "unread_count": unread_count,
        "notifications": [
            serialize_feedback(item) for item in recent_feedback
        ],
    }


@admin_router.patch(
    "/{feedback_id}/read",
    dependencies=[Depends(get_current_admin)],
)
def mark_admin_feedback_read(
    feedback_id: str,
):
    if not ObjectId.is_valid(feedback_id):
        raise HTTPException(status_code=400, detail="Invalid feedback ID")

    feedback_id_object = ObjectId(feedback_id)
    feedback = feedback_collection.find_one({"_id": feedback_id_object})
    if not feedback:
        raise HTTPException(status_code=404, detail="Feedback not found")

    if not feedback.get("is_read", False):
        read_at = datetime.now(timezone.utc)
        feedback_collection.update_one(
            {"_id": feedback_id_object, "is_read": False},
            {"$set": {"is_read": True, "read_at": read_at}},
        )
        feedback["is_read"] = True
        feedback["read_at"] = read_at

    return {"feedback": serialize_feedback(feedback)}
