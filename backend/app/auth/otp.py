import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv

from app.database.mongodb import otp_collection


load_dotenv()


def generate_otp() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_otp(otp_code: str) -> str:
    return hashlib.sha256(
        otp_code.encode("utf-8")
    ).hexdigest()


def save_otp(
    email: str,
    otp_code: str,
    purpose: str = "registration",
):
    email = email.lower().strip()

    expires_at = (
        datetime.now(timezone.utc)
        + timedelta(
            minutes=int(
                os.getenv(
                    "OTP_EXPIRE_MINUTES",
                    "10",
                )
            )
        )
    )

    current_time = datetime.now(timezone.utc)

    otp_collection.update_many(
        {
            "email": email,
            "is_used": False,
        },
        {
            "$set": {
                "is_used": True,
            }
        },
    )

    otp_collection.update_one(
        {
            "email": email,
        },
        {
            "$set": {
                "otp_hash": hash_otp(otp_code),
                "purpose": purpose,
                "expires_at": expires_at,
                "is_used": False,
                "created_at": current_time,
            }
        },
        upsert=True,
    )


def verify_otp(
    email: str,
    otp_code: str,
    purpose: str = "registration",
) -> bool:
    email = email.lower().strip()
    current_time = datetime.now(timezone.utc)

    otp = otp_collection.find_one(
        {
            "email": email,
            "purpose": purpose,
            "is_used": False,
        }
    )

    if not otp:
        return False

    expires_at = otp["expires_at"]

    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(
            tzinfo=timezone.utc
        )

    if expires_at <= current_time:
        otp_collection.update_one(
            {"_id": otp["_id"]},
            {
                "$set": {
                    "is_used": True,
                }
            },
        )
        return False

    entered_hash = hash_otp(
        otp_code.strip()
    )

    if otp["otp_hash"] != entered_hash:
        return False

    otp_collection.update_one(
        {"_id": otp["_id"]},
        {
            "$set": {
                "is_used": True,
                "verified_at": current_time,
            }
        },
    )

    return True