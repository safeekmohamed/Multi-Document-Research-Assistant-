import unittest
from unittest.mock import Mock, patch

from bson import ObjectId
from fastapi import HTTPException

from app.auth.password import hash_password, verify_password
from app.routes import auth
from app.schemas.auth import (
    LoginRequest,
    PasswordSetupConfirmRequest,
    PasswordSetupRequest,
)
from app.services import user_service


class PasswordSetupRouteTests(unittest.TestCase):
    def test_passwordless_google_account_gets_actionable_login_message(self):
        account = {
            "email": "google@example.com",
            "google_sub": "google-sub",
            "is_verified": True,
            "is_blocked": False,
        }
        with (
            patch.object(auth, "find_user_by_email", return_value=account),
            patch.object(user_service, "find_user_by_email", return_value=account),
        ):
            with self.assertRaises(HTTPException) as raised:
                auth.login(
                    LoginRequest(
                        email="google@example.com",
                        password="not-the-password",
                    )
                )

        self.assertEqual(raised.exception.status_code, 400)
        self.assertIn("uses Google sign-in", raised.exception.detail)
        self.assertIn("set a password", raised.exception.detail)

    def test_existing_email_password_login_still_returns_application_token(self):
        user = {
            "_id": ObjectId(),
            "email": "password@example.com",
        }
        with (
            patch.object(auth, "authenticate_user", return_value=user),
            patch.object(
                auth,
                "create_access_token",
                return_value="application-token",
            ) as create_token,
        ):
            response = auth.login(
                LoginRequest(
                    email="password@example.com",
                    password="correct-password",
                )
            )

        self.assertEqual(response["access_token"], "application-token")
        create_token.assert_called_once_with(
            user_id=str(user["_id"]),
            email=user["email"],
        )

    def test_existing_user_password_is_checked_with_the_stored_hash(self):
        stored_user = {
            "email": "password@example.com",
            "password_hash": hash_password("correct-password"),
            "is_verified": True,
            "is_blocked": False,
        }
        with patch.object(
            user_service,
            "find_user_by_email",
            return_value=stored_user,
        ):
            self.assertIs(
                user_service.authenticate_user(
                    "password@example.com",
                    "correct-password",
                ),
                stored_user,
            )
            self.assertIsNone(
                user_service.authenticate_user(
                    "password@example.com",
                    "incorrect-password",
                )
            )

    def test_password_setup_request_sends_a_purpose_scoped_otp(self):
        user = {
            "email": "google@example.com",
            "is_verified": True,
            "is_blocked": False,
        }
        with (
            patch.object(auth, "find_user_by_email", return_value=user),
            patch.object(auth, "generate_otp", return_value="123456"),
            patch.object(auth, "save_otp") as save_otp,
            patch.object(auth, "send_otp_email") as send_email,
        ):
            response = auth.request_password_setup(
                PasswordSetupRequest(email="google@example.com")
            )

        self.assertIn("If an eligible account exists", response["message"])
        save_otp.assert_called_once_with(
            email="google@example.com",
            otp_code="123456",
            purpose="password_setup",
        )
        send_email.assert_called_once_with(
            recipient_email="google@example.com",
            otp_code="123456",
            purpose="password_setup",
        )

    def test_unknown_email_gets_same_request_response_without_sending_email(self):
        with (
            patch.object(auth, "find_user_by_email", return_value=None),
            patch.object(auth, "generate_otp") as generate_otp,
            patch.object(auth, "send_otp_email") as send_email,
        ):
            response = auth.request_password_setup(
                PasswordSetupRequest(email="unknown@example.com")
            )

        self.assertIn("If an eligible account exists", response["message"])
        generate_otp.assert_not_called()
        send_email.assert_not_called()

    def test_valid_email_otp_sets_only_a_hashed_password(self):
        user = {
            "_id": ObjectId(),
            "email": "google@example.com",
            "is_verified": True,
            "is_blocked": False,
        }
        with (
            patch.object(auth, "find_user_by_email", return_value=user),
            patch.object(auth, "verify_otp", return_value=True) as verify_otp,
            patch.object(
                auth.users_collection,
                "update_one",
                return_value=Mock(matched_count=1),
            ) as update_user,
        ):
            response = auth.confirm_password_setup(
                PasswordSetupConfirmRequest(
                    email="google@example.com",
                    otp_code="123456",
                    password="new-password",
                )
            )

        update_filter, update = update_user.call_args.args
        stored_hash = update["$set"]["password_hash"]
        self.assertIn("successfully", response["message"])
        self.assertEqual(update_filter["_id"], user["_id"])
        self.assertTrue(stored_hash.startswith("$2"))
        self.assertTrue(verify_password("new-password", stored_hash))
        self.assertNotIn("new-password", str(update))
        verify_otp.assert_called_once_with(
            email="google@example.com",
            otp_code="123456",
            purpose="password_setup",
        )

    def test_invalid_email_otp_does_not_change_password(self):
        user = {
            "_id": ObjectId(),
            "email": "google@example.com",
            "is_verified": True,
            "is_blocked": False,
        }
        with (
            patch.object(auth, "find_user_by_email", return_value=user),
            patch.object(auth, "verify_otp", return_value=False),
            patch.object(auth.users_collection, "update_one") as update_user,
        ):
            with self.assertRaises(HTTPException) as raised:
                auth.confirm_password_setup(
                    PasswordSetupConfirmRequest(
                        email="google@example.com",
                        otp_code="123456",
                        password="new-password",
                    )
                )

        self.assertEqual(raised.exception.status_code, 400)
        update_user.assert_not_called()


if __name__ == "__main__":
    unittest.main()
