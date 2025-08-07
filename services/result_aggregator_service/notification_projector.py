"""Teacher notification projector for Result Aggregator Service.

Projects internal result aggregation events to teacher notifications.
This will be fully implemented in Session 3.1 of the RAS Event Publishing Infrastructure task.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from huleedu_service_libs.logging_utils import create_service_logger

if TYPE_CHECKING:
    from common_core.events.result_events import BatchAssessmentCompletedV1, BatchResultsReadyV1
    from huleedu_service_libs.protocols import KafkaPublisherProtocol

logger = create_service_logger("result_aggregator_service.notification_projector")


class ResultNotificationProjector:
    """Projects internal result aggregation events to teacher notifications.
    
    This is a stub implementation that will be completed in Session 3.1.
    It follows the CANONICAL NOTIFICATION PATTERN - direct invocation 
    after domain event (NO Kafka round-trip).
    """

    def __init__(
        self,
        kafka_publisher: KafkaPublisherProtocol,
    ) -> None:
        self.kafka_publisher = kafka_publisher

    async def handle_batch_results_ready(self, event: BatchResultsReadyV1) -> None:
        """Project batch completion to high-priority teacher notification.
        
        Will be implemented in Session 3.1 to create TeacherNotificationRequestedV1
        and publish to WebSocket service.
        """
        logger.info(
            "Batch results ready notification handler called (stub)",
            extra={
                "batch_id": event.batch_id,
                "user_id": event.user_id,
            },
        )
        # TODO: Implement in Session 3.1

    async def handle_batch_assessment_completed(self, event: BatchAssessmentCompletedV1) -> None:
        """Project CJ assessment completion to teacher notification.
        
        Will be implemented in Session 3.1 to create TeacherNotificationRequestedV1
        and publish to WebSocket service.
        """
        logger.info(
            "Batch assessment completed notification handler called (stub)",
            extra={
                "batch_id": event.batch_id,
                "user_id": event.user_id,
                "assessment_job_id": event.assessment_job_id,
            },
        )
        # TODO: Implement in Session 3.1
