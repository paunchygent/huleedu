"""
Common test utilities and fixtures for Essay Lifecycle Service unit tests.

Provides reusable mocks and fixtures for Unit of Work pattern testing.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def mock_session_factory():
    """
    Mock session factory for Unit of Work pattern.

    Returns a factory that creates AsyncSession mocks with proper
    async context manager support for transactions.
    """
    # Create the transaction mock
    mock_transaction = AsyncMock()
    mock_transaction.__aenter__.return_value = None
    mock_transaction.__aexit__.return_value = None

    # Create the session mock
    mock_session = AsyncMock()
    mock_session.__aenter__.return_value = mock_session
    mock_session.__aexit__.return_value = None
    # Make begin() return the transaction directly (not as a coroutine)
    mock_session.begin = MagicMock(return_value=mock_transaction)

    # Create the factory that returns the session when called
    mock_factory = MagicMock()
    mock_factory.return_value = mock_session

    # Attach the session to the factory for easy access in tests
    mock_factory._test_session = mock_session
    mock_factory._test_transaction = mock_transaction

    return mock_factory


def create_mock_session():
    """
    Create a standalone mock session for tests that need direct session access.

    Returns an AsyncSession mock with transaction support.
    """
    mock_transaction = AsyncMock()
    mock_transaction.__aenter__.return_value = None
    mock_transaction.__aexit__.return_value = None

    mock_session = AsyncMock()
    mock_session.__aenter__.return_value = mock_session
    mock_session.__aexit__.return_value = None
    mock_session.begin = MagicMock(return_value=mock_transaction)

    return mock_session
