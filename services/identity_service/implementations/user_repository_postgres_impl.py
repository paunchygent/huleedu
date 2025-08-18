from __future__ import annotations

from datetime import UTC, datetime
from typing import Optional

from services.identity_service.protocols import UserRepo


class DevInMemoryUserRepo(UserRepo):
    """Development-only in-memory user repository scaffold."""

    def __init__(self) -> None:
        self._users_by_email: dict[str, dict] = {}
        self._seq = 0

    async def create_user(self, email: str, org_id: str | None, password_hash: str) -> dict:
        self._seq += 1
        user_id = f"u-{self._seq:06d}"
        user = {
            "id": user_id,
            "email": email,
            "org_id": org_id,
            "password_hash": password_hash,
            "roles": ["teacher"],
            "email_verified": False,
            "registered_at": datetime.now(UTC),
        }
        self._users_by_email[email.lower()] = user
        return user

    async def get_user_by_email(self, email: str) -> Optional[dict]:
        return self._users_by_email.get(email.lower())

    async def set_email_verified(self, user_id: str) -> None:
        for u in self._users_by_email.values():
            if u["id"] == user_id:
                u["email_verified"] = True
                return
