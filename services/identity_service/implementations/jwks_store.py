from __future__ import annotations

from typing import List

from common_core.identity_models import JwksPublicKeyV1, JwksResponseV1


class JwksStore:
    """In-memory JWKS store for serving /.well-known/jwks.json."""

    def __init__(self) -> None:
        self._keys: List[JwksPublicKeyV1] = []

    def set_keys(self, keys: List[JwksPublicKeyV1]) -> None:
        self._keys = keys

    def add_key(self, key: JwksPublicKeyV1) -> None:
        # Replace if same kid exists
        self._keys = [k for k in self._keys if k.kid != key.kid] + [key]

    def get_jwks(self) -> JwksResponseV1:
        return JwksResponseV1(keys=self._keys)

