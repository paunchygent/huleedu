"""
Basic CRUD operations for Essay Lifecycle Service SQLite implementation.

Handles individual essay state operations including get, update, and create
for the SQLite-based persistence layer.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import aiosqlite
from common_core.enums import ContentType, EssayStatus
from common_core.metadata_models import EntityReference

from services.essay_lifecycle_service.implementations.essay_state_model import EssayState


class SQLiteEssayCrudOperations:
    """
    Handles basic CRUD operations for essay state in SQLite.

    Provides get, update, and create operations for individual essay records
    with proper JSON serialization and deserialization.
    """

    def __init__(self, database_path: str, timeout: float = 30.0) -> None:
        """
        Initialize the CRUD operations handler.

        Args:
            database_path: Path to the SQLite database file
            timeout: Database operation timeout in seconds
        """
        self.database_path = database_path
        self.timeout = timeout

    async def get_essay_state(self, essay_id: str) -> EssayState | None:
        """Retrieve essay state by ID."""
        async with aiosqlite.connect(self.database_path, timeout=self.timeout) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM essay_states WHERE essay_id = ?", (essay_id,)
            ) as cursor:
                row = await cursor.fetchone()

                if row is None:
                    return None

                return EssayState(
                    essay_id=row["essay_id"],
                    batch_id=row["batch_id"],
                    current_status=EssayStatus(row["current_status"]),
                    processing_metadata=json.loads(row["processing_metadata"]),
                    timeline={
                        k: datetime.fromisoformat(v) for k, v in json.loads(row["timeline"]).items()
                    },
                    storage_references={
                        ContentType(k): v for k, v in json.loads(row["storage_references"]).items()
                    },
                    created_at=datetime.fromisoformat(row["created_at"]),
                    updated_at=datetime.fromisoformat(row["updated_at"]),
                )

    async def update_essay_state(
        self, essay_id: str, new_status: EssayStatus, metadata: dict[str, Any]
    ) -> None:
        """Update essay state with new status and metadata."""
        async with aiosqlite.connect(self.database_path, timeout=self.timeout) as db:
            # First, get the current state
            current_state = await self.get_essay_state(essay_id)
            if current_state is None:
                raise ValueError(f"Essay {essay_id} not found")

            # Update the state
            current_state.update_status(new_status, metadata)

            # Save to database
            await db.execute(
                """
                UPDATE essay_states
                SET current_status = ?,
                    processing_metadata = ?,
                    timeline = ?,
                    updated_at = ?
                WHERE essay_id = ?
            """,
                (
                    current_state.current_status.value,
                    json.dumps(current_state.processing_metadata),
                    json.dumps({k: v.isoformat() for k, v in current_state.timeline.items()}),
                    current_state.updated_at.isoformat(),
                    essay_id,
                ),
            )

            await db.commit()

    async def create_essay_record(
        self,
        essay_ref: EntityReference | None = None,
        *,
        essay_id: str | None = None,
        slot_assignment: str | None = None,
        batch_id: str | None = None,
        initial_status: EssayStatus | None = None
    ) -> EssayState:
        """Create new essay record from entity reference or keyword arguments."""
        # Handle both calling patterns
        if essay_ref is not None:
            # Legacy pattern with EntityReference
            actual_essay_id = essay_ref.entity_id
            actual_batch_id = essay_ref.parent_id
            actual_status = EssayStatus.UPLOADED
        else:
            # New pattern with keyword arguments
            if essay_id is None:
                raise ValueError("essay_id is required when essay_ref is not provided")
            actual_essay_id = essay_id
            actual_batch_id = batch_id
            actual_status = initial_status or EssayStatus.READY_FOR_PROCESSING

        essay_state = EssayState(
            essay_id=actual_essay_id,
            batch_id=actual_batch_id,
            current_status=actual_status,
            timeline={actual_status.value: datetime.now(UTC)},
        )

        async with aiosqlite.connect(self.database_path, timeout=self.timeout) as db:
            await db.execute(
                """
                INSERT INTO essay_states (
                    essay_id, batch_id, current_status, processing_metadata,
                    timeline, storage_references, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    essay_state.essay_id,
                    essay_state.batch_id,
                    essay_state.current_status.value,
                    json.dumps(essay_state.processing_metadata),
                    json.dumps({k: v.isoformat() for k, v in essay_state.timeline.items()}),
                    json.dumps({k.value: v for k, v in essay_state.storage_references.items()}),
                    essay_state.created_at.isoformat(),
                    essay_state.updated_at.isoformat(),
                ),
            )

            await db.commit()

        return essay_state
