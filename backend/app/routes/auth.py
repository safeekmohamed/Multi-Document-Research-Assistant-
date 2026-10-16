from fastapi import APIRouter, HTTPException
import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode, urlsplit

from fastapi import Request
from fastapi.responses import RedirectResponse
from pymongo.errors import DuplicateKeyError

from app.auth.jwt import create_access_token
from app.auth.google_oauth import (
    GoogleOAuthError,
    build_google_authorization_url,
    exchange_google_code,
    get_google_oauth_config,
)
from app.auth.otp import generate_otp, save_otp, verify_otp
from app.auth.password import hash_password
from app.database.mongodb import (
    google_oauth_states_collection,
    users_collection,
)
from app.schemas.auth import (
    GooglePasswordSetupRequest,
    LoginRequest,
    PasswordSetupConfirmRequest,
    PasswordSetupRequest,
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

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)


def _google_frontend_redirect(
    *,
    token: str | None = None,
    setup_code: str | None = None,
    intent: str = "signup",
    error: str | None = None,
) -> RedirectResponse:
    frontend_origin = os.getenv(
        "FRONTEND_ORIGIN",
        "http://localhost:3000",
    ).rstrip("/")
    destination = f"{frontend_origin}/auth/google/callback"
    if error:
        error_page = "/login" if intent == "login" else "/register"
        destination = (
            f"{frontend_origin}{error_page}?"
            + urlencode({"google_error": error})
        )
    elif token:
        destination += f"#{urlencode({'access_token': token})}"
    elif setup_code:
        destination += (
            f"#{urlencode({'password_setup_code': setup_code})}"
        )
    return RedirectResponse(destination, status_code=303)


@router.get("/google")
def start_google_signup(intent: str = "signup"):
    if intent not in {"signup", "login"}:
        raise HTTPException(
            status_code=400,
            detail="Unsupported Google authentication intent.",
        )

    try:
        _, _, redirect_uri = get_google_oauth_config()
    except GoogleOAuthError:
        return _google_frontend_redirect(
            intent=intent,
            error="not_configured",
        )

    state = secrets.token_urlsafe(32)
    state_hash = hashlib.sha256(state.encode("utf-8")).hexdigest()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
    google_oauth_states_collection.insert_one(
        {
            "state_hash": state_hash,
            "purpose": "oauth_state",
            "intent": intent,
            "expires_at": expires_at,
        }
    )
    response = RedirectResponse(
        build_google_authorization_url(state),
        status_code=302,
    )
    response.set_cookie(
        "google_oauth_state",
        state,
        max_age=600,
        httponly=True,
        secure=urlsplit(redirect_uri).scheme == "https",
        samesite="lax",
        path="/auth/google/callback",
    )
    return response


