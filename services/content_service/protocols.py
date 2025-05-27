from __future__ import annotations

from typing import Optional, Protocol

# Assuming common_core models might be used in signatures
from common_core.enums import ContentType


class ContentRepositoryProtocol(Protocol):
    async def store_content(
        self,
        content_type: ContentType,
        content_data: bytes,
        user_id: Optional[str] = None,  # Optional user context
    ) -> str:
        """Stores content data and returns a unique storage ID."""
        ...

    async def retrieve_content(self, storage_id: str) -> bytes | None:
        """Retrieves content data by its storage ID, returns None if not found."""
        ...

    async def delete_content(self, storage_id: str) -> bool:
        """Deletes content data by its storage ID, returns True on success."""
        ...


class ContentEventPublisherProtocol(Protocol):
    async def publish_content_stored_event(
        self, storage_id: str, content_type: ContentType, user_id: Optional[str]
    ) -> None:
        """Publishes an event indicating content has been stored (example)."""
        # This is speculative; actual event details would be TBD.
        # Might use a specific EventEnvelope[ContentStoredEventData]
        ...
