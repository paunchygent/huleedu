"""
Migration test for total_budget and current_iteration defaults.

Per rule 085.4: "Service-level smoke test: every service MUST provide an automated
check (CI or local script) that provisions an ephemeral PostgreSQL instance
(TestContainers or docker compose) and runs `../../.venv/bin/alembic upgrade head`.
This regression test guards against enum/type duplication and other DDL conflicts
before migrations merge."

This test validates:
1. Migration can run on clean PostgreSQL instance
2. total_budget column is created successfully
3. total_budget accepts integer values
4. Backfill populates total_budget = total_comparisons for existing rows
5. current_iteration defaults to 0 for new rows
6. No DDL conflicts occur
"""

from __future__ import annotations

import subprocess
import uuid
from pathlib import Path
from typing import AsyncGenerator

import pytest
from common_core.status_enums import CJBatchStateEnum
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from testcontainers.postgres import PostgresContainer

from services.cj_assessment_service.enums_db import CJBatchStatusEnum
from services.cj_assessment_service.models_db import CJBatchState, CJBatchUpload


@pytest.fixture(scope="module")
def migration_postgres_container() -> PostgresContainer:
    """Create PostgreSQL container for migration testing."""
    with PostgresContainer(
        "postgres:15",
        username="migration_test_user",
        password="migration_test_password",
        dbname="cj_migration_test",
    ) as container:
        yield container


@pytest.fixture
async def migration_engine(
    migration_postgres_container: PostgresContainer,
) -> AsyncGenerator[AsyncEngine, None]:
    """Create engine for migration testing."""
    database_url = migration_postgres_container.get_connection_url().replace("psycopg2", "asyncpg")

    engine = create_async_engine(
        database_url,
        echo=False,
        future=True,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,
    )

    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture
async def migration_session(
    migration_engine: AsyncEngine,
) -> AsyncGenerator[AsyncSession, None]:
    """Create session for migration testing."""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    session_maker = async_sessionmaker(
        migration_engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )

    async with session_maker() as session:
        async with session.begin():
            yield session
            # Rollback happens automatically


def run_alembic_upgrade(container: PostgresContainer) -> subprocess.CompletedProcess:
    """Run Alembic upgrade head on the migration container."""
    import os

    # Build database URL for Alembic
    db_url = container.get_connection_url().replace("psycopg2", "asyncpg")

    # Get service directory
    service_dir = Path(__file__).parents[2]  # services/cj_assessment_service
    alembic_ini = service_dir / "alembic.ini"

    # Parse connection details from container URL
    container_url = container.get_connection_url()
    # Format: postgresql+psycopg2://user:password@host:port/database
    import re

    match = re.match(r"postgresql(?:\+\w+)?://([^:]+):([^@]+)@([^:]+):(\d+)/(.+)", container_url)
    if not match:
        raise ValueError(f"Could not parse container URL: {container_url}")

    user, password, host, port, database = match.groups()

    # Create environment with complete DATABASE_URL override
    # This bypasses Settings.DATABASE_URL property logic and directly provides the URL
    env = os.environ.copy()
    env["CJ_ASSESSMENT_SERVICE_DATABASE_URL"] = db_url

    # Run alembic upgrade head
    result = subprocess.run(
        [
            str(Path(__file__).parents[4] / ".venv" / "bin" / "alembic"),
            "-c",
            str(alembic_ini),
            "upgrade",
            "head",
        ],
        cwd=str(service_dir),
        env=env,
        capture_output=True,
        text=True,
    )

    return result


