"""Migration test for anchor uniqueness constraint on assignment/label/scale.

Per rule 085.4: "Service-level smoke test: every service MUST provide an automated
check (CI or local script) that provisions an ephemeral PostgreSQL instance
(TestContainers or docker compose) and runs `../../.venv/bin/alembic upgrade head`.
This regression test guards against DDL conflicts before migrations merge."

This test validates:
1. Migration can run on a clean PostgreSQL instance
2. Unique constraint exists on (assignment_id, anchor_label, grade_scale)
3. Duplicate anchors for the same (assignment_id, anchor_label, grade_scale) are rejected
4. PostgreSQL NULL semantics remain unchanged (multiple NULL assignment_id rows allowed)
5. Migration is idempotent (successive upgrades do not fail)
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import AsyncGenerator

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from testcontainers.postgres import PostgresContainer

from services.cj_assessment_service.models_db import AnchorEssayReference


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

    # Build database URL for Alembic (asyncpg driver)
    db_url = container.get_connection_url().replace("psycopg2", "asyncpg")

    # Get service directory and alembic.ini
    service_dir = Path(__file__).parents[2]  # services/cj_assessment_service
    alembic_ini = service_dir / "alembic.ini"

    # Parse connection details from container URL
    container_url = container.get_connection_url()
    # Format: postgresql+psycopg2://user:password@host:port/database
    match = re.match(r"postgresql(?:\+\w+)?://([^:]+):([^@]+)@([^:]+):(\d+)/(.+)", container_url)
    if not match:
        raise ValueError(f"Could not parse container URL: {container_url}")

    user, password, host, port, database = match.groups()
    assert user and password and host and port and database  # Sanity check

    # Provide DATABASE_URL override for service settings
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
class TestAnchorUniqueConstraintMigration:
    """Test anchor uniqueness constraint migration behavior."""

    async def test_migration_upgrade_from_clean_database(
        self,
        migration_postgres_container: PostgresContainer,
        migration_engine: AsyncEngine,
    ) -> None:
        """Migration runs successfully and unique constraint is present."""
        # Run Alembic upgrade head
        result = run_alembic_upgrade(migration_postgres_container)

        # Assert migration succeeded
        assert result.returncode == 0, (
            f"Alembic upgrade failed:\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"
        )

        # Verify unique constraint exists on anchor_essay_references
        async with migration_engine.connect() as conn:
            constraint_check = await conn.execute(
                text(
                    """
                    SELECT constraint_name
                    FROM information_schema.table_constraints
                    WHERE table_name = 'anchor_essay_references'
                      AND constraint_type = 'UNIQUE';
                    """
                )
            )
            constraints = [row[0] for row in constraint_check]
            assert "uq_anchor_assignment_label_scale" in constraints, (
                "Unique constraint uq_anchor_assignment_label_scale was not created"
            )

    async def test_constraint_prevents_duplicate_assignment_anchors(
        self,
        migration_postgres_container: PostgresContainer,
        migration_engine: AsyncEngine,
        migration_session: AsyncSession,
    ) -> None:
        """Duplicate anchors for same (assignment_id, anchor_label, grade_scale)."""
        # raise IntegrityError when duplicate created
        # Ensure schema is migrated
        result = run_alembic_upgrade(migration_postgres_container)
        assert result.returncode == 0, "Migration must succeed before testing constraint"

        # Insert first anchor
        anchor1 = AnchorEssayReference(
            assignment_id="test-assignment-001",
            anchor_label="anchor_A",
            grade="A",
            grade_scale="swedish_8_anchor",
            text_storage_id="storage-1",
        )
        migration_session.add(anchor1)
        await migration_session.flush()

        # Insert duplicate anchor with same key triple but different storage_id
        anchor2 = AnchorEssayReference(
            assignment_id="test-assignment-001",
            anchor_label="anchor_A",
            grade="A",
            grade_scale="swedish_8_anchor",
            text_storage_id="storage-2",
        )
        migration_session.add(anchor2)

        with pytest.raises(IntegrityError):
            await migration_session.flush()

    async def test_constraint_allows_null_assignment_id_duplicates(
        self,
        migration_postgres_container: PostgresContainer,
        migration_engine: AsyncEngine,
        migration_session: AsyncSession,
    ) -> None:
        """Multiple anchors with NULL assignment_id and same grade/scale are allowed.

        This documents current PostgreSQL NULL semantics for unique constraints and
        is informational only – behavior is relied on but not enforced by application
        logic.
        """
        # Ensure schema is migrated
        result = run_alembic_upgrade(migration_postgres_container)
        assert result.returncode == 0, "Migration must succeed before testing NULL semantics"

        # Insert two anchors with NULL assignment_id but same label/scale
        anchor1 = AnchorEssayReference(
            assignment_id=None,
            anchor_label="anchor_B",
            grade="B",
            grade_scale="swedish_8_anchor",
            text_storage_id="null-assignment-storage-1",
        )
        anchor2 = AnchorEssayReference(
            assignment_id=None,
            anchor_label="anchor_B",
            grade="B",
            grade_scale="swedish_8_anchor",
            text_storage_id="null-assignment-storage-2",
        )

        migration_session.add(anchor1)
        migration_session.add(anchor2)

        # Should not raise IntegrityError
        await migration_session.flush()

        # Verify both rows exist with distinct IDs
        await migration_session.refresh(anchor1)
        await migration_session.refresh(anchor2)
        assert anchor1.id != anchor2.id

    async def test_migration_idempotency(
        self,
        migration_postgres_container: PostgresContainer,
    ) -> None:
        """Running Alembic upgrade head twice does not fail."""
        # First run
        result1 = run_alembic_upgrade(migration_postgres_container)
        assert result1.returncode == 0, f"First migration run failed:\n{result1.stderr}"

        # Second run (should be idempotent)
        result2 = run_alembic_upgrade(migration_postgres_container)
        assert result2.returncode == 0, (
            f"Second migration run failed (not idempotent):\n{result2.stderr}"
        )

        # Should not contain "already exists" errors
        assert "already exists" not in result2.stderr.lower(), (
            f"Migration not idempotent - duplicate creation detected:\n{result2.stderr}"
        )
