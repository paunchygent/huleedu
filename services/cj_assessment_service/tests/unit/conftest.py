"""Shared fixtures for CJ Assessment Service unit tests.

This conftest makes fixtures from the fixtures directory available to all unit tests.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

# Import fixtures to make them available to all unit tests
from services.cj_assessment_service.tests.fixtures.session_provider_fixtures import (
    mock_grade_projector,
    mock_session_provider,
)

# Re-export fixtures for pytest discovery
__all__ = ["mock_session_provider", "mock_grade_projector", "base_mock_session_provider"]


# Alias for compatibility with tests that expect base_mock_session_provider
@pytest.fixture
def base_mock_session_provider(mock_session_provider: AsyncMock) -> AsyncMock:
    """Alias for mock_session_provider for backward compatibility."""
    return mock_session_provider
