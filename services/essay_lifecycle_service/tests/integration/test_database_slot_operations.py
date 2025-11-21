"""Integration tests for Option B single-statement assignment (DB-only).

Uses Postgres testcontainer to validate atomic assignment, idempotency,
and exhaustion behavior using essay_states as the only inventory.
"""

from __future__ import annotations

import asyncio
from collections import Counter
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from common_core.domain_enums import ContentType, CourseCode
from common_core.metadata_models import StorageReferenceMetadata
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer

from services.essay_lifecycle_service.implementations.assignment_sql import (
    assign_via_essay_states_immediate_commit,
)
from services.essay_lifecycle_service.implementations.batch_expectation import (
    BatchExpectation,
)
from services.essay_lifecycle_service.implementations.batch_tracker_persistence import (
    BatchTrackerPersistence,
)
from services.essay_lifecycle_service.implementations.essay_repository_postgres_impl import (
    PostgreSQLEssayRepository,
)
from services.essay_lifecycle_service.models_db import Base


def make_prompt_ref(label: str) -> StorageReferenceMetadata:
    prompt_ref = StorageReferenceMetadata()
    prompt_ref.add_reference(ContentType.STUDENT_PROMPT_TEXT, label)
    return prompt_ref


@pytest.mark.integration
@pytest.mark.asyncio
async def test_option_b_assignment_idempotency_and_exhaustion() -> None:
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
            student_prompt_ref=make_prompt_ref("prompt-option-b"),
            user_id="user-1",
            org_id=None,
            correlation_id=uuid4(),
            created_at=datetime.now(UTC),
            timeout_seconds=3600,
        )
        async with session_factory() as session:
            async with session.begin():
                await persistence.persist_batch_expectation(expectation, session=session)
        # Option B requires essay rows to exist in essay_states for inventory
        repository = PostgreSQLEssayRepository(session_factory)
        essay_data: list[dict[str, str | None]] = [
            {"entity_id": eid, "parent_id": batch_id, "entity_type": "essay"} for eid in essay_ids
        ]
        await repository.create_essay_records_batch(essay_data=essay_data, correlation_id=uuid4())

        # Assign first content via Option B
        was_created1, essay_id1 = await assign_via_essay_states_immediate_commit(
            session_factory=session_factory,
            batch_id=batch_id,
            text_storage_id="ts-1",
            original_file_name="a.txt",
            file_size=123,
            content_hash=None,
        )
        assert essay_id1 in essay_ids
        assert was_created1 is True

        # Idempotent re-assign of same content returns same essay_id
        was_created_repeat, essay_id1_repeat = await assign_via_essay_states_immediate_commit(
            session_factory=session_factory,
            batch_id=batch_id,
            text_storage_id="ts-1",
            original_file_name="a.txt",
            file_size=123,
            content_hash=None,
        )
        assert essay_id1_repeat == essay_id1
        assert was_created_repeat is False

        # Assign remaining
        _, essay_id2 = await assign_via_essay_states_immediate_commit(
            session_factory=session_factory,
            batch_id=batch_id,
            text_storage_id="ts-2",
            original_file_name="b.txt",
            file_size=123,
            content_hash=None,
        )
        _, essay_id3 = await assign_via_essay_states_immediate_commit(
            session_factory=session_factory,
            batch_id=batch_id,
            text_storage_id="ts-3",
            original_file_name="c.txt",
            file_size=123,
            content_hash=None,
        )
        assert {essay_id1, essay_id2, essay_id3} == set(essay_ids)

        # Exhaustion: next assignment should return None
        was_created4, no_slot = await assign_via_essay_states_immediate_commit(
            session_factory=session_factory,
            batch_id=batch_id,
            text_storage_id="ts-4",
            original_file_name="d.txt",
            file_size=123,
            content_hash=None,
        )
    assert was_created4 is False
    assert no_slot is None

    await engine.dispose()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_option_b_assignment_retries_when_slots_locked() -> None:
    """Ensure Option B retries when slots are temporarily lock-starved by concurrency."""

    batch_id = "batch-retry-001"
    essay_ids = ["e-001", "e-002", "e-003"]
    concurrent_calls = 20
    shared_text_storage_id = "ts-lock-retry"

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
            student_prompt_ref=make_prompt_ref("prompt-option-b-retry"),
            user_id="user-1",
            org_id=None,
            correlation_id=uuid4(),
            created_at=datetime.now(UTC),
            timeout_seconds=3600,
        )
        async with session_factory() as session:
            async with session.begin():
                await persistence.persist_batch_expectation(expectation, session=session)

        repository = PostgreSQLEssayRepository(session_factory)
        essay_data: list[dict[str, str | None]] = [
            {"entity_id": eid, "parent_id": batch_id, "entity_type": "essay"} for eid in essay_ids
        ]
        await repository.create_essay_records_batch(essay_data=essay_data, correlation_id=uuid4())

        async def do_assign() -> tuple[bool, str | None]:
            return await assign_via_essay_states_immediate_commit(
                session_factory=session_factory,
                batch_id=batch_id,
                text_storage_id=shared_text_storage_id,
                original_file_name="shared.txt",
                file_size=456,
                content_hash=None,
            )

        results = await asyncio.gather(*[do_assign() for _ in range(concurrent_calls)])

        # All calls should succeed idempotently and refer to the same essay id
        essay_ids_seen = [essay_id for _, essay_id in results if essay_id is not None]
        statuses = Counter(results)

        # Exactly one slot consumed, others treated as idempotent hits on same content
        assert len(set(essay_ids_seen)) == 1
        assert len(essay_ids_seen) == concurrent_calls

        # There must be exactly one (True, essay_id) and the rest (False, same essay_id)
        most_common = statuses.most_common()
        assert most_common[0][0][0] is False  # False, essay_id occurrences dominate
        assert any(status[0] is True for status, _ in most_common)

        # No call should return (False, None)
        assert (False, None) not in statuses

        await engine.dispose()
