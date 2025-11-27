"""Migration test for assignment_id column on batch_results in Result Aggregator Service.

Per rule 085, every Alembic migration must be validated against a clean
PostgreSQL instance to guard against DDL conflicts and ensure intended schema
changes (including idempotency) are applied correctly.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import AsyncGenerator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from testcontainers.postgres import PostgresContainer

from services.result_aggregator_service.models_db import BatchResult


@pytest.fixture(scope="module")
def migration_postgres_container() -> PostgresContainer:
    """Provision PostgreSQL container for migration testing."""
    with PostgresContainer(
        "postgres:15",
        username="ras_migration_user",
        password="ras_migration_password",
        dbname="ras_migration_test",
    ) as container:
        yield container


@pytest.fixture
async def migration_engine(
    migration_postgres_container: PostgresContainer,
) -> AsyncGenerator[AsyncEngine, None]:
    """Create async engine connected to migration container."""
    connection_url = migration_postgres_container.get_connection_url()
    if "+psycopg2://" in connection_url:
        connection_url = connection_url.replace("+psycopg2://", "+asyncpg://")
    elif "postgresql://" in connection_url:
        connection_url = connection_url.replace("postgresql://", "postgresql+asyncpg://")

    engine = create_async_engine(
        connection_url,
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
    """Create session bound to migration engine."""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    session_maker = async_sessionmaker(
        migration_engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )

    async with session_maker() as session:
        async with session.begin():
            yield session
            # Transaction rolled back automatically


def run_alembic_upgrade(container: PostgresContainer) -> subprocess.CompletedProcess[str]:
    """Run Alembic upgrade head for Result Aggregator Service against container database."""
    import os

    db_url = container.get_connection_url()
    if "+psycopg2://" in db_url:
        db_url = db_url.replace("+psycopg2://", "+asyncpg://")
    elif "postgresql://" in db_url:
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://")

    service_dir = Path(__file__).parents[2]
    alembic_ini = service_dir / "alembic.ini"

    env = os.environ.copy()
    # Service-specific override so Settings.DATABASE_URL uses container database
    env["RESULT_AGGREGATOR_SERVICE_DATABASE_URL"] = db_url

    return subprocess.run(
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


@pytest.mark.integration
@pytest.mark.slow
class TestAssignmentIdBatchMigration:
    """Integration tests for assignment_id migration on batch_results."""

    async def test_migration_upgrade_from_clean_database(
        self,
        migration_postgres_container: PostgresContainer,
        migration_engine: AsyncEngine,
    ) -> None:
        """Alembic upgrade succeeds and creates expected column and index."""
        result = run_alembic_upgrade(migration_postgres_container)
        assert result.returncode == 0, (
            f"Alembic upgrade failed:\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"
        )

        async with migration_engine.connect() as conn:
            column_rows = await conn.execute(
                text(
                    """
                    SELECT column_name, data_type, character_maximum_length, is_nullable
                    FROM information_schema.columns
                    WHERE table_name = 'batch_results'
                      AND column_name = 'assignment_id';
                    """
                )
            )
            rows = column_rows.fetchall()
            assert rows, "assignment_id column missing on batch_results"
            column = rows[0]
            assert column[1] == "character varying"
            assert column[2] == 100
            assert column[3] == "YES"

            index_rows = await conn.execute(
                text(
                    """
                    SELECT indexname
                    FROM pg_indexes
                    WHERE tablename = 'batch_results';
                    """
                )
            )
            index_names = {row[0] for row in index_rows.fetchall()}
            assert "ix_batch_results_assignment_id" in index_names

    async def test_assignment_id_insert_roundtrip(
        self,
        migration_postgres_container: PostgresContainer,
        migration_session: AsyncSession,
    ) -> None:
        """Batches with assignment_id can be persisted after migration."""
        result = run_alembic_upgrade(migration_postgres_container)
        assert result.returncode == 0, "Migration must succeed before insert test"

        batch = BatchResult(
            batch_id="assignment-batch-001",
            user_id="teacher-assignment",
            essay_count=1,
            completed_essay_count=0,
            failed_essay_count=0,
            assignment_id="assignment-123",
        )

        migration_session.add(batch)
        await migration_session.flush()
        await migration_session.refresh(batch)

        assert batch.assignment_id == "assignment-123"

    async def test_migration_idempotency(
        self,
        migration_postgres_container: PostgresContainer,
    ) -> None:
        """Running migrations twice remains idempotent (no duplicate objects)."""
        first = run_alembic_upgrade(migration_postgres_container)
        assert first.returncode == 0, f"First migration run failed:\n{first.stderr}"

        second = run_alembic_upgrade(migration_postgres_container)
        assert second.returncode == 0, (
            f"Second migration run failed (not idempotent):\n{second.stderr}"
        )
        assert "already exists" not in second.stderr.lower()
