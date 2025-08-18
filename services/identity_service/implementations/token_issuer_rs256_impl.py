from __future__ import annotations

import base64
import time
from pathlib import Path
from typing import Any

import jwt
from common_core.identity_models import JwksPublicKeyV1
from cryptography.hazmat.primitives import serialization

from services.identity_service.config import settings
from services.identity_service.implementations.jwks_store import JwksStore
from services.identity_service.protocols import TokenIssuer


def _b64url_uint(n: int) -> str:
    # Convert integer to base64url without padding
    b = n.to_bytes((n.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


class Rs256TokenIssuer(TokenIssuer):
    """RS256 Token Issuer using service-provided private key and JWKS exposure."""

    def __init__(self, jwks_store: JwksStore) -> None:
        self._jwks_store = jwks_store
        self._private_key = self._load_private_key()
        self._public_key = self._private_key.public_key()
        self._kid = settings.JWT_RS256_PUBLIC_JWKS_KID or "identity-rs256-key"
        self._register_jwk()

    def _load_private_key(self):
        key_path = settings.JWT_RS256_PRIVATE_KEY_PATH
        if not key_path:
            raise RuntimeError("JWT_RS256_PRIVATE_KEY_PATH must be set in production")
        pem = Path(key_path).read_bytes()
        return serialization.load_pem_private_key(pem, password=None)

    def _register_jwk(self) -> None:
        numbers = self._public_key.public_numbers()
        n = _b64url_uint(numbers.n)
        e = _b64url_uint(numbers.e)
        jwk = JwksPublicKeyV1(kid=self._kid, kty="RSA", n=n, e=e)
        self._jwks_store.add_key(jwk)

    def issue_access_token(self, user_id: str, org_id: str | None, roles: list[str]) -> str:
        payload = {
            "sub": user_id,
            "org": org_id,
            "roles": roles,
            "exp": int(time.time()) + settings.JWT_ACCESS_TOKEN_EXPIRES_SECONDS,
            "iss": settings.SERVICE_NAME,
        }
        headers = {"kid": self._kid, "alg": "RS256", "typ": "JWT"}
        return jwt.encode(payload, self._private_key, algorithm="RS256", headers=headers)

    def issue_refresh_token(self, user_id: str) -> tuple[str, str]:
        jti = f"r-{int(time.time() * 1000)}"
        payload = {
            "sub": user_id,
            "typ": "refresh",
            "jti": jti,
            "exp": int(time.time()) + settings.JWT_ACCESS_TOKEN_EXPIRES_SECONDS * 24,
            "iss": settings.SERVICE_NAME,
        }
        headers = {"kid": self._kid, "alg": "RS256", "typ": "JWT"}
        token = jwt.encode(payload, self._private_key, algorithm="RS256", headers=headers)
        return token, jti

    def verify(self, token: str) -> dict[str, Any]:
        try:
            return jwt.decode(
                token, self._public_key, algorithms=["RS256"], options={"verify_aud": False}
            )
        except Exception:
            return {}
