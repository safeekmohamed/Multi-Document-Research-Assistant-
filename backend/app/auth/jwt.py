import os
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt.exceptions import InvalidTokenError
from bson import ObjectId

from app.database.mongodb import users_collection

load_dotenv()

security = HTTPBearer()

def create_access_token(
    user_id: str,
    email: str,
) -> str:

    expires_at = (
        datetime.now(timezone.utc)
        + timedelta(
            minutes=int(
                os.getenv(
                    "JWT_EXPIRE_MINUTES",
                    "1440",
                )
            )
        )
    )

    payload = {
        "user_id": user_id,
        "email": email,
        "exp": expires_at,
    }

    return jwt.encode(
        payload,
        os.getenv("JWT_SECRET_KEY"),
        algorithm=os.getenv(
            "JWT_ALGORITHM",
            "HS256",
        ),
    )

def decode_access_token(
    token: str,
) -> dict:

    try:

        return jwt.decode(
            token,
            os.getenv(
                "JWT_SECRET_KEY"
            ),
            algorithms=[
                os.getenv(
                    "JWT_ALGORITHM",
                    "HS256",
                )
            ],
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

    user_id = payload.get(
        "user_id"
    )

    if not user_id:

        raise HTTPException(
            status_code=401,
            detail="Invalid token",
        )

    try:

        object_id = ObjectId(
            user_id
        )

    except Exception:

        raise HTTPException(
            status_code=401,
            detail="Invalid user ID",
        )

    user = users_collection.find_one(
        {
            "_id": object_id
        }
    )

    if not user:

        raise HTTPException(
            status_code=401,
            detail="User not found",
        )

    if user.get(
        "is_blocked",
        False,
    ):

        raise HTTPException(
            status_code=403,
            detail="Your account has been blocked by an administrator.",
        )

    return user

def get_current_admin(
    current_user: dict = Depends(
        get_current_user
    ),
):

    role = current_user.get(
        "role",
        "user",
    )

    if role != "admin":

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )

    return current_user
