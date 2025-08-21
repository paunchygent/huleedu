from __future__ import annotations

from argon2 import PasswordHasher as Argon2Hasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from services.identity_service.protocols import PasswordHasher


class Argon2idPasswordHasher(PasswordHasher):
    """Argon2id password hasher with sensible defaults."""

    def __init__(self) -> None:
        # Defaults are strong; tune if necessary for performance
        self._hasher = Argon2Hasher()

    def hash(self, password: str) -> str:
        return self._hasher.hash(password)

    def verify(self, hash: str, password: str) -> bool:
        try:
            return self._hasher.verify(hash, password)
        except (VerifyMismatchError, InvalidHashError, VerificationError):
            return False
