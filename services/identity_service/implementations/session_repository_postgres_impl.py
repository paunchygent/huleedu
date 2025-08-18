from __future__ import annotations

import time

from services.identity_service.protocols import SessionRepo


class DevInMemorySessionRepo(SessionRepo):
    """Development-only in-memory refresh session repository scaffold."""

    def __init__(self) -> None:
        self._refresh: dict[str, tuple[str, int]] = {}

    async def store_refresh(self, user_id: str, jti: str, exp_ts: int) -> None:
        self._refresh[jti] = (user_id, exp_ts)

    async def revoke_refresh(self, jti: str) -> None:
        self._refresh.pop(jti, None)

    async def is_refresh_valid(self, jti: str) -> bool:
        item = self._refresh.get(jti)
        return bool(item and item[1] > int(time.time()))
