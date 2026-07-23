"""Google OAuth 2.0 protocol client: PKCE, authorization URL, token exchange.

HTTP and protocol details only. Deciding which local user an identity maps to
is `services/google_identity.py`.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from hashlib import sha256
from secrets import token_urlsafe
from urllib.parse import urlencode

import httpx

from ..config import Settings

AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"

_HTTP_TIMEOUT = 15
_SCOPE = "openid email profile"
_STATE_BYTES = 32
_VERIFIER_BYTES = 64


class GoogleOAuthError(RuntimeError):
    """Google rejected the exchange or returned an unusable profile."""


@dataclass(frozen=True)
class PkceChallenge:
    state: str
    verifier: str
    challenge: str

    @classmethod
    def generate(cls) -> "PkceChallenge":
        verifier = token_urlsafe(_VERIFIER_BYTES)
        digest = sha256(verifier.encode()).digest()
        return cls(
            state=token_urlsafe(_STATE_BYTES),
            verifier=verifier,
            challenge=base64.urlsafe_b64encode(digest).rstrip(b"=").decode(),
        )


def authorization_url(cfg: Settings, pkce: PkceChallenge) -> str:
    params = {
        "client_id": cfg.GOOGLE_CLIENT_ID,
        "redirect_uri": cfg.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": _SCOPE,
        "state": pkce.state,
        "code_challenge": pkce.challenge,
        "code_challenge_method": "S256",
        "access_type": "online",
        "prompt": "select_account",
    }
    return f"{AUTHORIZE_URL}?{urlencode(params)}"


async def fetch_userinfo(cfg: Settings, code: str, verifier: str) -> dict[str, object]:
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        token_response = await client.post(
            TOKEN_URL,
            data={
                "code": code,
                "client_id": cfg.GOOGLE_CLIENT_ID,
                "client_secret": cfg.GOOGLE_CLIENT_SECRET,
                "redirect_uri": cfg.GOOGLE_REDIRECT_URI,
                "grant_type": "authorization_code",
                "code_verifier": verifier,
            },
        )
        if not token_response.is_success:
            raise GoogleOAuthError("Google login could not be completed.")

        access_token = token_response.json().get("access_token")
        response = await client.get(
            USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if not response.is_success:
            raise GoogleOAuthError("Google profile could not be read.")
        return response.json()
