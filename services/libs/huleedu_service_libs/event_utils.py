"""
Event processing utilities for HuleEdu platform.

This module provides utilities for extracting user information from various
event data types to support real-time notifications, as well as utilities
for robust event processing including deterministic ID generation for
idempotency guarantees.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def extract_user_id_from_event_data(event_data: Any) -> str | None:
    """
    Extract user_id from event data using various field name patterns.

    This utility handles the different user ID field names used across
    event types in the HuleEdu platform.

    Args:
        event_data: The event data object (typically a Pydantic model)

    Returns:
        The user ID as a string if found, None otherwise
    """
    # Common user ID field patterns in order of preference
    user_id_fields = [
        "user_id",
        "created_by_user_id",
        "updated_by_user_id",
        "created_by_id",
        "updated_by_id",
        "owner_id",
        "author_id",
    ]

    for field_name in user_id_fields:
        if hasattr(event_data, field_name):
            user_id = getattr(event_data, field_name)
            if user_id:
                return str(user_id)

    return None


def extract_correlation_id_as_string(correlation_id: Any) -> str | None:
    """
    Extract correlation ID as string for consistent logging and UI payloads.

    Args:
        correlation_id: UUID or string correlation ID

    Returns:
        Correlation ID as string if present, None otherwise
    """
    if correlation_id is not None:
        return str(correlation_id)
    return None


def generate_deterministic_event_id(msg_value: bytes) -> str:
    """
    Generates a deterministic ID for an event based on its business data payload.

    This function creates a stable hash of the `data` field within an event
    envelope. It ignores all envelope-level metadata (like `event_id`,
    `correlation_id`, `event_timestamp`), ensuring that two events with
    identical business data produce the same ID, which is critical for
    idempotency.

    To guarantee a consistent hash, the `data` dictionary is serialized into a
    canonical JSON string with sorted keys before hashing.

    Args:
        msg_value: The raw bytes of the Kafka message value (a JSON object).

    Returns:
        A SHA256 hexdigest of the canonical data payload.

    Raises:
        ValueError: If the message is not valid JSON or is missing the `data` field.

    Examples:
        >>> # Two events with same data but different metadata = SAME hash
        >>> event1 = b'{"event_id": "abc", "data": {"entity_id": "essay1", "status": "complete"}}'
        >>> event2 = b'{"event_id": "def", "data": {"entity_id": "essay1", "status": "complete"}}'
        >>> generate_deterministic_event_id(event1) == generate_deterministic_event_id(event2)
        True

        >>> # Two events with different data = DIFFERENT hash
        >>> event3 = b'{"event_id": "ghi", "data": {"entity_id": "essay2", "status": "complete"}}'
        >>> generate_deterministic_event_id(event1) != generate_deterministic_event_id(event3)
        True
    """
    try:
        event_dict = json.loads(msg_value)
        data_payload = event_dict.get("data")

        if data_payload is None:
            raise ValueError("Event message must contain a 'data' field.")

        # Create a canonical representation by sorting keys
        canonical_data = json.dumps(data_payload, sort_keys=True).encode("utf-8")

        # Return the SHA256 hash of the canonical data
        return hashlib.sha256(canonical_data).hexdigest()

    except (json.JSONDecodeError, TypeError) as e:
        raise ValueError(f"Failed to decode or process event message: {e}") from e


def extract_correlation_id_from_event(msg_value: bytes) -> str | None:
    """
    Extracts correlation ID from an event envelope for tracing purposes.

    Args:
        msg_value: The raw bytes of the Kafka message value.

    Returns:
        The correlation ID as a string if found, None otherwise.
    """
    try:
        event_dict = json.loads(msg_value)
        correlation_id = event_dict.get("correlation_id")

        # Runtime validation for type safety
        if correlation_id is not None and not isinstance(correlation_id, str):
            raise TypeError(f"Expected correlation_id to be str or None, got: {type(correlation_id)}")

        return correlation_id
    except (json.JSONDecodeError, TypeError, KeyError):
        return None
