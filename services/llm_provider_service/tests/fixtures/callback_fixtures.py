"""Callback-related test fixtures."""

from typing import Callable

import pytest


@pytest.fixture
def callback_topic_factory() -> Callable[[str], str]:
    """Generate unique callback topics for tests.

    Returns:
        Function that creates unique callback topics
    """

    def _factory(test_name: str) -> str:
        """Create a callback topic for a test.

        Args:
            test_name: Name of the test (will be cleaned up)

        Returns:
            Unique callback topic name
        """
        # Clean up test name for use in topic
        clean_name = test_name.replace("test_", "").replace("_", "")

        return f"test.{clean_name}.callback.v1"

    return _factory


@pytest.fixture
def test_callback_topic(callback_topic_factory: Callable[[str], str]) -> str:
    """Pre-generated callback topic for simple tests.

    Returns:
        Standard callback topic for basic test scenarios
    """
    return callback_topic_factory("default_test_callback")


# Specific callback topics for different test scenarios
@pytest.fixture
def orchestrator_callback_topic(callback_topic_factory: Callable[[str], str]) -> str:
    """Callback topic for orchestrator tests."""
    return callback_topic_factory("orchestrator_callback")


@pytest.fixture
def processor_callback_topic(callback_topic_factory: Callable[[str], str]) -> str:
    """Callback topic for processor tests."""
    return callback_topic_factory("processor_callback")


@pytest.fixture
def queue_callback_topic(callback_topic_factory: Callable[[str], str]) -> str:
    """Callback topic for queue tests."""
    return callback_topic_factory("queue_callback")


@pytest.fixture
def performance_callback_topic(callback_topic_factory: Callable[[str], str]) -> str:
    """Callback topic for performance tests."""
    return callback_topic_factory("performance_callback")


@pytest.fixture
def integration_callback_topic(callback_topic_factory: Callable[[str], str]) -> str:
    """Callback topic for integration tests."""
    return callback_topic_factory("integration_callback")
