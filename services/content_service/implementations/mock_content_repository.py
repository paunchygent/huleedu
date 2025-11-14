"""In-memory mock implementation of ContentRepositoryProtocol for tests."""

from __future__ import annotations

from typing import Dict, Tuple
from uuid import UUID

from services.content_service.protocols import ContentRepositoryProtocol


class MockContentRepository(ContentRepositoryProtocol):
    """Simple in-memory content repository for testing."""

    def __init__(self) -> None:
        self._store: Dict[str, Tuple[bytes, str]] = {}

    async def save_content(
        self,
        content_id: str,
        content_data: bytes,
        content_type: str,
        correlation_id: UUID | None = None,
    ) -> None:
        self._store[content_id] = (content_data, content_type)

    async def get_content(
        self,
        content_id: str,
        correlation_id: UUID | None = None,
    ) -> tuple[bytes, str]:
        data, content_type = self._store[content_id]
        return data, content_type

    async def content_exists(self, content_id: str) -> bool:
        return content_id in self._store
