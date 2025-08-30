"""Resource consumption event models.

Defines the standard event for reporting actual billable resource usage across
services. This enables accurate credit consumption in the Entitlements Service
and analytics in downstream systems.

Pattern: Thin, versioned event data models that extend BaseEventData and carry
only business-relevant fields. Correlation and transport details live in the
EventEnvelope.
"""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import Field

from ..event_enums import ProcessingEvent
from .base_event_models import BaseEventData

__all__ = ["ResourceConsumptionV1"]


class ResourceConsumptionV1(BaseEventData):
    """Event for tracking billable resource consumption.

    Published by processing services (e.g., CJ Assessment, AI Feedback) to report
    actual resource usage. Consumed by Entitlements Service for credit tracking.

    Notes:
    - `entity_id` and `entity_type` from BaseEventData identify the business entity
      (typically BOS batch id and "batch").
    - Correlation and transport metadata is carried by the EventEnvelope.
    """

    event_name: ProcessingEvent = Field(
        default=ProcessingEvent.RESOURCE_CONSUMPTION_REPORTED,
        description="Canonical name for resource consumption events",
    )

    # Identity
    user_id: str = Field(description="User who owns the workload")
    org_id: str | None = Field(default=None, description="Organization, if applicable")

    # Resource details
    resource_type: str = Field(
        description='Billable metric (e.g., "cj_comparison", "ai_feedback_generation")'
    )
    quantity: int = Field(ge=0, description="Number of resources consumed")

    # Service metadata
    service_name: str = Field(description="Producing service name")
    processing_id: str = Field(description="Internal job or processing ID for tracing")
    consumed_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="Timestamp of consumption"
    )