@router.get("/google/callback")
def finish_google_signup(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
):
    intent = "signup"

    def error_redirect(error_code: str) -> RedirectResponse:
        response = _google_frontend_redirect(
            intent=intent,
            error=error_code,
        )
        response.delete_cookie(
            "google_oauth_state",
            path="/auth/google/callback",
        )
        return response

    cookie_state = request.cookies.get("google_oauth_state")
    if (
        not state
        or not cookie_state
        or not secrets.compare_digest(state, cookie_state)
    ):
        return error_redirect("invalid_state")

    state_hash = hashlib.sha256(state.encode("utf-8")).hexdigest()
    stored_state = google_oauth_states_collection.find_one_and_delete(
        {
            "state_hash": state_hash,
            "purpose": "oauth_state",
            "expires_at": {"$gt": datetime.now(timezone.utc)},
        }
    )
    if not stored_state:
        return error_redirect("invalid_state")

    intent = stored_state.get("intent", "signup")
    if intent not in {"signup", "login"}:
        return error_redirect("invalid_state")

    if error == "access_denied":
        return error_redirect("cancelled")
    if error or not code:
        return error_redirect("authentication_failed")

    try:
        claims = exchange_google_code(code)
    except GoogleOAuthError:
        return error_redirect("authentication_failed")

    email = str(claims["email"]).strip().lower()
    google_sub = str(claims["sub"])
    user = users_collection.find_one({"email": email})

    if not user and intent == "login":
        return error_redirect("account_not_found")

    if user:
        if user.get("is_blocked", False):
            return error_redirect("account_blocked")
        if user.get("google_sub") != google_sub:
            return error_redirect("account_exists")
        users_collection.update_one(
            {"_id": user["_id"]},
            {
                "$set": {
                    "is_verified": True,
                    "verified_at": datetime.now(timezone.utc),
                    "last_login_at": datetime.now(timezone.utc),
                }
            },
        )
    else:
        now = datetime.now(timezone.utc)
        try:
            result = users_collection.insert_one(
                {
                    "name": str(claims.get("name") or email.partition("@")[0]),
                    "email": email,
                    "google_sub": google_sub,
                    "auth_provider": "google",
                    "is_verified": True,
                    "is_blocked": False,
                    "role": "user",
                    "created_at": now,
                    "verified_at": now,
                    "last_login_at": now,
                }
            )
            user = {
                "_id": result.inserted_id,
                "email": email,
            }
        except DuplicateKeyError:
            user = users_collection.find_one({"email": email})
            if (
                not user
                or user.get("google_sub") != google_sub
                or user.get("is_blocked", False)
            ):
                return error_redirect("account_exists")

    if intent == "signup":
        setup_code = secrets.token_urlsafe(32)
        google_oauth_states_collection.insert_one(
            {
                "state_hash": hashlib.sha256(
                    setup_code.encode("utf-8")
                ).hexdigest(),
                "purpose": "google_password_setup",
                "user_id": user["_id"],
                "expires_at": (
                    datetime.now(timezone.utc)
                    + timedelta(minutes=10)
                ),
            }
        )
        response = _google_frontend_redirect(
            setup_code=setup_code,
            intent=intent,
        )
        response.delete_cookie(
            "google_oauth_state",
            path="/auth/google/callback",
        )
        return response

    token = create_access_token(
        user_id=str(user["_id"]),
        email=email,
    )
    response = _google_frontend_redirect(
        token=token,
        intent=intent,
    )
    response.delete_cookie(
        "google_oauth_state",
        path="/auth/google/callback",
    )
    return response


@router.post(
    "/google/password/setup",
    response_model=TokenResponse,
)
def complete_google_password_setup(
    data: GooglePasswordSetupRequest,
):
    setup_hash = hashlib.sha256(
        data.setup_code.encode("utf-8")
    ).hexdigest()
    setup_record = google_oauth_states_collection.find_one_and_delete(
        {
            "state_hash": setup_hash,
            "purpose": "google_password_setup",
            "expires_at": {"$gt": datetime.now(timezone.utc)},
        }
    )
    if not setup_record:
        raise HTTPException(
            status_code=400,
            detail="This Google signup session expired or was already used. Please start again.",
        )

    user = users_collection.find_one(
        {
            "_id": setup_record["user_id"],
            "google_sub": {"$exists": True, "$ne": ""},
            "is_verified": True,
            "is_blocked": {"$ne": True},
        }
    )
    if not user:
        raise HTTPException(
            status_code=400,
            detail="This Google account cannot set a password. Please sign in again.",
        )

    result = users_collection.update_one(
        {
            "_id": user["_id"],
            "google_sub": user["google_sub"],
            "is_verified": True,
            "is_blocked": {"$ne": True},
        },
        {
            "$set": {
                "password_hash": hash_password(data.password),
                "password_set_at": datetime.now(timezone.utc),
            }
        },
    )
    if result.matched_count != 1:
        raise HTTPException(
            status_code=400,
            detail="This Google account cannot set a password. Please sign in again.",
        )

    token = create_access_token(
        user_id=str(user["_id"]),
        email=user["email"],
    )
    return {
        "access_token": token,
        "token_type": "bearer",
    }


@router.post("/register")
def register(data: RegisterRequest):

    email = data.email.lower().strip()

    existing_user = find_user_by_email(email)

    if not existing_user:

        user_id = create_user(
            name=data.name,
            email=email,
            password=data.password,
        )

        otp_code = generate_otp()

        save_otp(
            email=email,
            otp_code=otp_code,
            purpose="registration",
        )

        try:
            send_otp_email(
                recipient_email=email,
                otp_code=otp_code,
                purpose="registration",
            )

        except Exception as error:

            users_collection.delete_one(
                {"_id": user_id}
            )

            raise HTTPException(
                status_code=500,
                detail=f"OTP email could not be sent: {error}",
            )

        return {
            "message": (
                "Registration successful. "
                "Check your email for the OTP."
            ),
            "user_id": str(user_id),
        }

    if existing_user.get("is_verified", False):

        raise HTTPException(
            status_code=400,
            detail=(
                "Email is already verified. "
                "Please login instead."
            ),
        )

    users_collection.update_one(
        {"_id": existing_user["_id"]},
        {
            "$set": {
                "name": data.name,
                "password_hash": hash_password(data.password),
            }
        },
    )

    otp_code = generate_otp()

    save_otp(
        email=email,
        otp_code=otp_code,
        purpose="registration",
    )

    try:
        send_otp_email(
            recipient_email=email,
            otp_code=otp_code,
            purpose="registration",
        )

    except Exception as error:

        raise HTTPException(
            status_code=500,
            detail=f"OTP email could not be sent: {error}",
        )

    return {
        "message": (
            "Account already exists but is not verified. "
            "A new OTP has been sent."
        )
    }

