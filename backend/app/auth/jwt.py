from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt.exceptions import InvalidTokenError

from app.core.config import settings
from app.database.mongodb import users_collection


security = HTTPBearer()


def create_access_token(
    user_id: str,
    email: str,
) -> str:
    expires_at = (
        datetime.now(timezone.utc)
        + timedelta(
            minutes=settings.JWT_EXPIRE_MINUTES
        )
    )

    payload = {
        "user_id": user_id,
        "email": email,
        "exp": expires_at,
    }

    return jwt.encode(
        payload,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


def decode_access_token(token: str) -> dict:
    try:
        return jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
    except InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(
        security
    ),
):
    payload = decode_access_token(
        credentials.credentials
    )

    user_id = payload.get("user_id")

    if not user_id:
        raise HTTPException(
            status_code=401,
            detail="Invalid token",
        )

    user = users_collection.find_one(
        {"_id": __import__("bson").ObjectId(user_id)}
    )

    if not user:
        raise HTTPException(
            status_code=401,
            detail="User not found",
        )

    return user