"""
Pytest configuration and fixtures for File Service unit tests.

This module provides shared fixtures for testing file service functionality
including mocked dependencies and test constants.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from services.file_service.validation_models import ValidationResult


@pytest.fixture
def mock_text_extractor() -> AsyncMock:
    """Create mock text extractor."""
    extractor = AsyncMock()
    extractor.extract_text.return_value = (
        "This is a valid essay content with sufficient length for validation."
    )
    return extractor


@pytest.fixture
def mock_content_validator() -> AsyncMock:
    """Create mock content validator."""
    validator = AsyncMock()
    # Default to valid content
    validator.validate_content.return_value = ValidationResult(
        is_valid=True,
        error_code=None,
        error_message=None
    )
    return validator


@pytest.fixture
def mock_content_client() -> AsyncMock:
    """Create mock content service client."""
    client = AsyncMock()
    client.store_content.return_value = "storage_id_12345"
    return client


@pytest.fixture
def mock_event_publisher() -> AsyncMock:
    """Create mock event publisher."""
    publisher = AsyncMock()
    publisher.publish_essay_content_provisioned.return_value = None
    publisher.publish_essay_validation_failed.return_value = None
    return publisher
