"""Verify DI provider wiring for spell_checker_service.

Ensures that the Dishka container can resolve the spell-check repository and
that schema initialisation succeeds against a real Postgres instance.
"""

from __future__ import annotations

from typing import AsyncGenerator

import pytest
from dishka import make_async_container
from testcontainers.postgres import PostgresContainer

from services.spell_checker_service.config import Settings
from services.spell_checker_service.di import SpellCheckerServiceProvider
from services.spell_checker_service.implementations.spell_repository_postgres_impl import (
    PostgreSQLSpellcheckRepository,
)
from services.spell_checker_service.repository_protocol import SpellcheckRepositoryProtocol


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

    class TestSettings(Settings):
        DATABASE_URL: str = conn_url

    test_settings = TestSettings()
    # replace singletons in both modules
    monkeypatch.setattr("services.spell_checker_service.config.settings", test_settings)
    monkeypatch.setattr("services.spell_checker_service.di.settings", test_settings)


@pytest.mark.asyncio
async def test_container_resolves_repository(patch_settings: None) -> None:  # noqa: PT004 fixture used
    provider = SpellCheckerServiceProvider()
    container = make_async_container(provider)
    try:
        repo: SpellcheckRepositoryProtocol = await container.get(SpellcheckRepositoryProtocol)
        assert isinstance(repo, PostgreSQLSpellcheckRepository)

        # Sanity: can create a job (ensures DB wiring is live)
        import uuid

        await repo.create_job(batch_id=uuid.uuid4(), essay_id=uuid.uuid4())
    finally:
        await container.close()
