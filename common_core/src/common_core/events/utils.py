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

    This function creates a unique hash by combining:
    1. The entity identifier (essay_id, batch_id) to prevent collisions between
       different business entities
    2. The event_id from the envelope to ensure true duplicates are caught
    
    This approach prevents false duplicates where different entities have similar
    data (e.g., two essays with zero spelling errors), while still catching true
    duplicates from retries.

    Args:
        msg_value: The raw bytes of the Kafka message value.

    Returns:
        A SHA256 hexdigest representing the unique event.

    Examples:
        >>> # Two different essays with same result = different hashes
        >>> event1 = b'{"event_id": "abc", "data": {"entity_ref": {"entity_id": "essay1"}, "corrections_made": 0}}'
        >>> event2 = b'{"event_id": "def", "data": {"entity_ref": {"entity_id": "essay2"}, "corrections_made": 0}}'
        >>> generate_deterministic_event_id(event1) != generate_deterministic_event_id(event2)
        True
        
        >>> # Same event retried = same hash
        >>> event3 = b'{"event_id": "abc", "data": {"entity_ref": {"entity_id": "essay1"}, "corrections_made": 0}}'
        >>> generate_deterministic_event_id(event1) == generate_deterministic_event_id(event3)
        True
    """
    try:
        event_dict = json.loads(msg_value)
        
        # Use event_id from envelope as primary deduplication key
        # This handles retries perfectly - same event_id = same event
        event_id = event_dict.get("event_id", "")
        
        if event_id:
            # For properly formed events with event_id, use it directly
            # This is the most reliable way to detect true duplicates
            return hashlib.sha256(f"event:{event_id}".encode("utf-8")).hexdigest()
        
        # Fallback for events without event_id (shouldn't happen in practice)
        # Extract entity identifiers to prevent false collisions
        data_payload = event_dict.get("data", {})
        
        # Try to find entity identifier in common locations
        entity_id = ""
        if "entity_ref" in data_payload:
            entity_id = data_payload["entity_ref"].get("entity_id", "")
        elif "batch_id" in data_payload:
            entity_id = data_payload["batch_id"]
        elif "essay_id" in data_payload:
            entity_id = data_payload["essay_id"]
        
        # Create hash including entity ID to prevent collisions
        stable_data = json.dumps(data_payload, sort_keys=True, separators=(",", ":"))
        unique_string = f"{entity_id}:{stable_data}"
        
        return hashlib.sha256(unique_string.encode("utf-8")).hexdigest()

    except (json.JSONDecodeError, TypeError, UnicodeDecodeError):
        # Fallback for malformed messages
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
        return event_dict.get("correlation_id")
    except (json.JSONDecodeError, TypeError, KeyError):
        return None
