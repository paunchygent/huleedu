from __future__ import annotations

import time
from typing import Any

import jwt
from jwt import InvalidTokenError

from services.identity_service.config import settings
from services.identity_service.protocols import TokenIssuer


class DevTokenIssuer(TokenIssuer):
    """HS256-like dev token issuer (NOT secure, placeholder).

    For production, implement RS256 with JWKS exposure.
    """

    def __init__(self) -> None:
        self._secret = settings.JWT_DEV_SECRET.get_secret_value()

    def issue_access_token(self, user_id: str, org_id: str | None, roles: list[str]) -> str:
        payload = {
            "sub": user_id,
            "org": org_id,
            "roles": roles,
            "exp": int(time.time()) + settings.JWT_ACCESS_TOKEN_EXPIRES_SECONDS,
            "iss": settings.JWT_ISSUER,
            "aud": settings.JWT_AUDIENCE,
        }
        return self._encode(payload)

    def issue_refresh_token(self, user_id: str) -> tuple[str, str]:
        jti = f"r-{int(time.time() * 1000)}"
        payload = {
            "sub": user_id,
            "typ": "refresh",
            "jti": jti,
            "exp": int(time.time()) + settings.JWT_ACCESS_TOKEN_EXPIRES_SECONDS * 24,
            "iss": settings.JWT_ISSUER,
            "aud": settings.JWT_AUDIENCE,
        }
        return self._encode(payload), jti

    def verify(self, token: str) -> dict[str, Any]:
        try:
            return jwt.decode(
                token,
                self._secret,
                algorithms=["HS256"],
                audience=settings.JWT_AUDIENCE,
                issuer=settings.JWT_ISSUER,
                options={"verify_exp": False},
            )
        except InvalidTokenError:
            return {}

    def _encode(self, payload: dict[str, Any]) -> str:
        return jwt.encode(payload, self._secret, algorithm="HS256")