@router.post("/verify-otp")
def verify_registration_otp(
    data: VerifyOTPRequest,
):

    email = data.email.lower().strip()

    valid = verify_otp(
        email=email,
        otp_code=data.otp_code,
        purpose="registration",
    )

    if not valid:
        raise HTTPException(
            status_code=400,
            detail="Invalid or expired OTP",
        )

    verify_user(email)

    return {
        "message": "Email verified successfully"
    }

@router.post("/resend-otp")
def resend_otp(
    data: ResendOTPRequest,
):

    email = data.email.lower().strip()

    user = find_user_by_email(email)

    if not user:
        raise HTTPException(
            status_code=404,
            detail="User not found",
        )

    if user.get("is_verified", False):

        raise HTTPException(
            status_code=400,
            detail=(
                "Email is already verified. "
                "Please login instead."
            ),
        )

    otp_code = generate_otp()

    save_otp(
        email=email,
        otp_code=otp_code,
        purpose="registration",
    )

    try:
        send_otp_email(
            recipient_email=email,
            otp_code=otp_code,
            purpose="registration",
        )

    except Exception as error:

        raise HTTPException(
            status_code=500,
            detail=f"OTP email could not be sent: {error}",
        )

    return {
        "message": "New OTP sent to your email"
    }

@router.post("/password/setup/request")
def request_password_setup(
    data: PasswordSetupRequest,
):
    email = data.email.lower().strip()
    user = find_user_by_email(email)

    if (
        user
        and user.get("is_verified", False)
        and not user.get("is_blocked", False)
    ):
        otp_code = generate_otp()
        save_otp(
            email=email,
            otp_code=otp_code,
            purpose="password_setup",
        )

        try:
            send_otp_email(
                recipient_email=email,
                otp_code=otp_code,
                purpose="password_setup",
            )
        except Exception as error:
            raise HTTPException(
                status_code=500,
                detail=(
                    "Unable to send a verification code right now. "
                    "Please try again later."
                ),
            ) from error

    return {
        "message": (
            "If an eligible account exists, a verification code "
            "has been sent to its email address."
        )
    }


@router.post("/password/setup/confirm")
def confirm_password_setup(
    data: PasswordSetupConfirmRequest,
):
    email = data.email.lower().strip()
    user = find_user_by_email(email)

    if (
        not user
        or not user.get("is_verified", False)
        or user.get("is_blocked", False)
        or not verify_otp(
            email=email,
            otp_code=data.otp_code,
            purpose="password_setup",
        )
    ):
        raise HTTPException(
            status_code=400,
            detail="Invalid or expired verification code.",
        )

    result = users_collection.update_one(
        {
            "_id": user["_id"],
            "is_verified": True,
            "is_blocked": {"$ne": True},
        },
        {
            "$set": {
                "password_hash": hash_password(data.password),
                "password_set_at": datetime.now(timezone.utc),
            }
        },
    )
    if result.matched_count != 1:
        raise HTTPException(
            status_code=400,
            detail="Invalid or expired verification code.",
        )

    return {
        "message": (
            "Password set successfully. You can now sign in with "
            "your email and password."
        )
    }

@router.post(
    "/login",
    response_model=TokenResponse,
)
def login(
    data: LoginRequest,
):

    email = data.email.lower().strip()

    user = authenticate_user(
        email,
        data.password,
    )

    if not user:
        account = find_user_by_email(email)
        if (
            account
            and account.get("is_verified", False)
            and not account.get("is_blocked", False)
            and account.get("google_sub")
            and not account.get("password_hash")
        ):
            raise HTTPException(
                status_code=400,
                detail=(
                    "This account uses Google sign-in. Continue with "
                    "Google, or set a password to use email login."
                ),
            )

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
