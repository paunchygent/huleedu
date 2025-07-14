"""
Test Event Factory with Unique ID Generation

Prevents idempotency collisions by ensuring test events have unique IDs
across different test runs while maintaining deterministic behavior within
a single test run.
"""

import hashlib
import time
import uuid
from datetime import UTC, datetime
from typing import Any


class EventIdFactory:
    """Factory for generating unique test event IDs that prevent Redis collisions."""

    def __init__(self, test_run_id: str | None = None) -> None:
        """
        Initialize with a unique test run identifier.

        Args:
            test_run_id: Unique identifier for this test run. If None, generates one.
        """
        self.test_run_id = test_run_id or self._generate_test_run_id()
        self.event_counter = 0

    def _generate_test_run_id(self) -> str:
        """Generate a unique test run identifier."""
        # Combine timestamp + random UUID to ensure uniqueness
        timestamp = int(time.time() * 1000)  # millisecond precision
        random_part = str(uuid.uuid4()).replace("-", "")[:8]
        return f"{timestamp}_{random_part}"

    def create_unique_event_id(self, base_data: dict[str, Any]) -> uuid.UUID:
        """
        Create a unique event ID based on test run ID + counter + base data.

        This ensures:
        1. Different test runs generate different event IDs (prevents Redis collisions)
        2. Same test run generates deterministic IDs (supports test repeatability)
        3. Different events within same test run have different IDs

        Args:
            base_data: Base event data to include in ID generation

        Returns:
            Unique UUID for this event
        """
        self.event_counter += 1

        # Create deterministic but unique hash
        hash_input = f"{self.test_run_id}_{self.event_counter}_{str(base_data)}"
        hash_digest = hashlib.sha256(hash_input.encode()).hexdigest()

        # Convert hash to UUID format
        uuid_str = (
            f"{hash_digest[:8]}-{hash_digest[8:12]}-{hash_digest[12:16]}-"
            f"{hash_digest[16:20]}-{hash_digest[20:32]}"
        )
        return uuid.UUID(uuid_str)

    def create_unique_correlation_id(self) -> uuid.UUID:
        """Create a unique correlation ID for this test run."""
        return self.create_unique_event_id(
            {"type": "correlation", "timestamp": datetime.now(UTC).isoformat()}
        )

    def create_unique_batch_id(self, batch_suffix: str = "") -> str:
        """Create a unique batch ID for this test run."""
        base_id = str(self.create_unique_event_id({"type": "batch", "suffix": batch_suffix}))
        return base_id

    def get_test_run_info(self) -> dict[str, Any]:
        """Get information about this test run for debugging."""
        return {
            "test_run_id": self.test_run_id,
            "events_generated": self.event_counter,
            "started_at": datetime.now(UTC).isoformat(),
        }


# Global factory instance for tests
_test_event_factory: EventIdFactory | None = None


def get_test_event_factory() -> EventIdFactory:
    """Get or create the global test event factory."""
    global _test_event_factory
    if _test_event_factory is None:
        _test_event_factory = EventIdFactory()
    return _test_event_factory


def reset_test_event_factory() -> EventIdFactory:
    """Reset the global test event factory with a new test run ID."""
    global _test_event_factory
    _test_event_factory = EventIdFactory()
    return _test_event_factory


def create_unique_test_correlation_id() -> uuid.UUID:
    """Convenience function to create unique correlation ID for tests."""
    return get_test_event_factory().create_unique_correlation_id()


def create_unique_test_batch_id(suffix: str = "") -> str:
    """Convenience function to create unique batch ID for tests."""
    return get_test_event_factory().create_unique_batch_id(suffix)
