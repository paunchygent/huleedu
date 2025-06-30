"""Integration tests for PostgreSQLSpellcheckRepository using Testcontainers.

The pattern mirrors other service-level repository tests so CI remains
consistent across the mono-repo.
"""
from __future__ import annotations

from typing import AsyncGenerator
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer

from common_core.status_enums import SpellcheckJobStatus as SCJobStatus
from services.spell_checker_service.config import Settings
from services.spell_checker_service.implementations.spell_repository_postgres_impl import (
    PostgreSQLSpellcheckRepository,
)
from services.spell_checker_service.models_db import Base, SpellcheckToken

# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="function")
async def postgres_container() -> AsyncGenerator[PostgresContainer, None]:
    """Spin up a disposable Postgres instance for each test function."""

    with PostgresContainer("postgres:15") as container:  # noqa: S608 docker image OK
        yield container


@pytest.fixture(scope="function")
async def async_engine(
    postgres_container: PostgresContainer,
) -> AsyncGenerator[AsyncEngine, None]:
    """Async SQLAlchemy engine bound to container DB."""

    conn_url = postgres_container.get_connection_url()
    if "+psycopg2://" in conn_url:
        conn_url = conn_url.replace("+psycopg2://", "+asyncpg://")
    elif "postgresql://" in conn_url:
        conn_url = conn_url.replace("postgresql://", "postgresql+asyncpg://")

    engine = create_async_engine(conn_url, echo=False, pool_size=5, max_overflow=0)

    # enable pg_trgm required for GIN index on varchar
    from sqlalchemy import text

    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm;"))

    # create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture(scope="function")
async def repo(async_engine: AsyncEngine) -> AsyncGenerator[PostgreSQLSpellcheckRepository, None]:
    """Repository instance wired to the test database."""

    class TestSettings(Settings):
        DATABASE_URL: str = str(async_engine.url)

    repository = PostgreSQLSpellcheckRepository(TestSettings())
    # override the engine created in __init__ with the fixture engine
    repository.engine = async_engine  # type: ignore[assignment]
    repository.async_session_maker = async_sessionmaker(
        async_engine, expire_on_commit=False
    )
    yield repository


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_and_fetch_job(repo: PostgreSQLSpellcheckRepository) -> None:
    batch_id = uuid4()
    essay_id = uuid4()

    job_id = await repo.create_job(batch_id=batch_id, essay_id=essay_id)
    job = await repo.get_job(job_id)

    assert job is not None
    assert job.batch_id == batch_id
    assert job.essay_id == essay_id
    assert job.status == SCJobStatus.PENDING


@pytest.mark.asyncio
async def test_update_status(repo: PostgreSQLSpellcheckRepository) -> None:
    job_id = await repo.create_job(batch_id=uuid4(), essay_id=uuid4())

    await repo.update_status(job_id, SCJobStatus.IN_PROGRESS)
    updated = await repo.get_job(job_id)
    assert updated is not None
    assert updated.status == SCJobStatus.IN_PROGRESS


@pytest.mark.asyncio
async def test_add_tokens(repo: PostgreSQLSpellcheckRepository) -> None:
    job_id = await repo.create_job(batch_id=uuid4(), essay_id=uuid4())

    tokens = [
        ("mispelled", ["misspelled"], 15, "This is a mispelled word."),
        ("hous", ["house"], 37, None),
    ]
    await repo.add_tokens(job_id, tokens)

    job = await repo.get_job(job_id)
    assert job is not None
    assert len(job.tokens) == 2

    # Ensure token relationship was persisted
    assert {t.token for t in job.tokens} == {"mispelled", "hous"}
