"""
Batch command handler implementation for Essay Lifecycle Service.

Implements BatchCommandHandler protocol for processing batch commands from BOS
using injected service-specific command handlers.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

if TYPE_CHECKING:
    from common_core.batch_service_models import (
        BatchServiceAIFeedbackInitiateCommandDataV1,
        BatchServiceCJAssessmentInitiateCommandDataV1,
        BatchServiceNLPInitiateCommandDataV1,
        BatchServiceSpellcheckInitiateCommandDataV1,
        BatchServiceStudentMatchingInitiateCommandDataV1,
    )

from services.essay_lifecycle_service.implementations.cj_assessment_command_handler import (
    CJAssessmentCommandHandler,
)
from services.essay_lifecycle_service.implementations.future_services_command_handlers import (
    FutureServicesCommandHandler,
)
from services.essay_lifecycle_service.implementations.spellcheck_command_handler import (
    SpellcheckCommandHandler,
)
from services.essay_lifecycle_service.protocols import BatchCommandHandler


class DefaultBatchCommandHandler(BatchCommandHandler):
    """Default implementation of BatchCommandHandler protocol using injected service handlers."""

    def __init__(
        self,
        spellcheck_handler: SpellcheckCommandHandler,
        cj_assessment_handler: CJAssessmentCommandHandler,
        future_services_handler: FutureServicesCommandHandler,
        student_matching_handler: Any | None = None,  # StudentMatchingCommandHandler
    ) -> None:
        """
        Initialize with injected service-specific command handlers.

        Args:
            spellcheck_handler: Handler for spellcheck commands
            cj_assessment_handler: Handler for CJ assessment commands
            future_services_handler: Handler for future service commands
            student_matching_handler: Handler for Phase 1 student matching commands
        """
        self.spellcheck_handler = spellcheck_handler
        self.cj_assessment_handler = cj_assessment_handler
        self.future_services_handler = future_services_handler
        self.student_matching_handler = student_matching_handler

    async def process_initiate_spellcheck_command(
        self,
        command_data: BatchServiceSpellcheckInitiateCommandDataV1,
        correlation_id: UUID,
    ) -> None:
        """Process spellcheck initiation command from Batch Orchestrator Service."""
        await self.spellcheck_handler.process_initiate_spellcheck_command(
            command_data, correlation_id
        )

    async def process_initiate_nlp_command(
        self, command_data: BatchServiceNLPInitiateCommandDataV1, correlation_id: UUID
    ) -> None:
        """Process NLP initiation command from Batch Orchestrator Service."""
        await self.future_services_handler.process_initiate_nlp_command(
            command_data, correlation_id
        )

    async def process_initiate_ai_feedback_command(
        self,
        command_data: BatchServiceAIFeedbackInitiateCommandDataV1,
        correlation_id: UUID,
    ) -> None:
        """Process AI feedback initiation command from Batch Orchestrator Service."""
        await self.future_services_handler.process_initiate_ai_feedback_command(
            command_data, correlation_id
        )

    async def process_initiate_cj_assessment_command(
        self,
        command_data: BatchServiceCJAssessmentInitiateCommandDataV1,
        correlation_id: UUID,
    ) -> None:
        """Process CJ assessment initiation command from Batch Orchestrator Service."""
        await self.cj_assessment_handler.process_initiate_cj_assessment_command(
            command_data, correlation_id
        )

    async def process_student_matching_command(
        self,
        command_data: BatchServiceStudentMatchingInitiateCommandDataV1,
        correlation_id: UUID,
    ) -> None:
        """Process Phase 1 student matching command from Batch Orchestrator Service."""
        if self.student_matching_handler is None:
            raise NotImplementedError("Student matching handler not configured")

        await self.student_matching_handler.handle_student_matching_command(
            command_data, correlation_id
        )
