"""Migration test for assessment_instructions.context_origin default + backfill.

Per rule 085.4: every Alembic-enabled service MUST have an automated check that
provisions an ephemeral PostgreSQL instance (TestContainers or docker compose)
and runs `../../.venv/bin/alembic upgrade head`.

This test validates:
1. Migrations can run on a clean PostgreSQL instance
2. assessment_instructions.context_origin exists, is NOT NULL, and defaults to
   'research_experiment' (experiment-first workflow)
3. The ENG5 NP experiment assignment backfill (assignment_id=000...001) is applied
   when upgrading from a pre-context_origin schema
4. Migration is idempotent (successive upgrades do not fail)
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import AsyncGenerator, Iterator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from testcontainers.postgres import PostgresContainer

_ENG5_EXPERIMENT_ASSIGNMENT_ID = "00000000-0000-0000-0000-000000000001"


@pytest.fixture
def migration_postgres_container() -> Iterator[PostgresContainer]:
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


def _run_alembic_upgrade(
    container: PostgresContainer, target_revision: str
) -> subprocess.CompletedProcess:
    db_url = container.get_connection_url().replace("psycopg2", "asyncpg")

    service_dir = Path(__file__).parents[2]  # services/cj_assessment_service
    alembic_ini = service_dir / "alembic.ini"

    container_url = container.get_connection_url()
    match = re.match(
        r"postgresql(?:\+\w+)?://([^:]+):([^@]+)@([^:]+):(\d+)/(.+)",
        container_url,
    )
    if not match:
        raise ValueError(f"Could not parse container URL: {container_url}")

    env = os.environ.copy()
    env["CJ_ASSESSMENT_SERVICE_DATABASE_URL"] = db_url

    return subprocess.run(
        [
            str(Path(__file__).parents[4] / ".venv" / "bin" / "alembic"),
            "-c",
            str(alembic_ini),
            "upgrade",
            target_revision,
        ],
        cwd=str(service_dir),
        env=env,
        capture_output=True,
        text=True,
    )


@pytest.mark.integration
@pytest.mark.slow
class TestContextOriginMigration:
    async def test_upgrade_head_sets_default_to_research_experiment(
        self,
        migration_postgres_container: PostgresContainer,
        migration_engine: AsyncEngine,
    ) -> None:
        result = _run_alembic_upgrade(migration_postgres_container, "head")
        assert result.returncode == 0, (
            f"Alembic upgrade failed:\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"
        )

        async with migration_engine.connect() as conn:
            row = (
                await conn.execute(
                    text(
                        """
                        SELECT column_default, is_nullable
                        FROM information_schema.columns
                        WHERE table_name = 'assessment_instructions'
                          AND column_name = 'context_origin'
                        """
                    )
                )
            ).first()

            assert row is not None, "context_origin column must exist after migration"
            column_default, is_nullable = row
            assert is_nullable == "NO"
            assert column_default is not None
            assert "research_experiment" in str(column_default)

            inserted = (
                await conn.execute(
                    text(
                        """
                        INSERT INTO assessment_instructions (
                            assignment_id,
                            instructions_text,
                            grade_scale
                        )
                        VALUES (:assignment_id, :instructions_text, :grade_scale)
                        RETURNING context_origin
                        """
                    ),
                    {
                        "assignment_id": "11111111-1111-1111-1111-111111111111",
                        "instructions_text": "Test instructions for migration default check",
                        "grade_scale": "eng5_np_legacy_9_step",
                    },
                )
            ).scalar_one()
            assert inserted == "research_experiment"

    async def test_eng5_experiment_backfill_applies_when_upgrading_from_pre_revision(
        self,
        migration_postgres_container: PostgresContainer,
        migration_engine: AsyncEngine,
    ) -> None:
        pre = _run_alembic_upgrade(migration_postgres_container, "cj_forced_recovery_status")
        assert pre.returncode == 0, (
            f"Alembic pre-upgrade failed:\nSTDOUT: {pre.stdout}\nSTDERR: {pre.stderr}"
        )

        async with migration_engine.begin() as conn:
            await conn.execute(
                text(
                    """
                    INSERT INTO assessment_instructions (
                        assignment_id,
                        instructions_text,
                        grade_scale
                    )
                    VALUES (:assignment_id, :instructions_text, :grade_scale)
                    """
                ),
                {
                    "assignment_id": _ENG5_EXPERIMENT_ASSIGNMENT_ID,
                    "instructions_text": "Pre-migration ENG5 experiment instructions row",
                    "grade_scale": "eng5_np_legacy_9_step",
                },
            )

        upgraded = _run_alembic_upgrade(migration_postgres_container, "head")
        assert upgraded.returncode == 0, (
            f"Alembic upgrade failed:\nSTDOUT: {upgraded.stdout}\nSTDERR: {upgraded.stderr}"
        )

        async with migration_engine.connect() as conn:
            ctx = (
                await conn.execute(
                    text(
                        """
                        SELECT context_origin
                        FROM assessment_instructions
                        WHERE assignment_id = :assignment_id
                        """
                    ),
                    {"assignment_id": _ENG5_EXPERIMENT_ASSIGNMENT_ID},
                )
            ).scalar_one()
            assert ctx == "research_experiment"

    async def test_migration_idempotency(
        self,
        migration_postgres_container: PostgresContainer,
    ) -> None:
        result1 = _run_alembic_upgrade(migration_postgres_container, "head")
        assert result1.returncode == 0, f"First upgrade failed:\n{result1.stderr}"

        result2 = _run_alembic_upgrade(migration_postgres_container, "head")
        assert result2.returncode == 0, f"Second upgrade failed (not idempotent):\n{result2.stderr}"
