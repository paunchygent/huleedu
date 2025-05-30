"""
Specialized service request dispatcher implementation for Essay Lifecycle Service.

Implements SpecializedServiceRequestDispatcher protocol for dispatching requests to specialized services.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from aiokafka import AIOKafkaProducer
    from common_core.events.ai_feedback_events import AIFeedbackInputDataV1
    from common_core.metadata_models import EssayProcessingInputRefV1

    from config import Settings

from huleedu_service_libs.logging_utils import create_service_logger

from protocols import SpecializedServiceRequestDispatcher


class DefaultSpecializedServiceRequestDispatcher(SpecializedServiceRequestDispatcher):
    """Default implementation of SpecializedServiceRequestDispatcher protocol."""

    def __init__(self, producer: AIOKafkaProducer, settings: Settings) -> None:
        self.producer = producer
        self.settings = settings

    async def dispatch_spellcheck_requests(
        self,
        essays_to_process: list[EssayProcessingInputRefV1],
        language: str,
        batch_correlation_id: UUID | None = None,
    ) -> None:
        """Dispatch individual spellcheck requests to Spell Checker Service."""
        # TODO: Implement spellcheck request dispatching
        # Create EssayLifecycleSpellcheckRequestV1 for each essay
        # Publish to spell checker service topic
        logger = create_service_logger("specialized_service_dispatcher")
        logger.info(
            "Dispatching spellcheck requests (STUB)",
            extra={"essay_count": len(essays_to_process), "language": language},
        )

    async def dispatch_nlp_requests(
        self,
        essays_to_process: list[EssayProcessingInputRefV1],
        language: str,
        batch_correlation_id: UUID | None = None,
    ) -> None:
        """Dispatch individual NLP requests to NLP Service."""
        # TODO: Implement when NLP Service is available
        logger = create_service_logger("specialized_service_dispatcher")
        logger.info("Dispatching NLP requests (STUB)")

    async def dispatch_ai_feedback_requests(
        self,
        essays_to_process: list[EssayProcessingInputRefV1],
        context: AIFeedbackInputDataV1,
        batch_correlation_id: UUID | None = None,
    ) -> None:
        """Dispatch individual AI feedback requests to AI Feedback Service."""
        # TODO: Implement when AI Feedback Service is available
        logger = create_service_logger("specialized_service_dispatcher")
        logger.info("Dispatching AI feedback requests (STUB)")
