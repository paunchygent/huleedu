"""
NoopSlotOperations: Placeholder implementation for Option B architecture.

This implementation satisfies SlotOperationsProtocol but performs no operations,
as Option B uses direct essay_states assignment via assignment_sql module.
Used in DI configuration where SlotOperationsProtocol is required but not used.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from services.essay_lifecycle_service.protocols import SlotOperationsProtocol


class NoopSlotOperations(SlotOperationsProtocol):
    """No-op implementation of SlotOperationsProtocol for Option B architecture."""

    async def assign_slot_atomic(
        self, batch_id: str, content_metadata: dict[str, Any], correlation_id: UUID | None = None
    ) -> str | None:
        """No-op slot assignment - Option B uses assignment_sql directly."""
        return None

    async def get_available_slot_count(self, batch_id: str) -> int:
        """No-op slot count - Option B derives counts from essay_states."""
        return 0

    async def get_assigned_count(self, batch_id: str) -> int:
        """No-op assigned count - Option B derives counts from essay_states."""
        return 0

    async def get_essay_id_for_content(self, batch_id: str, text_storage_id: str) -> str | None:
        """No-op content lookup - Option B queries essay_states directly."""
        return None
