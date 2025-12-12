"""
Migration test for error_code ENUM to VARCHAR conversion.

Per rule 085.4: "Service-level smoke test: every service MUST provide an automated
check (CI or local script) that provisions an ephemeral PostgreSQL instance
(TestContainers or docker compose) and runs `../../.venv/bin/alembic upgrade head`.
This regression test guards against enum/type duplication and other DDL conflicts
before migrations merge."

This test validates:
1. Migration can run on clean PostgreSQL instance
2. error_code column accepts VARCHAR values (ErrorCode enum strings)
3. No ENUM duplication errors occur
"""

from __future__ import annotations

import subprocess
import uuid
from pathlib import Path
from typing import AsyncGenerator

import pytest
from common_core.error_enums import ErrorCode
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from testcontainers.postgres import PostgresContainer

from services.cj_assessment_service.enums_db import CJBatchStatusEnum
from services.cj_assessment_service.models_db import (
    CJBatchUpload,
    ComparisonPair,
    ProcessedEssay,
)


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
class TestErrorCodeMigration:
    """Test error_code ENUM to VARCHAR migration."""

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
            # Check that cj_comparison_pairs table exists
            table_check = await conn.execute(
                text(
                    """
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables
                        WHERE table_name = 'cj_comparison_pairs'
                    );
                """
                )
            )
            table_exists = table_check.scalar()
            assert table_exists, "cj_comparison_pairs table was not created"

            # Check error_code column type
            column_check = await conn.execute(
                text(
                    """
                    SELECT data_type, character_maximum_length
                    FROM information_schema.columns
                    WHERE table_name = 'cj_comparison_pairs'
                    AND column_name = 'error_code';
                """
                )
            )
            column_info = column_check.one()

            # After migration, should be VARCHAR(100), not ENUM
            assert column_info[0] == "character varying", (
                f"error_code column should be 'character varying', got: {column_info[0]}"
            )
            assert column_info[1] == 100, (
                f"error_code column should have max length 100, got: {column_info[1]}"
            )

    async def test_error_code_accepts_string_values(
        self,
        migration_postgres_container: PostgresContainer,
        migration_engine: AsyncEngine,
        migration_session: AsyncSession,
    ) -> None:
        """
        Test that error_code column accepts ErrorCode enum values as strings.

        This validates the migration achieves its goal: accepting string error codes
        without type mismatch errors.
        """
        # First run migrations to ensure schema is ready
        result = run_alembic_upgrade(migration_postgres_container)
        assert result.returncode == 0, "Migration must succeed before testing"

        # Create test data with error_code
        test_error_code = ErrorCode.RATE_LIMIT.value  # String value

        # First create a batch upload (parent record required by foreign key)
        batch = CJBatchUpload(
            bos_batch_id="test-batch-id",
            event_correlation_id=str(uuid.uuid4()),
            language="en",
            course_code="TEST101",
            expected_essay_count=10,
            status=CJBatchStatusEnum.PENDING,
        )
        migration_session.add(batch)
        await migration_session.flush()

        # Create processed essays (required by foreign key)
        essay_a = ProcessedEssay(
            els_essay_id="essay-a-id",
            cj_batch_id=batch.id,
            text_storage_id="storage-a",
            assessment_input_text="Test essay A text",
        )
        essay_b = ProcessedEssay(
            els_essay_id="essay-b-id",
            cj_batch_id=batch.id,
            text_storage_id="storage-b",
            assessment_input_text="Test essay B text",
        )
        migration_session.add(essay_a)
        migration_session.add(essay_b)
        await migration_session.flush()

        # Insert comparison pair with error_code using SQLAlchemy model
        comparison = ComparisonPair(
            cj_batch_id=batch.id,
            essay_a_els_id=essay_a.els_essay_id,
            essay_b_els_id=essay_b.els_essay_id,
            prompt_text="test prompt",
            error_code=test_error_code,
        )

        # This should NOT raise "column is of type errorcode" error
        migration_session.add(comparison)
        await migration_session.flush()

        # Verify value was stored correctly
        await migration_session.refresh(comparison)
        stored_error_code = comparison.error_code

        assert stored_error_code == test_error_code, (
            f"Expected error_code '{test_error_code}', got '{stored_error_code}'"
        )

    async def test_error_code_accepts_all_error_enum_values(
        self,
        migration_postgres_container: PostgresContainer,
        migration_engine: AsyncEngine,
    ) -> None:
        """
        Test that error_code column accepts all ErrorCode enum values.

        This validates flexibility: new error codes can be added without migration.
        """
        # Run migrations
        result = run_alembic_upgrade(migration_postgres_container)
        assert result.returncode == 0

        # Test a representative sample of error codes
        test_cases = [
            ErrorCode.UNKNOWN_ERROR,
            ErrorCode.RATE_LIMIT,
            ErrorCode.TIMEOUT,
            ErrorCode.PARSING_ERROR,
            ErrorCode.VALIDATION_ERROR,
            # New error codes not in original ENUM
            ErrorCode.AUTHORIZATION_ERROR,
            ErrorCode.LLM_PROVIDER_SERVICE_ERROR,
        ]

        # Use async session to properly handle SQLAlchemy models
        from sqlalchemy.ext.asyncio import async_sessionmaker

        session_maker = async_sessionmaker(
            migration_engine,
            expire_on_commit=False,
            class_=AsyncSession,
        )

        async with session_maker() as session:
            async with session.begin():
                # First create a batch upload (parent record required by foreign key)
                batch = CJBatchUpload(
                    bos_batch_id="test-batch-id",
                    event_correlation_id=str(uuid.uuid4()),
                    language="en",
                    course_code="TEST101",
                    expected_essay_count=10,
                    status=CJBatchStatusEnum.PENDING,
                )
                session.add(batch)
                await session.flush()

                # Create processed essays (required by foreign key)
                essay_a = ProcessedEssay(
                    els_essay_id="essay-a",
                    cj_batch_id=batch.id,
                    text_storage_id="storage-a",
                    assessment_input_text="Test essay A text",
                )
                essay_b = ProcessedEssay(
                    els_essay_id="essay-b",
                    cj_batch_id=batch.id,
                    text_storage_id="storage-b",
                    assessment_input_text="Test essay B text",
                )
                session.add(essay_a)
                session.add(essay_b)
                await session.flush()

                for error_code in test_cases:
                    # Insert with this error code using SQLAlchemy model
                    comparison = ComparisonPair(
                        cj_batch_id=batch.id,
                        essay_a_els_id=essay_a.els_essay_id,
                        essay_b_els_id=essay_b.els_essay_id,
                        prompt_text="prompt",
                        error_code=error_code.value,
                    )
                    session.add(comparison)
                    await session.flush()

                    # Verify it was stored
                    await session.refresh(comparison)
                    assert comparison.error_code == error_code.value

    async def test_no_enum_type_exists_after_migration(
        self,
        migration_postgres_container: PostgresContainer,
        migration_engine: AsyncEngine,
    ) -> None:
        """
        Test that errorcode ENUM type is dropped after migration.

        This prevents "type already exists" errors and validates cleanup.
        """
        # Run migrations
        result = run_alembic_upgrade(migration_postgres_container)
        assert result.returncode == 0

        # Check that errorcode ENUM type does NOT exist
        async with migration_engine.connect() as conn:
            enum_check = await conn.execute(
                text(
                    """
                    SELECT EXISTS (
                        SELECT FROM pg_type
                        WHERE typname = 'errorcode'
                    );
                """
                )
            )
            enum_exists = enum_check.scalar()

            assert not enum_exists, (
                "errorcode ENUM type should be dropped after migration, "
                "but still exists in database"
            )

    async def test_migration_idempotency(
        self,
        migration_postgres_container: PostgresContainer,
    ) -> None:
        """
        Test that running migrations twice doesn't cause errors.

        This guards against ENUM duplication and other DDL conflicts.
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