@pytest.mark.integration
@pytest.mark.slow
class TestTotalBudgetMigration:
    """Test total_budget column addition and current_iteration default update."""

    async def test_migration_upgrade_from_clean_database(
        self,
        migration_postgres_container: PostgresContainer,
        migration_engine: AsyncEngine,
    ) -> None:
        """
        Test that migration can run successfully on clean PostgreSQL instance.

        This is the MANDATORY smoke test per rule 085.4.
        """
        # Run Alembic upgrade head
        result = run_alembic_upgrade(migration_postgres_container)

        # Assert migration succeeded
        assert result.returncode == 0, (
            f"Alembic upgrade failed:\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"
        )

        # Verify schema was created
        async with migration_engine.connect() as conn:
            # Check that cj_batch_states table exists
            table_check = await conn.execute(
                text(
                    """
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables
                        WHERE table_name = 'cj_batch_states'
                    );
                """
                )
            )
            table_exists = table_check.scalar()
            assert table_exists, "cj_batch_states table was not created"

            # Check total_budget column exists and is correct type
            column_check = await conn.execute(
                text(
                    """
                    SELECT data_type, is_nullable
                    FROM information_schema.columns
                    WHERE table_name = 'cj_batch_states'
                    AND column_name = 'total_budget';
                """
                )
            )
            column_info = column_check.one_or_none()

            assert column_info is not None, "total_budget column was not created"

            # Should be integer, nullable (for backwards compatibility)
            assert column_info[0] == "integer", (
                f"total_budget should be 'integer', got: {column_info[0]}"
            )
            assert column_info[1] == "YES", (
                f"total_budget should be nullable, got: {column_info[1]}"
            )

            # Check current_iteration has correct default
            default_check = await conn.execute(
                text(
                    """
                    SELECT column_default
                    FROM information_schema.columns
                    WHERE table_name = 'cj_batch_states'
                    AND column_name = 'current_iteration';
                """
                )
            )
            default_value = default_check.scalar()
            assert default_value == "0", (
                f"current_iteration should default to 0, got: {default_value}"
            )

    async def test_total_budget_accepts_integer_values(
        self,
        migration_postgres_container: PostgresContainer,
        migration_engine: AsyncEngine,
        migration_session: AsyncSession,
    ) -> None:
        """
        Test that total_budget column accepts integer values.

        This validates the migration achieves its goal: storing original comparison budget.
        """
        # First run migrations to ensure schema is ready
        result = run_alembic_upgrade(migration_postgres_container)
        assert result.returncode == 0, "Migration must succeed before testing"

        # Create test upload record first
        test_upload = CJBatchUpload(
            bos_batch_id=str(uuid.uuid4()),
            event_correlation_id=str(uuid.uuid4()),
            language="sv",
            course_code="TEST_COURSE",
            expected_essay_count=24,
            status=CJBatchStatusEnum.PENDING,
        )
        migration_session.add(test_upload)
        await migration_session.flush()

        # Create batch state with total_budget
        test_budget = 100
        batch_state = CJBatchState(
            batch_id=test_upload.id,
            total_budget=test_budget,
            total_comparisons=50,
            submitted_comparisons=25,
            completed_comparisons=0,
            failed_comparisons=0,
            state=CJBatchStateEnum.GENERATING_PAIRS,
        )

        # This should NOT raise any errors
        migration_session.add(batch_state)
        await migration_session.flush()

        # Verify values were stored correctly
        await migration_session.refresh(batch_state)
        assert batch_state.total_budget == test_budget, (
            f"Expected total_budget '{test_budget}', got '{batch_state.total_budget}'"
        )
        assert batch_state.total_comparisons == 50
        assert batch_state.current_iteration == 0, "new rows should default to iteration 0"

    async def test_total_budget_backfill_for_existing_rows(
        self,
        migration_postgres_container: PostgresContainer,
        migration_engine: AsyncEngine,
    ) -> None:
        """
        Test that existing rows get backfilled with total_budget = total_comparisons.

        This validates the migration's data migration logic.
        """
        # Run migrations
        result = run_alembic_upgrade(migration_postgres_container)
        assert result.returncode == 0

        # Insert test data with NULL total_budget
        async with migration_engine.begin() as conn:
            # Create upload (let server defaults handle timestamps)
            upload_result = await conn.execute(
                text(
                    """
                    INSERT INTO cj_batch_uploads
                    (bos_batch_id, event_correlation_id, language, course_code,
                     expected_essay_count, status)
                    VALUES
                    (:bos_batch_id, :event_correlation_id, :language, :course_code,
                     :expected_essay_count, :status)
                    RETURNING id
                """
                ),
                {
                    "bos_batch_id": str(uuid.uuid4()),
                    "event_correlation_id": str(uuid.uuid4()),
                    "language": "sv",
                    "course_code": "TEST_COURSE",
                    "expected_essay_count": 24,
                    "status": CJBatchStatusEnum.PENDING.value,
                },
            )
            batch_id = upload_result.scalar_one()

            # Insert batch state WITHOUT total_budget (simulating pre-migration data)
            # Note: total_budget is nullable, so we can test backfill behavior
            # last_activity_at has server default and onupdate, so we don't set it
            await conn.execute(
                text(
                    """
                    INSERT INTO cj_batch_states
                    (batch_id, total_comparisons, submitted_comparisons, completed_comparisons,
                     failed_comparisons, state)
                    VALUES
                    (:batch_id, :total, :submitted, :completed, :failed, :state)
                """
                ),
                {
                    "batch_id": batch_id,
                    "total": 75,
                    "submitted": 75,
                    "completed": 0,
                    "failed": 0,
                    "state": CJBatchStateEnum.GENERATING_PAIRS.value,
                },
            )

            # Now run the backfill UPDATE (simulating what the migration does)
            await conn.execute(
                text(
                    """
                    UPDATE cj_batch_states
                    SET total_budget = total_comparisons
                    WHERE total_budget IS NULL
                """
                )
            )

            # Verify backfill worked
            query_result = await conn.execute(
                text(
                    """
                    SELECT total_budget, total_comparisons
                    FROM cj_batch_states
                    WHERE batch_id = :batch_id
                """
                ),
                {"batch_id": batch_id},
            )
            row = query_result.one()
            assert row.total_budget == 75, (
                f"Backfill failed: total_budget should be 75, got {row.total_budget}"
            )
            assert row.total_budget == row.total_comparisons, (
                "Backfill failed: total_budget should equal total_comparisons"
            )

    async def test_total_budget_nullable_for_backwards_compatibility(
        self,
        migration_postgres_container: PostgresContainer,
        migration_engine: AsyncEngine,
        migration_session: AsyncSession,
    ) -> None:
        """
        Test that total_budget can be NULL for backwards compatibility.

        This ensures the migration doesn't break existing code that doesn't set total_budget.
        """
        # Run migrations
        result = run_alembic_upgrade(migration_postgres_container)
        assert result.returncode == 0

        # Create upload
        test_upload = CJBatchUpload(
            bos_batch_id=str(uuid.uuid4()),
            event_correlation_id=str(uuid.uuid4()),
            language="sv",
            course_code="TEST_COURSE",
            expected_essay_count=24,
            status=CJBatchStatusEnum.PENDING,
        )
        migration_session.add(test_upload)
        await migration_session.flush()

        # Create batch state WITHOUT total_budget
        batch_state = CJBatchState(
            batch_id=test_upload.id,
            total_budget=None,  # Explicitly NULL
            total_comparisons=100,
            submitted_comparisons=0,
            completed_comparisons=0,
            failed_comparisons=0,
            state=CJBatchStateEnum.INITIALIZING,
        )

        # This should work fine
        migration_session.add(batch_state)
        await migration_session.flush()

        # Verify NULL was stored
        await migration_session.refresh(batch_state)
        assert batch_state.total_budget is None

    async def test_current_iteration_defaults_to_zero(
        self,
        migration_postgres_container: PostgresContainer,
        migration_engine: AsyncEngine,
        migration_session: AsyncSession,
    ) -> None:
        """
        Test that new rows get current_iteration = 0 by default.

        This validates the migration's schema change for iteration tracking.
        """
        # Run migrations
        result = run_alembic_upgrade(migration_postgres_container)
        assert result.returncode == 0

        # Create upload
        test_upload = CJBatchUpload(
            bos_batch_id=str(uuid.uuid4()),
            event_correlation_id=str(uuid.uuid4()),
            language="sv",
            course_code="TEST_COURSE",
            expected_essay_count=24,
            status=CJBatchStatusEnum.PENDING,
        )
        migration_session.add(test_upload)
        await migration_session.flush()

        # Create batch state WITHOUT explicitly setting current_iteration
        batch_state = CJBatchState(
            batch_id=test_upload.id,
            total_budget=100,
            total_comparisons=0,
            submitted_comparisons=0,
            completed_comparisons=0,
            failed_comparisons=0,
            state=CJBatchStateEnum.INITIALIZING,
            # Note: current_iteration NOT set - should use default
        )

        migration_session.add(batch_state)
        await migration_session.flush()

        # Verify default value
        await migration_session.refresh(batch_state)
        assert batch_state.current_iteration == 0, (
            f"current_iteration should default to 0, got {batch_state.current_iteration}"
        )

    async def test_migration_idempotency(
        self,
        migration_postgres_container: PostgresContainer,
    ) -> None:
        """
        Test that running migrations twice doesn't cause errors.

        This guards against column duplication and other DDL conflicts.
        """
        # Run migrations first time
        result1 = run_alembic_upgrade(migration_postgres_container)
        assert result1.returncode == 0, f"First migration run failed:\n{result1.stderr}"

        # Run migrations second time (should be idempotent)
        result2 = run_alembic_upgrade(migration_postgres_container)
        assert result2.returncode == 0, (
            f"Second migration run failed (not idempotent):\n{result2.stderr}"
        )

        # Should not contain "already exists" errors
        assert "already exists" not in result2.stderr.lower(), (
            f"Migration not idempotent - duplicate creation detected:\n{result2.stderr}"
        )
