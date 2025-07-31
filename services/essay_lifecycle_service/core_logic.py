"""
Core business logic for the Essay Lifecycle Service.

This module contains utility functions for essay state management,
ID generation, and entity reference creation.
"""

from __future__ import annotations

from uuid import UUID, uuid4

# EntityReference removed - no longer needed with primitive parameter patterns


def generate_correlation_id() -> UUID:
    """Generate a new correlation ID for event tracking."""
    return uuid4()


# create_entity_reference function removed - EntityReference pattern eliminated
# Use primitive parameters (essay_id, batch_id, entity_type) directly instead
