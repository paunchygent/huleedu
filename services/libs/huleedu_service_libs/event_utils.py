"""
Event processing utilities for HuleEdu platform.

This module provides utilities for extracting user information from various
event data types to support real-time notifications.
"""

from __future__ import annotations

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
