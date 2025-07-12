"""Verify DI provider wiring for spellchecker_service.

Ensures that the Dishka container can resolve the spell-check repository and
that schema initialisation succeeds against a real Postgres instance.
"""

from __future__ import annotations

from typing import AsyncGenerator

import pytest
from dishka import make_async_container
from testcontainers.postgres import PostgresContainer

from services.spellchecker_service.config import Settings
from services.spellchecker_service.di import SpellCheckerServiceProvider
from services.spellchecker_service.implementations.spell_repository_postgres_impl import (
    PostgreSQLSpellcheckRepository,
)
from services.spellchecker_service.repository_protocol import SpellcheckRepositoryProtocol


@pytest.fixture(scope="function")
async def postgres_container() -> AsyncGenerator[PostgresContainer, None]:
    with PostgresContainer("postgres:15") as container:  # noqa: S608 docker ok in tests
        yield container


@pytest.fixture(scope="function")
async def patch_settings(
    postgres_container: PostgresContainer, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Monkey-patch global settings object so DI uses test DB URL."""
    conn_url = postgres_container.get_connection_url()
    if "+psycopg2://" in conn_url:
        conn_url = conn_url.replace("+psycopg2://", "+asyncpg://")
    elif "postgresql://" in conn_url:
        conn_url = conn_url.replace("postgresql://", "postgresql+asyncpg://")

    # Extract connection components from URL
    from urllib.parse import urlparse

    parsed = urlparse(conn_url)

    class TestSettings(Settings):
        DB_HOST: str = parsed.hostname or "localhost"
        DB_PORT: int = parsed.port or 5432
        DB_USER: str = parsed.username or "postgres"
        DB_PASSWORD: str = parsed.password or "postgres"
        DB_NAME: str = parsed.path.lstrip("/") if parsed.path else "postgres"

    test_settings = TestSettings()
    # replace singletons in both modules
    monkeypatch.setattr("services.spellchecker_service.config.settings", test_settings)
    monkeypatch.setattr("services.spellchecker_service.di.settings", test_settings)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_container_resolves_repository(
    postgres_container: PostgresContainer, patch_settings: None
) -> None:  # noqa: PT004 fixture used
    """Integration test: DI container resolves PostgreSQL repository with proper extensions."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    from services.spellchecker_service.models_db import Base

    # Create PostgreSQL engine from testcontainer
    conn_url = postgres_container.get_connection_url()
    if "+psycopg2://" in conn_url:
        conn_url = conn_url.replace("+psycopg2://", "+asyncpg://")
    elif "postgresql://" in conn_url:
        conn_url = conn_url.replace("postgresql://", "postgresql+asyncpg://")

    engine = create_async_engine(conn_url, echo=False, pool_size=5, max_overflow=0)

    # Setup PostgreSQL extensions and schema
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm;"))
        await conn.run_sync(Base.metadata.create_all)

    provider = SpellCheckerServiceProvider(engine=engine)
    container = make_async_container(provider)
    try:
        repo: SpellcheckRepositoryProtocol = await container.get(SpellcheckRepositoryProtocol)
        assert isinstance(repo, PostgreSQLSpellcheckRepository)

        # Sanity: can create a job (ensures DB wiring is live)
        import uuid

        await repo.create_job(batch_id=uuid.uuid4(), essay_id=uuid.uuid4())
    finally:
        await container.close()
        await engine.dispose()
