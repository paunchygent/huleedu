"""
Event processing utilities for HuleEdu platform.

This module provides utilities for robust event processing, including
deterministic ID generation for idempotency guarantees.
"""

import hashlib
import json


def generate_deterministic_event_id(msg_value: bytes) -> str:
    """
    Generates a deterministic ID for an event based on its stable content.

    This function ignores transient envelope metadata (like event_id, timestamp)
    by focusing on the 'data' payload, ensuring that retried events produce
    the same key. This is critical for idempotency - producer retries due to
    network issues would generate new event_id UUIDs, but the business data
    remains the same.

    Args:
        msg_value: The raw bytes of the Kafka message value.

    Returns:
        A SHA256 hexdigest representing the stable event content.

    Examples:
        >>> event_bytes = b'{"data": {"batch_id": "123", "status": "completed"}}'
        >>> id1 = generate_deterministic_event_id(event_bytes)
        >>> id2 = generate_deterministic_event_id(event_bytes)
        >>> id1 == id2
        True
    """
    try:
        event_dict = json.loads(msg_value)

        # The 'data' field contains the business payload, which is stable.
        # This excludes transient envelope fields like event_id, timestamp.
        data_payload = event_dict.get('data', {})

        # Create a canonical representation by sorting keys. This ensures that
        # {"b": 2, "a": 1} and {"a": 1, "b": 2} produce the same hash.
        stable_string = json.dumps(data_payload, sort_keys=True, separators=(",", ":"))

        return hashlib.sha256(stable_string.encode('utf-8')).hexdigest()

    except (json.JSONDecodeError, TypeError, UnicodeDecodeError):
        # Fallback for malformed messages, events without a 'data' field,
        # or non-UTF8 bytes. Hashing the entire raw message value is a safe default.
        # This ensures we still get deterministic IDs even for edge cases.
        return hashlib.sha256(msg_value).hexdigest()


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
        return event_dict.get('correlation_id')
    except (json.JSONDecodeError, TypeError, KeyError):
        return None
