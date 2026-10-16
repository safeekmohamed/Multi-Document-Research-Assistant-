import hashlib
import unittest
from datetime import datetime, timezone
from unittest.mock import ANY, Mock, patch
from urllib.parse import parse_qs, urlsplit

from bson import ObjectId
from fastapi import HTTPException

from app.auth import google_oauth
from app.routes import auth
from app.schemas.auth import GooglePasswordSetupRequest


class GoogleOAuthServiceTests(unittest.TestCase):
    @patch.dict(
        "os.environ",
        {
            "GOOGLE_CLIENT_ID": "client-id",
            "GOOGLE_CLIENT_SECRET": "client-secret",
            "GOOGLE_REDIRECT_URI": "http://localhost:8000/auth/google/callback",
        },
        clear=False,
    )
    def test_code_exchange_verifies_identity_token_for_configured_audience(self):
        response = Mock()
        response.json.return_value = {"id_token": "encoded-google-token"}
        claims = {
            "iss": "https://accounts.google.com",
            "sub": "google-subject",
            "email": "verified@example.com",
            "email_verified": True,
        }

        with (
            patch.object(google_oauth.requests, "post", return_value=response) as post,
            patch.object(
                google_oauth.id_token,
                "verify_oauth2_token",
                return_value=claims,
            ) as verify,
        ):
            result = google_oauth.exchange_google_code("authorization-code")

        self.assertEqual(result, claims)
        self.assertEqual(post.call_args.kwargs["timeout"], 15)
        self.assertEqual(verify.call_args.kwargs["audience"], "client-id")

    @patch.dict(
        "os.environ",
        {
            "GOOGLE_CLIENT_ID": "client-id",
            "GOOGLE_CLIENT_SECRET": "client-secret",
            "GOOGLE_REDIRECT_URI": "http://localhost:8000/auth/google/callback",
        },
        clear=False,
    )
    def test_unverified_google_email_is_rejected(self):
        response = Mock()
        response.json.return_value = {"id_token": "encoded-google-token"}
        with (
            patch.object(google_oauth.requests, "post", return_value=response),
            patch.object(
                google_oauth.id_token,
                "verify_oauth2_token",
                return_value={
                    "iss": "https://accounts.google.com",
                    "sub": "google-subject",
                    "email": "unverified@example.com",
                    "email_verified": False,
                },
            ),
        ):
            with self.assertRaisesRegex(
                google_oauth.GoogleOAuthError,
                "verify the email address",
            ):
                google_oauth.exchange_google_code("authorization-code")

    @patch.dict("os.environ", {}, clear=True)
    def test_missing_oauth_configuration_is_explicit(self):
        with self.assertRaisesRegex(
            google_oauth.GoogleOAuthError,
            "GOOGLE_CLIENT_ID",
        ):
            google_oauth.get_google_oauth_config()


