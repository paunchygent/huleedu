"""
Migration test for pair_generation_mode column on ComparisonPair.

Per rule 085.4: "Service-level smoke test: every service MUST provide an automated
check (CI or local script) that provisions an ephemeral PostgreSQL instance
(TestContainers or docker-compose) and runs `../../.venv/bin/alembic upgrade head`.
This regression test guards against enum/type duplication and other DDL conflicts
before migrations merge."

This test validates:
1. Migration can run on clean PostgreSQL instance
2. pair_generation_mode column is created with correct type (VARCHAR(20), nullable)
3. Column accepts values "coverage" and "resampling"
4. Migration is idempotent (running twice doesn't error)
"""

from __future__ import annotations

import subprocess
import uuid
from pathlib import Path
from typing import AsyncGenerator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from testcontainers.postgres import PostgresContainer

from services.cj_assessment_service.enums_db import CJBatchStatusEnum
from services.cj_assessment_service.models_db import CJBatchUpload, ComparisonPair


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
    import re

    # Build database URL for Alembic
    db_url = container.get_connection_url().replace("psycopg2", "asyncpg")

    # Get service directory
    service_dir = Path(__file__).parents[2]  # services/cj_assessment_service
    alembic_ini = service_dir / "alembic.ini"

    # Parse connection details from container URL
    container_url = container.get_connection_url()
    match = re.match(r"postgresql(?:\+\w+)?://([^:]+):([^@]+)@([^:]+):(\d+)/(.+)", container_url)
    if not match:
        raise ValueError(f"Could not parse container URL: {container_url}")

    # Create environment with complete DATABASE_URL override
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
class TestPairGenerationModeMigration:
    """Test pair_generation_mode column addition to ComparisonPair."""

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

    async def test_pair_generation_mode_column_type_and_nullability(
        self,
        migration_postgres_container: PostgresContainer,
        migration_engine: AsyncEngine,
    ) -> None:
        """
        Test that pair_generation_mode column exists with correct type and nullability.
        """
        # Run migrations first
        result = run_alembic_upgrade(migration_postgres_container)
        assert result.returncode == 0, "Migration must succeed before testing"

        async with migration_engine.connect() as conn:
            # Check pair_generation_mode column exists and is correct type
            column_check = await conn.execute(
                text(
                    """
                    SELECT data_type, is_nullable, character_maximum_length
                    FROM information_schema.columns
                    WHERE table_name = 'cj_comparison_pairs'
                    AND column_name = 'pair_generation_mode';
                """
                )
            )
            column_info = column_check.one_or_none()

            assert column_info is not None, "pair_generation_mode column was not created"

            # Should be character varying (VARCHAR), nullable, max length 20
            assert column_info[0] == "character varying", (
                f"pair_generation_mode should be 'character varying', got: {column_info[0]}"
            )
            assert column_info[1] == "YES", (
                f"pair_generation_mode should be nullable, got: {column_info[1]}"
            )
            assert column_info[2] == 20, (
                f"pair_generation_mode should have max length 20, got: {column_info[2]}"
            )

    async def test_pair_generation_mode_index_exists(
        self,
        migration_postgres_container: PostgresContainer,
        migration_engine: AsyncEngine,
    ) -> None:
        """
        Test that pair_generation_mode column has an index for query performance.
        """
        # Run migrations first
        result = run_alembic_upgrade(migration_postgres_container)
        assert result.returncode == 0, "Migration must succeed before testing"

        async with migration_engine.connect() as conn:
            # Check for index on pair_generation_mode column
            index_check = await conn.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM pg_indexes
                    WHERE tablename = 'cj_comparison_pairs'
                    AND indexdef LIKE '%pair_generation_mode%';
                """
                )
            )
            index_count = index_check.scalar()
            assert index_count is not None and index_count > 0, (
                "pair_generation_mode should have an index"
            )

    async def test_pair_generation_mode_accepts_valid_values(
        self,
        migration_postgres_container: PostgresContainer,
        migration_session: AsyncSession,
    ) -> None:
        """
        Test that pair_generation_mode column accepts 'coverage' and 'resampling' values.
        """
        # Run migrations first
        result = run_alembic_upgrade(migration_postgres_container)
        assert result.returncode == 0, "Migration must succeed before testing"

        # Create a batch upload to satisfy foreign key
        test_upload = CJBatchUpload(
            bos_batch_id=str(uuid.uuid4()),
            event_correlation_id=str(uuid.uuid4()),
            language="sv",
            course_code="TEST_COURSE",
            expected_essay_count=5,
            status=CJBatchStatusEnum.PENDING,
        )
        migration_session.add(test_upload)
        await migration_session.flush()

        # Create essay records to satisfy foreign keys
        from services.cj_assessment_service.models_db import ProcessedEssay

        essay_a_id = str(uuid.uuid4())
        essay_b_id = str(uuid.uuid4())
        essay_c_id = str(uuid.uuid4())

        essay_a = ProcessedEssay(
            els_essay_id=essay_a_id,
            cj_batch_id=test_upload.id,
            text_storage_id="storage-1",
            assessment_input_text="Essay A text",
        )
        essay_b = ProcessedEssay(
            els_essay_id=essay_b_id,
            cj_batch_id=test_upload.id,
            text_storage_id="storage-2",
            assessment_input_text="Essay B text",
        )
        essay_c = ProcessedEssay(
            els_essay_id=essay_c_id,
            cj_batch_id=test_upload.id,
            text_storage_id="storage-3",
            assessment_input_text="Essay C text",
        )
        migration_session.add_all([essay_a, essay_b, essay_c])
        await migration_session.flush()

        # Create comparison pair with 'coverage' mode
        coverage_pair = ComparisonPair(
            cj_batch_id=test_upload.id,
            essay_a_els_id=essay_a_id,
            essay_b_els_id=essay_b_id,
            prompt_text="Compare these essays",
            pair_generation_mode="coverage",
        )
        migration_session.add(coverage_pair)
        await migration_session.flush()

        # Create comparison pair with 'resampling' mode
        resampling_pair = ComparisonPair(
            cj_batch_id=test_upload.id,
            essay_a_els_id=essay_b_id,
            essay_b_els_id=essay_c_id,
            prompt_text="Compare these essays",
            pair_generation_mode="resampling",
        )
        migration_session.add(resampling_pair)
        await migration_session.flush()

        # Verify values were stored correctly
        await migration_session.refresh(coverage_pair)
        await migration_session.refresh(resampling_pair)

        assert coverage_pair.pair_generation_mode == "coverage", (
            f"Expected 'coverage', got '{coverage_pair.pair_generation_mode}'"
        )
        assert resampling_pair.pair_generation_mode == "resampling", (
            f"Expected 'resampling', got '{resampling_pair.pair_generation_mode}'"
        )

    async def test_pair_generation_mode_nullable_for_backwards_compatibility(
        self,
        migration_postgres_container: PostgresContainer,
        migration_session: AsyncSession,
    ) -> None:
        """
        Test that pair_generation_mode can be NULL for backwards compatibility.

        This ensures existing code that doesn't set pair_generation_mode continues to work.
        """
        # Run migrations first
        result = run_alembic_upgrade(migration_postgres_container)
        assert result.returncode == 0, "Migration must succeed before testing"

        # Create a batch upload to satisfy foreign key
        test_upload = CJBatchUpload(
            bos_batch_id=str(uuid.uuid4()),
            event_correlation_id=str(uuid.uuid4()),
            language="sv",
            course_code="TEST_COURSE",
            expected_essay_count=5,
            status=CJBatchStatusEnum.PENDING,
        )
        migration_session.add(test_upload)
        await migration_session.flush()

        # Create essay records
        from services.cj_assessment_service.models_db import ProcessedEssay

        essay_a_id = str(uuid.uuid4())
        essay_b_id = str(uuid.uuid4())

        essay_a = ProcessedEssay(
            els_essay_id=essay_a_id,
            cj_batch_id=test_upload.id,
            text_storage_id="storage-1",
            assessment_input_text="Essay A text",
        )
        essay_b = ProcessedEssay(
            els_essay_id=essay_b_id,
            cj_batch_id=test_upload.id,
            text_storage_id="storage-2",
            assessment_input_text="Essay B text",
        )
        migration_session.add_all([essay_a, essay_b])
        await migration_session.flush()

        # Create comparison pair WITHOUT pair_generation_mode (NULL)
        null_mode_pair = ComparisonPair(
            cj_batch_id=test_upload.id,
            essay_a_els_id=essay_a_id,
            essay_b_els_id=essay_b_id,
            prompt_text="Compare these essays",
            pair_generation_mode=None,
        )
        migration_session.add(null_mode_pair)
        await migration_session.flush()

        # Verify NULL was stored
        await migration_session.refresh(null_mode_pair)
        assert null_mode_pair.pair_generation_mode is None

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
