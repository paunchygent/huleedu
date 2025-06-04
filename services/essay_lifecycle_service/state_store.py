"""
Essay state storage implementation for the Essay Lifecycle Service.

This module provides the essay state model and SQLite-based persistence layer
for managing essay lifecycle states and transitions.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import aiosqlite
from common_core.enums import ContentType, EssayStatus
from common_core.metadata_models import EntityReference
from pydantic import BaseModel, Field


class EssayState(BaseModel):
    """
    Essay state data model for tracking essay processing lifecycle.

    This model represents the complete state of an essay as it progresses
    through the HuleEdu processing pipeline.
    """

    essay_id: str
    batch_id: str | None = None
    current_status: EssayStatus
    processing_metadata: dict[str, Any] = Field(default_factory=dict)
    timeline: dict[str, datetime] = Field(default_factory=dict)
    storage_references: dict[ContentType, str] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Config:
        """Pydantic configuration."""

        json_encoders = {
            datetime: lambda v: v.isoformat(),
        }

    def update_status(
        self, new_status: EssayStatus, metadata: dict[str, Any] | None = None
    ) -> None:
        """Update essay status and metadata."""
        self.current_status = new_status
        self.updated_at = datetime.now(UTC)
        self.timeline[new_status.value] = self.updated_at

        if metadata:
            self.processing_metadata.update(metadata)


class SQLiteEssayStateStore:
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

    async def initialize(self) -> None:
        """Initialize the database schema and migrations."""
        async with aiosqlite.connect(self.database_path, timeout=self.timeout) as db:
            # Enable foreign keys
            await db.execute("PRAGMA foreign_keys = ON")

            # Create schema version table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS schema_version (
                    version INTEGER PRIMARY KEY,
                    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Create essay_states table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS essay_states (
                    essay_id TEXT PRIMARY KEY,
                    batch_id TEXT,
                    current_status TEXT NOT NULL,
                    processing_metadata TEXT NOT NULL DEFAULT '{}',
                    timeline TEXT NOT NULL DEFAULT '{}',
                    storage_references TEXT NOT NULL DEFAULT '{}',
                    created_at TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP NOT NULL
                )
            """)

            # Create index for batch queries
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_essay_states_batch_id
                ON essay_states(batch_id)
            """)

            # Create index for status queries
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_essay_states_status
                ON essay_states(current_status)
            """)

            # Set current schema version
            await db.execute("""
                INSERT OR IGNORE INTO schema_version (version) VALUES (1)
            """)

            await db.commit()

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

    async def update_essay_status_via_machine(
        self, essay_id: str, new_status: EssayStatus, metadata: dict[str, Any]
    ) -> None:
        """Update essay state using status from state machine."""
        await self.update_essay_state(essay_id, new_status, metadata)

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

    async def list_essays_by_batch(self, batch_id: str) -> list[EssayState]:
        """List all essays in a batch."""
        async with aiosqlite.connect(self.database_path, timeout=self.timeout) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM essay_states WHERE batch_id = ? ORDER BY created_at", (batch_id,)
            ) as cursor:
                rows = await cursor.fetchall()

                return [
                    EssayState(
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
                    for row in rows
                ]

    async def get_batch_status_summary(self, batch_id: str) -> dict[EssayStatus, int]:
        """Get status count breakdown for a batch."""
        async with aiosqlite.connect(self.database_path, timeout=self.timeout) as db:
            async with db.execute(
                "SELECT current_status, COUNT(*) as count FROM essay_states WHERE batch_id = ? GROUP BY current_status",
                (batch_id,),
            ) as cursor:
                rows = await cursor.fetchall()

                return {EssayStatus(row[0]): row[1] for row in rows}

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

    async def list_essays_by_batch_and_phase(self, batch_id: str, phase_name: str) -> list[EssayState]:
        """List all essays in a batch that are part of a specific processing phase."""
        async with aiosqlite.connect(self.database_path, timeout=self.timeout) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM essay_states WHERE batch_id = ? ORDER BY created_at", (batch_id,)
            ) as cursor:
                rows = await cursor.fetchall()

                essay_states = []
                for row in rows:
                    processing_metadata = json.loads(row["processing_metadata"])

                    # Check if this essay belongs to the specified phase
                    # Phase information is stored in processing_metadata when BOS commands are processed
                    current_phase = processing_metadata.get("current_phase")
                    commanded_phases = processing_metadata.get("commanded_phases", [])

                    # Essay belongs to this phase if it's currently in this phase or was commanded for this phase
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
                        essay_states.append(essay_state)

                return essay_states
