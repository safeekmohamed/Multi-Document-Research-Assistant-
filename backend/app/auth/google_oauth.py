import os
from urllib.parse import urlencode

import requests
from google.auth.exceptions import TransportError
from google.auth.transport.requests import Request
from google.oauth2 import id_token


GOOGLE_AUTHORIZATION_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"


class GoogleOAuthError(RuntimeError):
    pass


def get_google_oauth_config() -> tuple[str, str, str]:
    client_id = os.getenv("GOOGLE_CLIENT_ID", "").strip()
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "").strip()
    redirect_uri = os.getenv("GOOGLE_REDIRECT_URI", "").strip()
    if not client_id or not client_secret or not redirect_uri:
        raise GoogleOAuthError(
            "Google sign-in is not configured. Set GOOGLE_CLIENT_ID, "
            "GOOGLE_CLIENT_SECRET, and GOOGLE_REDIRECT_URI in backend/.env."
        )
    return client_id, client_secret, redirect_uri


def build_google_authorization_url(
    state: str,
) -> str:
    client_id, _, redirect_uri = get_google_oauth_config()
    params = urlencode(
        {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
        }
    )
    return f"{GOOGLE_AUTHORIZATION_ENDPOINT}?{params}"


def exchange_google_code(code: str) -> dict:
    client_id, client_secret, redirect_uri = get_google_oauth_config()
    try:
        response = requests.post(
            GOOGLE_TOKEN_ENDPOINT,
            data={
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
            timeout=15,
        )
        response.raise_for_status()
        token_payload = response.json()
    except (requests.RequestException, ValueError) as error:
        raise GoogleOAuthError(
            "Google could not complete sign-in. Please try again."
        ) from error

    encoded_id_token = token_payload.get("id_token")
    if not encoded_id_token:
        raise GoogleOAuthError(
            "Google did not return an identity token."
        )

    try:
        claims = id_token.verify_oauth2_token(
            encoded_id_token,
            Request(),
            audience=client_id,
        )
    except (TransportError, ValueError) as error:
        raise GoogleOAuthError(
            "Google identity verification failed. Check the OAuth setup and try again."
        ) from error

    if claims.get("iss") not in {
        "accounts.google.com",
        "https://accounts.google.com",
    }:
        raise GoogleOAuthError(
            "Google identity token issuer is invalid."
        )
    if not claims.get("email_verified"):
        raise GoogleOAuthError(
            "Google must verify the email address before sign-in."
        )
    if not claims.get("sub") or not claims.get("email"):
        raise GoogleOAuthError(
            "Google did not provide a verified account identity."
        )
    return claims
