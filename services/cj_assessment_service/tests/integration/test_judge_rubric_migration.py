"""
Migration test for judge_rubric_storage_id column addition.

Per rule 085.4: "Service-level smoke test: every service MUST provide an automated
check (CI or local script) that provisions an ephemeral PostgreSQL instance
(TestContainers or docker-compose) and runs `../../.venv/bin/alembic upgrade head`.
This regression test guards against enum/type duplication and other DDL conflicts
before migrations merge."

This test validates:
1. Migration can run on clean PostgreSQL instance
2. judge_rubric_storage_id column is created successfully
3. judge_rubric_storage_id accepts VARCHAR values
4. No DDL conflicts occur
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

from services.cj_assessment_service.models_db import AssessmentInstruction


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
class TestJudgeRubricMigration:
    """Test judge_rubric_storage_id column addition migration."""

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
            # Check that assessment_instructions table exists
            table_check = await conn.execute(
                text(
                    """
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables
                        WHERE table_name = 'assessment_instructions'
                    );
                """
                )
            )
            table_exists = table_check.scalar()
            assert table_exists, "assessment_instructions table was not created"

            # Check judge_rubric_storage_id column exists and is correct type
            column_check = await conn.execute(
                text(
                    """
                    SELECT data_type, character_maximum_length, is_nullable
                    FROM information_schema.columns
                    WHERE table_name = 'assessment_instructions'
                    AND column_name = 'judge_rubric_storage_id';
                """
                )
            )
            column_info = column_check.one_or_none()

            assert column_info is not None, "judge_rubric_storage_id column was not created"

            # Should be VARCHAR(255), nullable
            assert column_info[0] == "character varying", (
                f"judge_rubric_storage_id should be 'character varying', got: {column_info[0]}"
            )
            assert column_info[1] == 255, (
                f"judge_rubric_storage_id should have max length 255, got: {column_info[1]}"
            )
            assert column_info[2] == "YES", (
                f"judge_rubric_storage_id should be nullable, got: {column_info[2]}"
            )

            # Check that index was created
            index_check = await conn.execute(
                text(
                    """
                    SELECT EXISTS (
                        SELECT FROM pg_indexes
                        WHERE tablename = 'assessment_instructions'
                        AND indexname = 'ix_assessment_instructions_judge_rubric_storage_id'
                    );
                """
                )
            )
            index_exists = index_check.scalar()
            assert index_exists, "Index on judge_rubric_storage_id was not created"

    async def test_judge_rubric_storage_id_accepts_string_values(
        self,
        migration_postgres_container: PostgresContainer,
        migration_engine: AsyncEngine,
        migration_session: AsyncSession,
    ) -> None:
        """
        Test that judge_rubric_storage_id column accepts string values.

        This validates the migration achieves its goal: storing rubric storage IDs.
        """
        # First run migrations to ensure schema is ready
        result = run_alembic_upgrade(migration_postgres_container)
        assert result.returncode == 0, "Migration must succeed before testing"

        # Create test data with judge_rubric_storage_id
        test_storage_id = f"judge-rubric-{uuid.uuid4()}"
        test_student_prompt_id = f"student-prompt-{uuid.uuid4()}"

        # Create assessment instruction with judge rubric storage ID
        assessment = AssessmentInstruction(
            assignment_id="TEST_ASSIGNMENT_001",
            course_id=None,
            instructions_text="Test assessment instructions",
            grade_scale="swedish_8_anchor",
            student_prompt_storage_id=test_student_prompt_id,
            judge_rubric_storage_id=test_storage_id,
        )

        # This should NOT raise any errors
        migration_session.add(assessment)
        await migration_session.flush()

        # Verify values were stored correctly
        await migration_session.refresh(assessment)
        assert assessment.judge_rubric_storage_id == test_storage_id, (
            f"Expected judge_rubric_storage_id '{test_storage_id}', "
            f"got '{assessment.judge_rubric_storage_id}'"
        )
        assert assessment.student_prompt_storage_id == test_student_prompt_id

    async def test_judge_rubric_storage_id_nullable(
        self,
        migration_postgres_container: PostgresContainer,
        migration_engine: AsyncEngine,
        migration_session: AsyncSession,
    ) -> None:
        """
        Test that judge_rubric_storage_id can be NULL.

        This validates backwards compatibility: existing records without rubric IDs still work.
        """
        # Run migrations
        result = run_alembic_upgrade(migration_postgres_container)
        assert result.returncode == 0

        # Create assessment instruction WITHOUT judge rubric storage ID
        assessment = AssessmentInstruction(
            assignment_id="TEST_ASSIGNMENT_002",
            course_id=None,
            instructions_text="Test assessment without judge rubric",
            grade_scale="eng5_np_national_9_step",
            student_prompt_storage_id=None,
            judge_rubric_storage_id=None,  # Explicitly NULL
        )

        # This should work fine
        migration_session.add(assessment)
        await migration_session.flush()

        # Verify NULL was stored
        await migration_session.refresh(assessment)
        assert assessment.judge_rubric_storage_id is None

    async def test_both_storage_ids_can_be_set_independently(
        self,
        migration_postgres_container: PostgresContainer,
        migration_engine: AsyncEngine,
        migration_session: AsyncSession,
    ) -> None:
        """
        Test that student_prompt_storage_id and judge_rubric_storage_id are independent.

        This validates the schema allows flexible combinations:
        - Both set
        - Only student prompt set
        - Only judge rubric set
        - Neither set
        """
        # Run migrations
        result = run_alembic_upgrade(migration_postgres_container)
        assert result.returncode == 0

        test_cases = [
            ("both", "student-1", "judge-1"),
            ("student_only", "student-2", None),
            ("judge_only", None, "judge-3"),
            ("neither", None, None),
        ]

        for case_name, student_id, judge_id in test_cases:
            assessment = AssessmentInstruction(
                assignment_id=f"TEST_ASSIGNMENT_{case_name}",
                course_id=None,
                instructions_text=f"Test case: {case_name}",
                grade_scale="swedish_8_anchor",
                student_prompt_storage_id=student_id,
                judge_rubric_storage_id=judge_id,
            )

            migration_session.add(assessment)
            await migration_session.flush()

            # Verify values
            await migration_session.refresh(assessment)
            assert assessment.student_prompt_storage_id == student_id, (
                f"Case {case_name}: student_prompt_storage_id mismatch"
            )
            assert assessment.judge_rubric_storage_id == judge_id, (
                f"Case {case_name}: judge_rubric_storage_id mismatch"
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
