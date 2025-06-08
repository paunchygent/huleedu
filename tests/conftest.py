"""
Pytest Configuration

Global configuration for HuleEdu functional testing framework.
Configures async testing, fixtures, and test collection.
"""

import asyncio
from typing import Generator

import pytest

# Configure pytest-asyncio for async test support
pytest_plugins = ["pytest_asyncio"]


def pytest_configure(config):
    """Configure pytest with custom markers and settings."""
    config.addinivalue_line("markers", "functional: mark test as functional/integration test")
    config.addinivalue_line("markers", "slow: mark test as slow running")
    config.addinivalue_line("markers", "docker: mark test as requiring Docker services")


@pytest.fixture(scope="session")
def event_loop(
    event_loop_policy: asyncio.AbstractEventLoopPolicy
) -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create an instance of the default event loop for the test session."""
    loop = event_loop_policy.new_event_loop()
    asyncio.set_event_loop(loop)  # Set this loop as current for the session context
    yield loop
    loop.close()
    asyncio.set_event_loop(None)  # Clean up by removing the loop from current context


# TODO: Add common test data fixtures
# TODO: Add authentication fixtures
# TODO: Add database fixtures
