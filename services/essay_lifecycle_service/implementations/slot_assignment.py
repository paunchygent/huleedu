"""
Slot assignment data model for batch coordination.

Simple data model representing assignment of content to internal essay ID slots.
"""

from __future__ import annotations

from datetime import UTC, datetime


class SlotAssignment:
    """Represents assignment of content to an internal essay ID slot."""

    def __init__(
        self,
        internal_essay_id: str,
        text_storage_id: str,
        original_file_name: str,
    ) -> None:
        self.internal_essay_id = internal_essay_id
        self.text_storage_id = text_storage_id
        self.original_file_name = original_file_name
        self.assigned_at = datetime.now(UTC)
