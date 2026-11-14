import hmac
from dataclasses import dataclass

import httpx2
from google.auth.exceptions import GoogleAuthError
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

from app.core.config import settings
from app.core.errors import BadRequest

TOKEN_URL = "https://oauth2.googleapis.com/token"
ISSUERS = ("accounts.google.com", "https://accounts.google.com")
CALLBACK_PATH = "/api/auth/google/callback"
FAILED = "Google sign-in didn't work. Please try again."


@dataclass(frozen=True)
class GoogleUser:
    subject: str
    email: str
    name: str


def enabled() -> bool:
    return bool(settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET.get_secret_value())


def check_redirect(redirect_uri: str) -> None:
    origins = {*settings.cors_origins_list, settings.WEB_APP_URL.rstrip("/")}
    if redirect_uri not in {origin + CALLBACK_PATH for origin in origins}:
        raise BadRequest(FAILED)


def exchange(code: str, verifier: str, redirect_uri: str) -> str:
    try:
        res = httpx2.post(
            TOKEN_URL,
            data={
                "code": code,
                "code_verifier": verifier,
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET.get_secret_value(),
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
            timeout=10,
        )
    except httpx2.HTTPError as e:
        raise BadRequest(FAILED) from e
    token = res.json().get("id_token") if res.status_code == 200 else None
    if not isinstance(token, str):
        raise BadRequest(FAILED)
    return token


def verify(token: str, nonce: str) -> GoogleUser:
    try:
        info = id_token.verify_oauth2_token(
            token, google_requests.Request(), settings.GOOGLE_CLIENT_ID
        )
    except (ValueError, GoogleAuthError) as e:
        raise BadRequest(FAILED) from e
    if info.get("iss") not in ISSUERS or not hmac.compare_digest(str(info.get("nonce", "")), nonce):
        raise BadRequest(FAILED)
    email = str(info.get("email") or "").strip().lower()
    if not email or info.get("email_verified") is not True:
        raise BadRequest("Your Google account needs a confirmed email to sign in to Sukat.")
    name = str(info.get("name") or email.split("@")[0])[:120]
    return GoogleUser(subject=str(info["sub"]), email=email, name=name)


def google_user(code: str, verifier: str, redirect_uri: str, nonce: str) -> GoogleUser:
    if not enabled():
        raise BadRequest("Sign in with Google isn't set up yet.")
    check_redirect(redirect_uri)
    return verify(exchange(code, verifier, redirect_uri), nonce)
