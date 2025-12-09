"""Migration test for COMPLETE_FORCED_RECOVERY CJ batch status.

Per rule 085.4: this test provisions an ephemeral PostgreSQL instance and runs
`alembic upgrade head` to guard against DDL conflicts before migrations merge.

This test validates:
1. Alembic migrations run successfully on a clean PostgreSQL instance.
2. The `cj_batch_status_enum` type contains the `COMPLETE_FORCED_RECOVERY` label.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import AsyncGenerator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from testcontainers.postgres import PostgresContainer


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
    assert user and password and host and port and database

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
class TestCJBatchStatusForcedRecoveryMigration:
    """Test migration adding COMPLETE_FORCED_RECOVERY batch status."""

    async def test_migration_adds_forced_recovery_status(
        self,
        migration_postgres_container: PostgresContainer,
        migration_engine: AsyncEngine,
    ) -> None:
        """Migration runs and cj_batch_status_enum contains COMPLETE_FORCED_RECOVERY."""
        # Run Alembic upgrade head
        result = run_alembic_upgrade(migration_postgres_container)

        # Assert migration succeeded
        assert result.returncode == 0, (
            f"Alembic upgrade failed:\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"
        )

        # Verify enum contains the new status label
        async with migration_engine.connect() as conn:
            enum_check = await conn.execute(
                text(
                    """
                    SELECT enumlabel
                    FROM pg_enum e
                    JOIN pg_type t ON t.oid = e.enumtypid
                    WHERE t.typname = 'cj_batch_status_enum'
                    ORDER BY enumsortorder;
                    """
                )
            )
            labels = [row[0] for row in enum_check]

        assert "COMPLETE_FORCED_RECOVERY" in labels, (
            "cj_batch_status_enum is missing COMPLETE_FORCED_RECOVERY after migration"
        )
