"""Event publisher implementation for the CJ Assessment Service.

This module provides the concrete implementation of CJEventPublisherProtocol,
enabling the CJ service to publish assessment results and failures using the
TRUE OUTBOX PATTERN for transactional safety.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from huleedu_service_libs.logging_utils import create_service_logger

if TYPE_CHECKING:
    from services.cj_assessment_service.config import Settings
    from services.cj_assessment_service.implementations.outbox_manager import OutboxManager

from services.cj_assessment_service.protocols import CJEventPublisherProtocol

logger = create_service_logger("cj_assessment_service.event_publisher")


class CJEventPublisherImpl(CJEventPublisherProtocol):
    """Implementation of CJEventPublisherProtocol using TRUE OUTBOX PATTERN."""

    def __init__(self, outbox_manager: OutboxManager, settings: Settings) -> None:
        """Initialize event publisher with outbox manager for transactional safety."""
        self.outbox_manager = outbox_manager
        self.settings = settings

    async def publish_assessment_completed(
        self,
        completion_data: Any,
        correlation_id: UUID,
    ) -> None:
        """Publish CJ assessment completion event using TRUE OUTBOX PATTERN.

        Args:
            completion_data: The CJ assessment completion event data (already an EventEnvelope)
            correlation_id: Correlation ID for event tracing

        Note:
            This uses the transactional outbox pattern to ensure atomic consistency
            between database state and event publishing. Events are stored in the
            outbox table and published asynchronously by the relay worker.
        """
        # completion_data is already an EventEnvelope from event_processor.py
        # Extract aggregate information from the event data
        aggregate_id = str(correlation_id)  # Default to correlation_id
        if hasattr(completion_data, "data") and hasattr(completion_data.data, "entity_id"):
            aggregate_id = str(completion_data.data.entity_id)

        # Store in outbox using OutboxManager (TRUE OUTBOX PATTERN)
        await self.outbox_manager.publish_to_outbox(
            aggregate_type="cj_batch",
            aggregate_id=aggregate_id,
            event_type=self.settings.CJ_ASSESSMENT_COMPLETED_TOPIC,
            event_data=completion_data,  # Pass original EventEnvelope to OutboxManager
            topic=self.settings.CJ_ASSESSMENT_COMPLETED_TOPIC,
        )

        logger.info(
            "CJ assessment completion event stored in outbox",
            extra={
                "correlation_id": str(correlation_id),
                "aggregate_id": aggregate_id,
                "topic": self.settings.CJ_ASSESSMENT_COMPLETED_TOPIC,
            },
        )

    async def publish_assessment_failed(
        self,
        failure_data: Any,
        correlation_id: UUID,
    ) -> None:
        """Publish CJ assessment failure event using TRUE OUTBOX PATTERN.

        Args:
            failure_data: The CJ assessment failure event data (already an EventEnvelope)
            correlation_id: Correlation ID for event tracing

        Note:
            This uses the transactional outbox pattern to ensure atomic consistency
            between database state and event publishing. Events are stored in the
            outbox table and published asynchronously by the relay worker.
        """
        # failure_data is already an EventEnvelope from event_processor.py
        # Extract aggregate information from the event data
        aggregate_id = str(correlation_id)  # Default to correlation_id
        if hasattr(failure_data, "data") and hasattr(failure_data.data, "entity_id"):
            aggregate_id = str(failure_data.data.entity_id)

        # Store in outbox using OutboxManager (TRUE OUTBOX PATTERN)
        await self.outbox_manager.publish_to_outbox(
            aggregate_type="cj_batch",
            aggregate_id=aggregate_id,
            event_type=self.settings.CJ_ASSESSMENT_FAILED_TOPIC,
            event_data=failure_data,  # Pass original EventEnvelope to OutboxManager
            topic=self.settings.CJ_ASSESSMENT_FAILED_TOPIC,
        )

        logger.info(
            "CJ assessment failure event stored in outbox",
            extra={
                "correlation_id": str(correlation_id),
                "aggregate_id": aggregate_id,
                "topic": self.settings.CJ_ASSESSMENT_FAILED_TOPIC,
            },
        )
    
    async def publish_assessment_result(
        self,
        result_data: Any,
        correlation_id: UUID,
    ) -> None:
        """Publish assessment results to RAS using TRUE OUTBOX PATTERN.
        
        Args:
            result_data: The assessment result event data (EventEnvelope with AssessmentResultV1)
            correlation_id: Correlation ID for event tracing
            
        Note:
            This publishes rich assessment data directly to RAS, bypassing ELS.
            Uses the same outbox pattern as other event publishing methods.
        """
        # result_data is an EventEnvelope[AssessmentResultV1]
        aggregate_id = str(correlation_id)
        
        if hasattr(result_data, "data") and hasattr(result_data.data, "cj_assessment_job_id"):
            aggregate_id = str(result_data.data.cj_assessment_job_id)
        
        # Store in outbox for atomic consistency
        await self.outbox_manager.publish_to_outbox(
            aggregate_type="assessment_result",
            aggregate_id=aggregate_id,
            event_type="assessment.result.published",
            event_data=result_data,
            topic=self.settings.ASSESSMENT_RESULT_TOPIC,
        )
        
        logger.info(
            "Assessment result event stored in outbox for RAS",
            extra={
                "correlation_id": str(correlation_id),
                "aggregate_id": aggregate_id,
                "topic": self.settings.ASSESSMENT_RESULT_TOPIC,
            },
        )
