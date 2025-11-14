"""Base event data models for all HuleEdu event contracts.

Provides foundational structures for both thin (state-tracking) and rich (business)
events. ALL event data models ultimately derive from BaseEventData.

See: libs/common_core/docs/event-envelope.md for dual-event pattern context
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from ..event_enums import ProcessingEvent
from ..metadata_models import SystemProcessingMetadata
from ..status_enums import BatchStatus, EssayStatus

if TYPE_CHECKING:
    pass  # Keep for any future type-only imports


class BaseEventData(BaseModel):
    """Universal base class for ALL event data models in HuleEdu architecture.

    Rich business events (e.g., AssessmentResultV1, EssayCreatedV1) extend
    BaseEventData directly, adding domain-specific fields. Thin state-tracking
    events inherit via ProcessingUpdate or EventTracker subclasses.

    Provides entity threading fields (entity_id, entity_type, parent_id) for
    distributed tracing across service boundaries and correlation of events
    related to the same business entity or parent workflow.
    """

    event_name: ProcessingEvent = Field(
        description=(
            "Specific event name from ProcessingEvent enum. "
            "Pydantic coerces from string during deserialization."
        )
    )
    entity_id: str | None = Field(
        default=None,
        description=(
            "Business entity ID this event relates to (essay_id, batch_id, user_id). "
            "For correlation and tracing across service boundaries."
        ),
    )
    entity_type: str | None = Field(
        default=None,
        description=(
            "Type of business entity (essay, batch, user). "
            "Clarifies entity_id context when multiple entity types share ID space."
        ),
    )
    parent_id: str | None = Field(
        default=None,
        description=(
            "Parent entity ID for hierarchical relationships (batch_id for essay events). "
            "Enables workflow correlation across parent-child boundaries."
        ),
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Event creation timestamp in UTC. Auto-generated at event construction.",
    )
    # SystemProcessingMetadata is now part of the concrete event data models below


class ProcessingUpdate(BaseEventData):
    """Base for thin state-machine transition events.

    Use ProcessingUpdate when an event represents an actual status change for
    a business entity (essay, batch). The required status field indicates the
    new lifecycle state after the transition.

    Thin events focus on state tracking with minimal business data, relying on
    status enum and system_metadata for operational context. Rich business events
    extend BaseEventData directly instead.
    """

    status: EssayStatus | BatchStatus = Field(
        description=(
            "New status of the entity after this state machine transition. "
            "Use EssayStatus for essay entities, BatchStatus for batch entities."
        )
    )
    system_metadata: SystemProcessingMetadata = Field(
        description=(
            "Operational context of THIS event's creation "
            "(service, correlation_id, error_info). "
            "Includes tracing and error tracking data."
        )
    )


class EventTracker(BaseEventData):
    """Base for informational progress events without status changes.

    Use EventTracker for lighter-weight progress updates where you need to log
    operational context or progress information WITHOUT altering the entity's
    lifecycle state. EventTracker omits the status field present in ProcessingUpdate.

    Suitable for checkpoint notifications, progress milestones, or operational
    logging that doesn't represent a state machine transition.
    """

    system_metadata: SystemProcessingMetadata = Field(
        description=(
            "Operational context of THIS event's creation "
            "(service, correlation_id, error_info). "
            "Includes tracing and error tracking data."
        )
    )


# Note: Model rebuilding is now handled explicitly in test environments (conftest.py)
# and at the package level (__init__.py) after all imports are complete.
# We no longer silently ignore rebuild failures as they indicate real issues.
