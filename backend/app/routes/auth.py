from fastapi import APIRouter, HTTPException

from app.auth.jwt import create_access_token
from app.auth.otp import (
    generate_otp,
    save_otp,
    verify_otp,
)
from app.auth.password import hash_password
from app.schemas.auth import (
    LoginRequest,
    RegisterRequest,
    ResendOTPRequest,
    TokenResponse,
    VerifyOTPRequest,
)
from app.services.email_service import send_otp_email
from app.services.user_service import (
    authenticate_user,
    create_user,
    find_user_by_email,
    verify_user,
)
from app.database.mongodb import users_collection


router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)


@router.post("/register")
def register(
    data: RegisterRequest,
):
    existing_user = find_user_by_email(data.email)

    if existing_user:
        # Repair an old OTP-created user that has no password_hash
        if not existing_user.get("password_hash"):
            users_collection.update_one(
                {"_id": existing_user["_id"]},
                {
                    "$set": {
                        "name": data.name,
                        "password_hash": hash_password(
                            data.password
                        ),
                        "is_verified": False,
                        "provider": "password",
                    }
                },
            )

            otp_code = generate_otp()

            save_otp(
                data.email,
                otp_code,
                purpose="registration",
            )

            send_otp_email(
                data.email,
                otp_code,
                purpose="registration",
            )

            return {
                "message": (
                    "Account updated successfully. "
                    "Check your email for the OTP."
                )
            }

        if existing_user.get(
            "is_verified",
            False,
        ):
            raise HTTPException(
                status_code=400,
                detail="Email is already registered",
            )

        # Existing user has a password but is not verified
        users_collection.update_one(
            {"_id": existing_user["_id"]},
            {
                "$set": {
                    "name": data.name,
                    "password_hash": hash_password(
                        data.password
                    ),
                }
            },
        )

        otp_code = generate_otp()

        save_otp(
            data.email,
            otp_code,
            purpose="registration",
        )

        send_otp_email(
            data.email,
            otp_code,
            purpose="registration",
        )

        return {
            "message": (
                "Account already exists but is not verified. "
                "A new OTP has been sent."
            )
        }

    user_id = create_user(
        name=data.name,
        email=data.email,
        password=data.password,
    )

    otp_code = generate_otp()

    save_otp(
        data.email,
        otp_code,
        purpose="registration",
    )

    send_otp_email(
        data.email,
        otp_code,
        purpose="registration",
    )

    return {
        "message": (
            "Registration successful. "
            "Check your email for the OTP."
        ),
        "user_id": str(user_id),
    }


@router.post("/verify-otp")
def verify_registration_otp(
    data: VerifyOTPRequest,
):
    valid = verify_otp(
        data.email,
        data.otp_code,
        purpose="registration",
    )

    if not valid:
        raise HTTPException(
            status_code=400,
            detail="Invalid or expired OTP",
        )

    verify_user(data.email)

    return {
        "message": "Email verified successfully"
    }


@router.post("/resend-otp")
def resend_otp(
    data: ResendOTPRequest,
):
    user = find_user_by_email(data.email)

    if not user:
        raise HTTPException(
            status_code=404,
            detail="User not found",
        )

    if user.get(
        "is_verified",
        False,
    ):
        raise HTTPException(
            status_code=400,
            detail="Email is already verified",
        )

    otp_code = generate_otp()

    save_otp(
        data.email,
        otp_code,
        purpose="registration",
    )

    send_otp_email(
        data.email,
        otp_code,
        purpose="registration",
    )

    return {
        "message": "New OTP sent to your email"
    }


@router.post(
    "/login",
    response_model=TokenResponse,
)
def login(
    data: LoginRequest,
):
    user = authenticate_user(
        data.email,
        data.password,
    )

    if not user:
        raise HTTPException(
            status_code=401,
            detail=(
                "Invalid email/password "
                "or email is not verified"
            ),
        )

    token = create_access_token(
        user_id=str(user["_id"]),
        email=user["email"],
    )

    return {
        "access_token": token,
        "token_type": "bearer",
    }