from datetime import datetime, timezone

from bson import ObjectId

from app.auth.password import (
    hash_password,
    verify_password,
)
from app.database.mongodb import users_collection


def find_user_by_email(email: str):
    return users_collection.find_one(
        {"email": email.lower()}
    )


def create_user(
    name: str,
    email: str,
    password: str,
):
    user = {
        "name": name,
        "email": email.lower(),
        "password_hash": hash_password(password),
        "is_verified": False,
        "created_at": datetime.now(timezone.utc),
    }

    result = users_collection.insert_one(user)

    return result.inserted_id


def verify_user(email: str):
    users_collection.update_one(
        {"email": email.lower()},
        {
            "$set": {
                "is_verified": True,
                "verified_at": datetime.now(timezone.utc),
            }
        },
    )


def authenticate_user(
    email: str,
    password: str,
):
    user = find_user_by_email(email)

    if not user:
        return None

    if not user.get("is_verified", False):
        return None

    if not verify_password(
        password,
        user.get("password_hash", ""),
    ):
        return None

    return user


def get_user_by_id(user_id: str):
    if not ObjectId.is_valid(user_id):
        return None

    return users_collection.find_one(
        {"_id": ObjectId(user_id)}
    )