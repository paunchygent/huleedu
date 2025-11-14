"""Migration test for stored_content table creation in Content Service.

Per rule 085.4: every service MUST provide a smoke test that provisions an
ephemeral PostgreSQL instance and runs `alembic upgrade head` to guard against
DDL conflicts before migrations merge.

This test validates that:
1. Alembic migrations run successfully on a clean PostgreSQL instance.
2. The stored_content table is created with the expected columns and types.
3. The created_at index exists.
4. Running migrations twice is idempotent (no "already exists" errors).
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import AsyncGenerator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from testcontainers.postgres import PostgresContainer

from services.content_service.models_db import StoredContent


@pytest.fixture(scope="module")
def migration_postgres_container() -> PostgresContainer:
    """Create PostgreSQL container for Content Service migration testing."""
    with PostgresContainer(
        "postgres:15",
        username="content_migration_user",
        password="content_migration_password",
        dbname="content_migration_test",
    ) as container:
        yield container


@pytest.fixture
async def migration_engine(
    migration_postgres_container: PostgresContainer,
) -> AsyncGenerator[AsyncEngine, None]:
    """Create async engine for migration testing."""
    database_url = migration_postgres_container.get_connection_url().replace(
        "psycopg2",
        "asyncpg",
    )

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
            # Transaction is rolled back automatically


def run_alembic_upgrade(container: PostgresContainer) -> subprocess.CompletedProcess[str]:
    """Run Alembic upgrade head for Content Service on the given container."""
    import os

    # Build async database URL for Alembic (env override)
    db_url = container.get_connection_url().replace("psycopg2", "asyncpg")

    # Service directory and alembic.ini path
    service_dir = Path(__file__).parents[2]  # services/content_service
    alembic_ini = service_dir / "alembic.ini"

    # Prepare environment: override CONTENT_SERVICE_DATABASE_URL
    env = os.environ.copy()
    env["CONTENT_SERVICE_DATABASE_URL"] = db_url

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
class TestStoredContentMigration:
    """Integration tests for stored_content Alembic migration."""

    async def test_migration_upgrade_from_clean_database(
        self,
        migration_postgres_container: PostgresContainer,
        migration_engine: AsyncEngine,
    ) -> None:
        """Mandatory smoke test: migrations run on clean PostgreSQL instance."""
        result = run_alembic_upgrade(migration_postgres_container)

        assert result.returncode == 0, (
            f"Alembic upgrade failed:\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"
        )

        async with migration_engine.connect() as conn:
            # Check that stored_content table exists
            table_check = await conn.execute(
                text(
                    """
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables
                        WHERE table_name = 'stored_content'
                    );
                    """
                )
            )
            table_exists = table_check.scalar()
            assert table_exists, "stored_content table was not created"

            # Verify core columns and types via information_schema
            column_check = await conn.execute(
                text(
                    """
                    SELECT column_name, data_type, character_maximum_length, is_nullable
                    FROM information_schema.columns
                    WHERE table_name = 'stored_content'
                    ORDER BY column_name;
                    """
                )
            )
            columns = {row[0]: row for row in column_check.fetchall()}

            assert "content_id" in columns
            assert columns["content_id"][1] == "character varying"
            assert columns["content_id"][2] == 32

            assert "content_data" in columns
            assert columns["content_data"][1] in {"bytea"}

            assert "content_size" in columns
            assert columns["content_size"][1] in {"integer", "int4"}

            assert "content_type" in columns
            assert columns["content_type"][1] == "character varying"
            assert columns["content_type"][2] == 100

            assert "created_at" in columns
            # created_at should be NOT NULL
            assert columns["created_at"][3] == "NO"

            # Check that created_at index exists
            index_check = await conn.execute(
                text(
                    """
                    SELECT EXISTS (
                        SELECT FROM pg_indexes
                        WHERE tablename = 'stored_content'
                        AND indexname = 'ix_stored_content_created_at'
                    );
                    """
                )
            )
            index_exists = index_check.scalar()
            assert index_exists, "Index on stored_content.created_at was not created"

    async def test_stored_content_insert_roundtrip(
        self,
        migration_postgres_container: PostgresContainer,
        migration_engine: AsyncEngine,
        migration_session: AsyncSession,
    ) -> None:
        """Verify that StoredContent model can insert and read bytes after migration."""
        result = run_alembic_upgrade(migration_postgres_container)
        assert result.returncode == 0, "Migration must succeed before testing insert"

        test_content_id = "a" * 32
        test_bytes = b"test content bytes for stored_content migration"
        test_type = "text/plain"

        stored = StoredContent(
            content_id=test_content_id,
            content_data=test_bytes,
            content_size=len(test_bytes),
            content_type=test_type,
        )
        migration_session.add(stored)
        await migration_session.flush()
        await migration_session.refresh(stored)

        assert stored.content_id == test_content_id
        assert stored.content_data == test_bytes
        assert stored.content_size == len(test_bytes)
        assert stored.content_type == test_type

    async def test_migration_idempotency(
        self,
        migration_postgres_container: PostgresContainer,
    ) -> None:
        """Running migrations twice should not cause DDL conflicts."""
        result1 = run_alembic_upgrade(migration_postgres_container)
        assert result1.returncode == 0, f"First migration run failed:\n{result1.stderr}"

        result2 = run_alembic_upgrade(migration_postgres_container)
        assert result2.returncode == 0, (
            f"Second migration run failed (not idempotent):\n{result2.stderr}"
        )

        assert "already exists" not in result2.stderr.lower(), (
            f"Migration not idempotent - duplicate creation detected:\n{result2.stderr}"
        )
