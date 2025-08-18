from __future__ import annotations

import base64
import json
import time
from typing import Any

from services.identity_service.config import settings
from services.identity_service.protocols import TokenIssuer


class DevTokenIssuer(TokenIssuer):
    """HS256-like dev token issuer (NOT secure, placeholder).

    For production, implement RS256 with JWKS exposure.
    """

    def issue_access_token(self, user_id: str, org_id: str | None, roles: list[str]) -> str:
        payload = {
            "sub": user_id,
            "org": org_id,
            "roles": roles,
            "exp": int(time.time()) + settings.JWT_ACCESS_TOKEN_EXPIRES_SECONDS,
            "iss": settings.SERVICE_NAME,
        }
        return self._encode(payload)

    def issue_refresh_token(self, user_id: str) -> tuple[str, str]:
        jti = f"r-{int(time.time()*1000)}"
        payload = {
            "sub": user_id,
            "typ": "refresh",
            "jti": jti,
            "exp": int(time.time()) + settings.JWT_ACCESS_TOKEN_EXPIRES_SECONDS * 24,
        }
        return self._encode(payload), jti

    def verify(self, token: str) -> dict[str, Any]:
        # Dev-only: decode without signature verification
        try:
            _, body_b64, _ = token.split(".")
            padded = body_b64 + "=" * (-len(body_b64) % 4)
            return json.loads(base64.urlsafe_b64decode(padded))
        except Exception:
            return {}

    def _encode(self, payload: dict[str, Any]) -> str:
        header = {"alg": "HS256", "typ": "JWT"}
        h = base64.urlsafe_b64encode(json.dumps(header).encode()).rstrip(b"=")
        b = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=")
        # Dev signature placeholder
        sig = base64.urlsafe_b64encode(settings.JWT_DEV_SECRET.encode()).rstrip(b"=")
        return f"{h.decode()}.{b.decode()}.{sig.decode()}"

