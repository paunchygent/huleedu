"""
Basic CRUD operations for Essay Lifecycle Service SQLite implementation.

Handles individual essay state operations including get, update, and create
for the SQLite-based persistence layer.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, cast

import aiosqlite
from common_core.domain_enums import ContentType

# EntityReference removed - using primitive parameters
from common_core.status_enums import EssayStatus
from huleedu_service_libs.error_handling import raise_resource_not_found

from services.essay_lifecycle_service.domain_models import EssayState


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
                from uuid import uuid4

                raise_resource_not_found(
                    service="essay_lifecycle_service",
                    operation="update_essay_state",
                    resource_type="Essay",
                    resource_id=essay_id,
                    correlation_id=uuid4(),
                )

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
        essay_id: str,
        batch_id: str | None = None,
        entity_type: str = "essay",
        initial_status: EssayStatus | None = None,
        slot_assignment: str | None = None,
    ) -> EssayState:
        """Create new essay record from primitive parameters."""
        # EntityReference removed - using primitive parameters only
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
                    json.dumps(
                        {k: cast(datetime, v).isoformat() for k, v in essay_state.timeline.items()}
                    ),
                    json.dumps({k.value: v for k, v in essay_state.storage_references.items()}),
                    cast(datetime, essay_state.created_at).isoformat(),
                    cast(datetime, essay_state.updated_at).isoformat(),
                ),
            )

            await db.commit()

        return essay_state
