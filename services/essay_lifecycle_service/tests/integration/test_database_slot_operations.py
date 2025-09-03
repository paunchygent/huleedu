"""Integration tests for DatabaseSlotOperations (DB-only slot assignment).

Uses Postgres testcontainer to validate atomic assignment, idempotency,
and exhaustion behavior without Redis.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from common_core.domain_enums import CourseCode
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer

from services.essay_lifecycle_service.implementations.batch_expectation import (
    BatchExpectation,
)
from services.essay_lifecycle_service.implementations.batch_tracker_persistence import (
    BatchTrackerPersistence,
)
from services.essay_lifecycle_service.implementations.database_slot_operations import (
    DatabaseSlotOperations,
)
from services.essay_lifecycle_service.models_db import Base


@pytest.mark.integration
@pytest.mark.asyncio
async def test_db_slot_assignment_idempotency_and_exhaustion() -> None:
    """Validate assignment returns essay IDs, is idempotent, and handles exhaustion."""
    batch_id = "batch-test-001"
    essay_ids = ["e-001", "e-002", "e-003"]

    with PostgresContainer("postgres:15-alpine") as pg:
        pg_connection_url = pg.get_connection_url()
        if "+psycopg2://" in pg_connection_url:
            pg_connection_url = pg_connection_url.replace("+psycopg2://", "+asyncpg://")
        elif "postgresql://" in pg_connection_url:
            pg_connection_url = pg_connection_url.replace("postgresql://", "postgresql+asyncpg://")

        engine = create_async_engine(pg_connection_url)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        session_factory = async_sessionmaker(engine, expire_on_commit=False)

        # Pre-seed tracker and inventory via persistence
        persistence = BatchTrackerPersistence(engine)
        expectation = BatchExpectation(
            batch_id=batch_id,
            expected_essay_ids=frozenset(essay_ids),
            expected_count=len(essay_ids),
            course_code=CourseCode.ENG5,
            essay_instructions="Test",
            user_id="user-1",
            org_id=None,
            correlation_id=uuid4(),
            created_at=datetime.now(UTC),
            timeout_seconds=3600,
        )
        await persistence.persist_batch_expectation(expectation)

        slot_ops = DatabaseSlotOperations(session_factory)

        # Assign first content
        essay_id1 = await slot_ops.assign_slot_atomic(
            batch_id,
            {"text_storage_id": "ts-1", "original_file_name": "a.txt"},
        )
        assert essay_id1 in essay_ids

        # Idempotent re-assign of same content returns same essay_id
        essay_id1_repeat = await slot_ops.assign_slot_atomic(
            batch_id,
            {"text_storage_id": "ts-1", "original_file_name": "a.txt"},
        )
        assert essay_id1_repeat == essay_id1

        # Assign remaining
        essay_id2 = await slot_ops.assign_slot_atomic(
            batch_id,
            {"text_storage_id": "ts-2", "original_file_name": "b.txt"},
        )
        essay_id3 = await slot_ops.assign_slot_atomic(
            batch_id,
            {"text_storage_id": "ts-3", "original_file_name": "c.txt"},
        )
        assert {essay_id1, essay_id2, essay_id3} == set(essay_ids)

        # Exhaustion: next assignment should return None
        no_slot = await slot_ops.assign_slot_atomic(
            batch_id,
            {"text_storage_id": "ts-4", "original_file_name": "d.txt"},
        )
        assert no_slot is None

        await engine.dispose()
