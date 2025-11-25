from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from services.cj_assessment_service.implementations.session_provider_impl import (
    CJSessionProviderImpl,
)


@pytest.fixture
async def sqlite_engine() -> AsyncGenerator[AsyncEngine, None]:
    """Provide in-memory SQLite engine for session provider tests."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.execute(
            text("CREATE TABLE demo_items (id INTEGER PRIMARY KEY AUTOINCREMENT, value TEXT)")
        )
    yield engine
    await engine.dispose()


@pytest.fixture
def session_provider(sqlite_engine: AsyncEngine) -> CJSessionProviderImpl:
    """Create CJ session provider bound to shared engine."""
    return CJSessionProviderImpl(sqlite_engine)


@pytest.mark.asyncio
async def test_session_provider_allows_multiple_sequential_sessions(
    session_provider: CJSessionProviderImpl,
) -> None:
    async with session_provider.session() as session:
        await session.execute(text("INSERT INTO demo_items (value) VALUES ('first')"))
        await session.commit()

    async with session_provider.session() as session:
        result = await session.execute(text("SELECT COUNT(*) FROM demo_items"))
        count = result.scalar_one()

    assert count == 1


@pytest.mark.asyncio
async def test_session_closed_after_context_exit(
    session_provider: CJSessionProviderImpl,
) -> None:
    async with session_provider.session() as session:
        await session.execute(text("SELECT 1"))
        connection = await session.connection()

    assert connection.closed
