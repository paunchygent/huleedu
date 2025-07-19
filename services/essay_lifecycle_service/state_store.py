"""
SQLite storage implementation for Essay Lifecycle Service.

Provides SQLite-based persistence implementation that serves as the
development/testing alternative to the PostgreSQL production implementation.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import aiosqlite
from common_core.domain_enums import ContentType
from common_core.metadata_models import EntityReference
from common_core.status_enums import EssayStatus

from services.essay_lifecycle_service.implementations.database_schema_manager import (
    SQLiteDatabaseSchemaManager,
)
from services.essay_lifecycle_service.implementations.essay_crud_operations import (
    SQLiteEssayCrudOperations,
)
from services.essay_lifecycle_service.implementations.essay_state_model import EssayState
from services.essay_lifecycle_service.protocols import EssayRepositoryProtocol

if TYPE_CHECKING:
    from services.essay_lifecycle_service.protocols import EssayState as ProtocolEssayState


class SQLiteEssayStateStore(EssayRepositoryProtocol):
    """
    SQLite-based implementation of essay state persistence.

    Provides async operations for managing essay state with proper
    database schema versioning and migration support.
    """

    def __init__(self, database_path: str, timeout: float = 30.0) -> None:
        """
        Initialize the SQLite state store.

        Args:
            database_path: Path to the SQLite database file
            timeout: Database operation timeout in seconds
        """
        self.database_path = database_path
        self.timeout = timeout
        self.schema_manager = SQLiteDatabaseSchemaManager(database_path, timeout)
        self.crud_ops = SQLiteEssayCrudOperations(database_path, timeout)

    async def initialize(self) -> None:
        """Initialize the database schema and migrations."""
        await self.schema_manager.initialize_schema()

    async def get_essay_state(self, essay_id: str) -> EssayState | None:
        """Retrieve essay state by ID."""
        return await self.crud_ops.get_essay_state(essay_id)

    async def update_essay_state(
        self,
        essay_id: str,
        new_status: EssayStatus,
        metadata: dict[str, Any],
        storage_reference: tuple[ContentType, str] | None = None,
    ) -> None:
        """Update essay state with new status and metadata."""
        await self.crud_ops.update_essay_state(essay_id, new_status, metadata)

    async def update_essay_status_via_machine(
        self,
        essay_id: str,
        new_status: EssayStatus,
        metadata: dict[str, Any],
        storage_reference: tuple[ContentType, str] | None = None,
    ) -> None:
        """Update essay state using status from state machine."""
        await self.crud_ops.update_essay_state(essay_id, new_status, metadata)

    async def create_essay_record(
        self,
        essay_ref: EntityReference | None = None,
        *,
        essay_id: str | None = None,
        slot_assignment: str | None = None,
        batch_id: str | None = None,
        initial_status: EssayStatus | None = None,
    ) -> EssayState:
        """Create new essay record from entity reference or keyword arguments."""
        return await self.crud_ops.create_essay_record(
            essay_ref=essay_ref,
            essay_id=essay_id,
            slot_assignment=slot_assignment,
            batch_id=batch_id,
            initial_status=initial_status,
        )

    async def list_essays_by_batch(self, batch_id: str) -> list[ProtocolEssayState]:
        """List all essays in a batch."""
        async with aiosqlite.connect(self.database_path, timeout=self.timeout) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM essay_states WHERE batch_id = ? ORDER BY created_at", (batch_id,)
            ) as cursor:
                rows = await cursor.fetchall()

                essays: list[ProtocolEssayState] = []
                for row in rows:
                    essay_state = EssayState(
                        essay_id=row["essay_id"],
                        batch_id=row["batch_id"],
                        current_status=EssayStatus(row["current_status"]),
                        processing_metadata=json.loads(row["processing_metadata"]),
                        timeline={
                            k: datetime.fromisoformat(v)
                            for k, v in json.loads(row["timeline"]).items()
                        },
                        storage_references={
                            ContentType(k): v
                            for k, v in json.loads(row["storage_references"]).items()
                        },
                        created_at=datetime.fromisoformat(row["created_at"]),
                        updated_at=datetime.fromisoformat(row["updated_at"]),
                    )
                    essays.append(essay_state)  # type: ignore[arg-type]

                return essays

    async def get_batch_status_summary(self, batch_id: str) -> dict[EssayStatus, int]:
        """Get status count breakdown for a batch."""
        async with aiosqlite.connect(self.database_path, timeout=self.timeout) as db:
            async with db.execute(
                "SELECT current_status, COUNT(*) as count "
                "FROM essay_states WHERE batch_id = ? "
                "GROUP BY current_status",
                (batch_id,),
            ) as cursor:
                rows = await cursor.fetchall()

                return {EssayStatus(row[0]): row[1] for row in rows}

    async def get_batch_summary_with_essays(
        self, batch_id: str
    ) -> tuple[list[EssayState], dict[EssayStatus, int]]:
        """Get both essays and status summary for a batch in single operation (prevents N+1 queries)."""
        # Fetch essays once
        essays = await self.list_essays_by_batch(batch_id)

        # Compute status summary from already-fetched essays
        summary: dict[EssayStatus, int] = {}
        for essay in essays:
            status = essay.current_status
            summary[status] = summary.get(status, 0) + 1

        return essays, summary  # type: ignore[return-value]

    async def get_essay_by_text_storage_id_and_batch_id(
        self, batch_id: str, text_storage_id: str
    ) -> EssayState | None:
        """Retrieve essay state by text_storage_id and batch_id for idempotency checking."""
        async with aiosqlite.connect(self.database_path, timeout=self.timeout) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT * FROM essay_states
                WHERE batch_id = ? AND json_extract(storage_references, '$.ORIGINAL_ESSAY') = ?
                """,
                (batch_id, text_storage_id),
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

    async def create_or_update_essay_state_for_slot_assignment(
        self,
        internal_essay_id: str,
        batch_id: str,
        text_storage_id: str,
        original_file_name: str,
        file_size: int,
        content_hash: str | None,
        initial_status: EssayStatus,
    ) -> EssayState:
        """Create or update essay state for slot assignment with content metadata."""
        # Check if essay already exists
        existing_state = await self.get_essay_state(internal_essay_id)
        current_time = datetime.now(UTC)

        # Prepare content metadata
        content_metadata = {
            "original_file_name": original_file_name,
            "file_size_bytes": file_size,
        }
        if content_hash is not None:
            content_metadata["content_md5_hash"] = content_hash

        # Prepare storage references with text_storage_id
        storage_references = {ContentType.ORIGINAL_ESSAY: text_storage_id}

        if existing_state is not None:
            # Update existing essay state
            existing_state.current_status = initial_status
            existing_state.updated_at = current_time
            existing_state.timeline[initial_status.value] = current_time
            existing_state.processing_metadata.update(content_metadata)
            existing_state.storage_references.update(storage_references)

            async with aiosqlite.connect(self.database_path, timeout=self.timeout) as db:
                await db.execute(
                    """
                    UPDATE essay_states
                    SET current_status = ?,
                        processing_metadata = ?,
                        timeline = ?,
                        storage_references = ?,
                        updated_at = ?
                    WHERE essay_id = ?
                """,
                    (
                        existing_state.current_status.value,
                        json.dumps(existing_state.processing_metadata),
                        json.dumps({k: v.isoformat() for k, v in existing_state.timeline.items()}),
                        json.dumps(
                            {k.value: v for k, v in existing_state.storage_references.items()}
                        ),
                        existing_state.updated_at.isoformat(),
                        internal_essay_id,
                    ),
                )
                await db.commit()

            return existing_state
        else:
            # Create new essay state
            essay_state = EssayState(
                essay_id=internal_essay_id,
                batch_id=batch_id,
                current_status=initial_status,
                processing_metadata=content_metadata,
                timeline={initial_status.value: current_time},
                storage_references=storage_references,
                created_at=current_time,
                updated_at=current_time,
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

    async def list_essays_by_batch_and_phase(
        self, batch_id: str, phase_name: str
    ) -> list[ProtocolEssayState]:
        """List all essays in a batch that are part of a specific processing phase."""
        async with aiosqlite.connect(self.database_path, timeout=self.timeout) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM essay_states WHERE batch_id = ? ORDER BY created_at", (batch_id,)
            ) as cursor:
                rows = await cursor.fetchall()

                essay_states: list[ProtocolEssayState] = []
                for row in rows:
                    processing_metadata = json.loads(row["processing_metadata"])

                    # Check if this essay belongs to the specified phase
                    # Phase information is stored in processing_metadata when BOS
                    # commands are processed
                    current_phase = processing_metadata.get("current_phase")
                    commanded_phases = processing_metadata.get("commanded_phases", [])

                    # Essay belongs to this phase if it's currently in this phase
                    # or was commanded for this phase
                    if current_phase == phase_name or phase_name in commanded_phases:
                        essay_state = EssayState(
                            essay_id=row["essay_id"],
                            batch_id=row["batch_id"],
                            current_status=EssayStatus(row["current_status"]),
                            processing_metadata=processing_metadata,
                            timeline={
                                k: datetime.fromisoformat(v)
                                for k, v in json.loads(row["timeline"]).items()
                            },
                            storage_references={
                                ContentType(k): v
                                for k, v in json.loads(row["storage_references"]).items()
                            },
                            created_at=datetime.fromisoformat(row["created_at"]),
                            updated_at=datetime.fromisoformat(row["updated_at"]),
                        )
                        essay_states.append(essay_state)  # type: ignore[arg-type]

                return essay_states
