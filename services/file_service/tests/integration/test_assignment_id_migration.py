"""Migration test for assignment_id and text_storage_id indexes in File Service.

Per rule 085: every Alembic migration must be validated against a clean
PostgreSQL instance to guard against DDL conflicts and ensure intended schema
changes are applied (including idempotency).
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import AsyncGenerator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from testcontainers.postgres import PostgresContainer

from services.file_service.models_db import FileUpload


@pytest.fixture(scope="module")
def migration_postgres_container() -> PostgresContainer:
    """Provision PostgreSQL container for migration testing."""
    with PostgresContainer(
        "postgres:15",
        username="file_migration_user",
        password="file_migration_password",
        dbname="file_migration_test",
    ) as container:
        yield container


@pytest.fixture
async def migration_engine(
    migration_postgres_container: PostgresContainer,
) -> AsyncGenerator[AsyncEngine, None]:
    """Create async engine connected to migration container."""
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
    """Run Alembic upgrade head for File Service against container database."""
    import os

    db_url = container.get_connection_url().replace("psycopg2", "asyncpg")

    service_dir = Path(__file__).parents[2]
    alembic_ini = service_dir / "alembic.ini"

    env = os.environ.copy()
    env["FILE_SERVICE_DATABASE_URL"] = db_url

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
class TestAssignmentIdMigration:
    """Integration tests for assignment_id and text_storage_id migration."""

    async def test_migration_upgrade_from_clean_database(
        self,
        migration_postgres_container: PostgresContainer,
        migration_engine: AsyncEngine,
    ) -> None:
        """Alembic upgrade succeeds and creates expected columns/indexes."""
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
                    WHERE table_name = 'file_uploads'
                      AND column_name IN ('assignment_id', 'text_storage_id')
                    ORDER BY column_name;
                    """
                )
            )
            columns = {row[0]: row for row in column_rows.fetchall()}

            assert "assignment_id" in columns, "assignment_id column missing"
            assert columns["assignment_id"][1] == "character varying"
            assert columns["assignment_id"][2] == 255
            assert columns["assignment_id"][3] == "YES"

            assert "text_storage_id" in columns, "text_storage_id column missing"
            assert columns["text_storage_id"][1] == "character varying"
            assert columns["text_storage_id"][2] == 255

            index_rows = await conn.execute(
                text(
                    """
                    SELECT indexname
                    FROM pg_indexes
                    WHERE tablename = 'file_uploads';
                    """
                )
            )
            index_names = {row[0] for row in index_rows.fetchall()}
            assert "ix_file_uploads_assignment_id" in index_names
            assert "ix_file_uploads_text_storage_id" in index_names

    async def test_assignment_id_insert_roundtrip(
        self,
        migration_postgres_container: PostgresContainer,
        migration_session: AsyncSession,
    ) -> None:
        """Records with assignment_id and text_storage_id can be persisted after migration."""
        result = run_alembic_upgrade(migration_postgres_container)
        assert result.returncode == 0, "Migration must succeed before insert test"

        upload = FileUpload(
            file_upload_id="test-upload-assign-1",
            batch_id="batch-123",
            user_id="user-123",
            assignment_id="assignment-xyz",
            filename="essay.txt",
            file_size_bytes=1024,
            raw_file_storage_id="raw-abc",
            text_storage_id="text-abc",
        )

        migration_session.add(upload)
        await migration_session.flush()
        await migration_session.refresh(upload)

        assert upload.assignment_id == "assignment-xyz"
        assert upload.text_storage_id == "text-abc"

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
