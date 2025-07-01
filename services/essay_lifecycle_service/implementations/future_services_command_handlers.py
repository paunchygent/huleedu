"""
Future services command handlers for Essay Lifecycle Service.

Contains stub implementations for services that are planned but not yet implemented:
- NLP Service
- AI Feedback Service

These handlers will be expanded when the services become available.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from common_core.batch_service_models import (
        BatchServiceAIFeedbackInitiateCommandDataV1,
        BatchServiceNLPInitiateCommandDataV1,
    )

from huleedu_service_libs.logging_utils import create_service_logger

from services.essay_lifecycle_service.protocols import (
    EssayRepositoryProtocol,
    EventPublisher,
    SpecializedServiceRequestDispatcher,
)

logger = create_service_logger("future_services_command_handler")


class FutureServicesCommandHandler:
    """Handles command initiation for future services (NLP, AI Feedback)."""

    def __init__(
        self,
        repository: EssayRepositoryProtocol,
        request_dispatcher: SpecializedServiceRequestDispatcher,
        event_publisher: EventPublisher,
    ) -> None:
        self.repository = repository
        self.request_dispatcher = request_dispatcher
        self.event_publisher = event_publisher

    async def process_initiate_nlp_command(
        self, command_data: BatchServiceNLPInitiateCommandDataV1, correlation_id: UUID
    ) -> None:
        """Process NLP initiation command from Batch Orchestrator Service."""
        # TODO: Implement when NLP Service is available
        logger.info("Received NLP initiation command (STUB)")

    async def process_initiate_ai_feedback_command(
        self,
        command_data: BatchServiceAIFeedbackInitiateCommandDataV1,
        correlation_id: UUID,
    ) -> None:
        """Process AI feedback initiation command from Batch Orchestrator Service."""
        # TODO: Implement when AI Feedback Service is available
        logger.info("Received AI feedback initiation command (STUB)")
