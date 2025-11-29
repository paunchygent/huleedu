"""Session provider mocks for CJ Assessment Service unit tests.

Provides mock implementations of SessionProviderProtocol for testing
database session management patterns without requiring actual database connections.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, Mock

from sqlalchemy.ext.asyncio import AsyncSession


class MockSessionProvider:
    """Mock implementing SessionProviderProtocol for unit tests.

    Provides AsyncMock sessions with properly configured sync/async methods.
    Tracks all sessions created for test assertions.
    """

    def __init__(self) -> None:
        """Initialize with empty session tracking list."""
        self._sessions: list[MagicMock] = []

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        """Yield a mock AsyncSession with standard DB methods configured.

        The returned mock session has:
        - add: Sync method (Mock)
        - flush, commit, rollback, execute, close: Async methods (AsyncMock)

        Yields:
        # Uses MagicMock with attached AsyncMocks to avoid 'coroutine never awaited' warnings
        # during introspection by test runners.
            MagicMock configured as AsyncSession for testing
        """
        # Use MagicMock container pattern to avoid introspection warnings
        mock_session = MagicMock(spec=AsyncSession)
        mock_session.add = Mock()  # Sync method
        mock_session.flush = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()
        mock_session.close = AsyncMock()
        mock_session.execute = AsyncMock(
            return_value=SimpleNamespace(scalar_one_or_none=Mock(return_value=None))
        )

        # Add get/refresh methods which are often used
        mock_session.get = AsyncMock()
        mock_session.refresh = AsyncMock()

        self._sessions.append(mock_session)
        yield mock_session

    def get_last_session(self) -> MagicMock:
        """Return the most recently created session for assertions.

        Returns:
            The last mock session created by session() context manager

        Raises:
            IndexError: If no sessions have been created yet
        """
        return self._sessions[-1]

    def get_all_sessions(self) -> list[MagicMock]:
        """Return all sessions created during test execution.

        Returns:
            List of all mock sessions in creation order
        """
        return self._sessions

    def reset(self) -> None:
        """Clear session tracking list for test cleanup."""
        self._sessions.clear()