class GoogleOAuthRouteTests(unittest.TestCase):
    @patch.dict(
        "os.environ",
        {
            "GOOGLE_CLIENT_ID": "client-id",
            "GOOGLE_CLIENT_SECRET": "client-secret",
            "GOOGLE_REDIRECT_URI": "http://localhost:8000/auth/google/callback",
        },
        clear=False,
    )
    def test_start_route_saves_hash_and_redirects_with_state(self):
        with (
            patch.object(auth, "build_google_authorization_url") as build_url,
            patch.object(auth.google_oauth_states_collection, "insert_one") as insert,
        ):
            build_url.side_effect = lambda state: f"https://accounts.google.test/?state={state}"
            response = auth.start_google_signup(intent="signup")

        state = parse_qs(urlsplit(response.headers["location"]).query)["state"][0]
        inserted = insert.call_args.args[0]
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            inserted["state_hash"],
            hashlib.sha256(state.encode("utf-8")).hexdigest(),
        )
        self.assertEqual(inserted["purpose"], "oauth_state")
        self.assertEqual(inserted["intent"], "signup")
        self.assertGreater(inserted["expires_at"], datetime.now(timezone.utc))

    @patch.dict(
        "os.environ",
        {"FRONTEND_ORIGIN": "http://localhost:3000"},
        clear=False,
    )
    def test_google_signup_creates_user_and_returns_single_use_setup_code(self):
        user_id = ObjectId()
        claims = {
            "email": "new.user@example.com",
            "sub": "verified-google-sub",
            "name": "New User",
            "email_verified": True,
        }
        with (
            patch.object(
                auth.google_oauth_states_collection,
                "find_one_and_delete",
                return_value={
                    "state_hash": "consumed",
                    "intent": "signup",
                },
            ) as consume_state,
            patch.object(
                auth.google_oauth_states_collection,
                "insert_one",
            ) as insert_setup_code,
            patch.object(auth, "exchange_google_code", return_value=claims),
            patch.object(auth.users_collection, "find_one", return_value=None),
            patch.object(
                auth.users_collection,
                "insert_one",
                return_value=Mock(inserted_id=user_id),
            ) as insert_user,
        ):
            response = auth.finish_google_signup(
                request=Mock(cookies={"google_oauth_state": "one-time-state"}),
                code="authorization-code",
                state="one-time-state",
            )

        destination = urlsplit(response.headers["location"])
        created_user = insert_user.call_args.args[0]
        self.assertEqual(response.status_code, 303)
        self.assertEqual(destination.scheme, "http")
        self.assertEqual(destination.netloc, "localhost:3000")
        self.assertEqual(destination.path, "/auth/google/callback")
        self.assertEqual(destination.query, "")
        setup_code = parse_qs(destination.fragment)["password_setup_code"][0]
        self.assertNotIn("password_hash", created_user)
        self.assertTrue(created_user["is_verified"])
        self.assertEqual(created_user["google_sub"], claims["sub"])
        self.assertEqual(
            consume_state.call_args.args[0]["state_hash"],
            hashlib.sha256(b"one-time-state").hexdigest(),
        )
        self.assertEqual(
            consume_state.call_args.args[0]["purpose"],
            "oauth_state",
        )
        setup_record = insert_setup_code.call_args.args[0]
        self.assertEqual(
            setup_record["state_hash"],
            hashlib.sha256(setup_code.encode("utf-8")).hexdigest(),
        )
        self.assertEqual(setup_record["purpose"], "google_password_setup")
        self.assertEqual(setup_record["user_id"], user_id)

    def test_existing_password_account_is_not_silently_linked(self):
        with (
            patch.object(
                auth.google_oauth_states_collection,
                "find_one_and_delete",
                return_value={
                    "state_hash": "consumed",
                    "intent": "signup",
                },
            ),
            patch.object(
                auth,
                "exchange_google_code",
                return_value={
                    "email": "existing@example.com",
                    "sub": "different-google-sub",
                },
            ),
            patch.object(
                auth.users_collection,
                "find_one",
                return_value={
                    "_id": ObjectId(),
                    "email": "existing@example.com",
                    "password_hash": "existing-hash",
                },
            ),
            patch.object(auth.users_collection, "insert_one") as insert_user,
        ):
            response = auth.finish_google_signup(
                request=Mock(cookies={"google_oauth_state": "one-time-state"}),
                code="authorization-code",
                state="one-time-state",
            )

        destination = urlsplit(response.headers["location"])
        self.assertEqual(
            parse_qs(destination.query)["google_error"],
            ["account_exists"],
        )
        insert_user.assert_not_called()

    @patch.dict(
        "os.environ",
        {"FRONTEND_ORIGIN": "http://localhost:3000"},
        clear=False,
    )
    def test_existing_google_account_can_sign_in_without_creating_a_duplicate(self):
        user = {
            "_id": ObjectId(),
            "email": "existing.google@example.com",
            "google_sub": "verified-google-sub",
            "is_verified": True,
            "is_blocked": False,
        }
        claims = {
            "email": user["email"],
            "sub": user["google_sub"],
            "email_verified": True,
        }
        with (
            patch.object(
                auth.google_oauth_states_collection,
                "find_one_and_delete",
                return_value={
                    "state_hash": "consumed",
                    "intent": "login",
                },
            ),
            patch.object(auth, "exchange_google_code", return_value=claims),
            patch.object(auth.users_collection, "find_one", return_value=user),
            patch.object(auth.users_collection, "update_one"),
            patch.object(
                auth.users_collection,
                "insert_one",
            ) as insert_user,
            patch.object(
                auth,
                "create_access_token",
                return_value="application-session-token",
            ) as create_token,
        ):
            response = auth.finish_google_signup(
                request=Mock(cookies={"google_oauth_state": "one-time-state"}),
                code="authorization-code",
                state="one-time-state",
            )

        destination = urlsplit(response.headers["location"])
        self.assertEqual(response.status_code, 303)
        self.assertEqual(
            parse_qs(destination.fragment)["access_token"],
            ["application-session-token"],
        )
        insert_user.assert_not_called()
        create_token.assert_called_once_with(
            user_id=str(user["_id"]),
            email=user["email"],
        )

    def test_google_login_does_not_create_an_unregistered_account(self):
        with (
            patch.object(
                auth.google_oauth_states_collection,
                "find_one_and_delete",
                return_value={
                    "state_hash": "consumed",
                    "intent": "login",
                },
            ),
            patch.object(
                auth,
                "exchange_google_code",
                return_value={
                    "email": "unknown@example.com",
                    "sub": "verified-google-sub",
                    "email_verified": True,
                },
            ),
            patch.object(auth.users_collection, "find_one", return_value=None),
            patch.object(auth.users_collection, "insert_one") as insert_user,
            patch.object(auth, "create_access_token") as create_token,
        ):
            response = auth.finish_google_signup(
                request=Mock(cookies={"google_oauth_state": "one-time-state"}),
                code="authorization-code",
                state="one-time-state",
            )

        destination = urlsplit(response.headers["location"])
        self.assertEqual(
            parse_qs(destination.query)["google_error"],
            ["account_not_found"],
        )
        self.assertEqual(destination.path, "/login")
        insert_user.assert_not_called()
        create_token.assert_not_called()

    def test_google_password_setup_consumes_code_hash_and_returns_app_session(self):
        user_id = ObjectId()
        user = {
            "_id": user_id,
            "email": "existing.google@example.com",
            "google_sub": "verified-google-sub",
            "is_verified": True,
            "is_blocked": False,
        }
        setup_code = "single-use-google-signup-code-1234567890"
        with (
            patch.object(
                auth.google_oauth_states_collection,
                "find_one_and_delete",
                return_value={"user_id": user_id},
            ) as consume_code,
            patch.object(auth.users_collection, "find_one", return_value=user),
            patch.object(
                auth.users_collection,
                "update_one",
                return_value=Mock(matched_count=1),
            ) as update_user,
            patch.object(
                auth,
                "hash_password",
                return_value="bcrypt-hash",
            ) as hash_password,
            patch.object(
                auth,
                "create_access_token",
                return_value="application-session-token",
            ) as create_token,
        ):
            response = auth.complete_google_password_setup(
                GooglePasswordSetupRequest(
                    setup_code=setup_code,
                    password="new-password",
                )
            )

        consume_code.assert_called_once_with(
            {
                "state_hash": hashlib.sha256(
                    setup_code.encode("utf-8")
                ).hexdigest(),
                "purpose": "google_password_setup",
                "expires_at": {"$gt": ANY},
            }
        )
        self.assertEqual(response["access_token"], "application-session-token")
        create_token.assert_called_once_with(
            user_id=str(user_id),
            email=user["email"],
        )
        hash_password.assert_called_once_with("new-password")
        self.assertEqual(
            update_user.call_args.args[1]["$set"]["password_hash"],
            "bcrypt-hash",
        )

    def test_expired_or_replayed_google_password_setup_code_is_rejected(self):
        with (
            patch.object(
                auth.google_oauth_states_collection,
                "find_one_and_delete",
                return_value=None,
            ),
            patch.object(auth.users_collection, "update_one") as update_user,
        ):
            with self.assertRaises(HTTPException) as raised:
                auth.complete_google_password_setup(
                    GooglePasswordSetupRequest(
                        setup_code="single-use-google-signup-code-1234567890",
                        password="new-password",
                    )
                )

        self.assertEqual(raised.exception.status_code, 400)
        update_user.assert_not_called()

    def test_invalid_or_replayed_state_never_exchanges_code(self):
        with (
            patch.object(
                auth.google_oauth_states_collection,
                "find_one_and_delete",
                return_value=None,
            ),
            patch.object(auth, "exchange_google_code") as exchange,
        ):
            response = auth.finish_google_signup(
                request=Mock(cookies={"google_oauth_state": "already-used-state"}),
                code="authorization-code",
                state="already-used-state",
            )

        self.assertEqual(
            parse_qs(urlsplit(response.headers["location"]).query)[
                "google_error"
            ],
            ["invalid_state"],
        )
        exchange.assert_not_called()


if __name__ == "__main__":
    unittest.main()
