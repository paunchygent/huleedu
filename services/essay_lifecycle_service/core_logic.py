"""
Core business logic for the Essay Lifecycle Service.

This module contains utility functions for essay state management,
ID generation, and entity reference creation.
"""

from __future__ import annotations

from uuid import UUID, uuid4

from common_core.metadata_models import EntityReference


def generate_correlation_id() -> UUID:
    """Generate a new correlation ID for event tracking."""
    return uuid4()


def create_entity_reference(essay_id: str, batch_id: str | None = None) -> EntityReference:
    """
    Create an EntityReference for an essay.

    Args:
        essay_id: The essay identifier
        batch_id: Optional batch identifier

    Returns:
        EntityReference instance for the essay
    """
    return EntityReference(entity_id=essay_id, entity_type="essay", parent_id=batch_id)
