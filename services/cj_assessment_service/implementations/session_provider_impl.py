"""Session provider implementation for CJ Assessment Service."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from services.cj_assessment_service.protocols import SessionProviderProtocol


class CJSessionProviderImpl(SessionProviderProtocol):
    """Provide AsyncSession contexts backed by a shared AsyncEngine."""

    def __init__(self, engine: AsyncEngine) -> None:
        """Initialize session provider with shared engine."""
        self._session_maker = async_sessionmaker(
            engine,
            expire_on_commit=False,
            class_=AsyncSession,
        )

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        """Yield an AsyncSession and ensure it is closed."""
        session = self._session_maker()
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
