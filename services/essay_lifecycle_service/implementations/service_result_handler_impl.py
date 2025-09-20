"""
Service result handler implementation for Essay Lifecycle Service.

Handles results from specialized services like spell checker and CJ assessment,
integrating with EssayStateMachine for proper state transitions.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from common_core.events.cj_assessment_events import (
    CJAssessmentCompletedV1,
    CJAssessmentFailedV1,
)
from common_core.events.nlp_events import BatchNlpAnalysisCompletedV1
from common_core.events.spellcheck_models import SpellcheckResultDataV1, SpellcheckResultV1
from common_core.status_enums import EssayStatus
from huleedu_service_libs.logging_utils import create_service_logger

# Import event constants from state machine to ensure consistency

# Import at runtime to avoid circular imports
if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from services.essay_lifecycle_service.protocols import (
        BatchPhaseCoordinator,
        EssayRepositoryProtocol,
        ServiceResultHandler,
    )

# Import EssayStateMachine at runtime since it's used in the code
from services.essay_lifecycle_service.protocols import (
    BatchPhaseCoordinator,
    EssayRepositoryProtocol,
    ServiceResultHandler,
)

logger = create_service_logger("service_result_handler")


class DefaultServiceResultHandler(ServiceResultHandler):
    """Facade for service result handling that delegates to specialized handlers."""

    def __init__(
        self,
        repository: EssayRepositoryProtocol,
        batch_coordinator: BatchPhaseCoordinator,
        session_factory: async_sessionmaker,
    ) -> None:
        self.repository = repository
        self.batch_coordinator = batch_coordinator
        self.session_factory = session_factory

        # Import handlers here to avoid circular imports
        from services.essay_lifecycle_service.implementations.cj_result_handler import (
            CJResultHandler,
        )
        from services.essay_lifecycle_service.implementations.nlp_result_handler import (
            NLPResultHandler,
        )
        from services.essay_lifecycle_service.implementations.spellcheck_result_handler import (
            SpellcheckResultHandler,
        )

        # Initialize delegate handlers
        self.spellcheck_handler = SpellcheckResultHandler(
            repository, batch_coordinator, session_factory
        )
        self.cj_handler = CJResultHandler(repository, batch_coordinator, session_factory)
        self.nlp_handler = NLPResultHandler(repository, batch_coordinator, session_factory)

    async def handle_spellcheck_result(
        self,
        result_data: SpellcheckResultDataV1,
        correlation_id: UUID,
        confirm_idempotency: Any = None,
    ) -> bool:
        """Delegate spellcheck result handling to SpellcheckResultHandler."""
        return await self.spellcheck_handler.handle_spellcheck_result(
            result_data, correlation_id, confirm_idempotency
        )

    async def handle_spellcheck_rich_result(
        self,
        result_data: SpellcheckResultV1,
        correlation_id: UUID,
    ) -> bool:
        """Delegate rich spellcheck metrics handling to SpellcheckResultHandler."""
        return await self.spellcheck_handler.handle_spellcheck_rich_result(
            result_data, correlation_id
        )

    async def handle_spellcheck_phase_completed(
        self,
        essay_id: str,
        batch_id: str,
        status: EssayStatus,
        corrected_text_storage_id: str | None,
        error_code: str | None,
        correlation_id: UUID,
        confirm_idempotency: Any = None,
    ) -> bool:
        """Delegate spellcheck phase completion to SpellcheckResultHandler."""
        return await self.spellcheck_handler.handle_spellcheck_phase_completed(
            essay_id,
            batch_id,
            status,
            corrected_text_storage_id,
            error_code,
            correlation_id,
            confirm_idempotency,
        )

    async def handle_cj_assessment_completed(
        self,
        result_data: CJAssessmentCompletedV1,
        correlation_id: UUID,
        confirm_idempotency: Any = None,
    ) -> bool:
        """Delegate CJ assessment completion to CJResultHandler."""
        return await self.cj_handler.handle_cj_assessment_completed(
            result_data, correlation_id, confirm_idempotency
        )

    async def handle_cj_assessment_failed(
        self,
        result_data: CJAssessmentFailedV1,
        correlation_id: UUID,
    ) -> bool:
        """Delegate CJ assessment failure to CJResultHandler."""
        return await self.cj_handler.handle_cj_assessment_failed(result_data, correlation_id)

    async def handle_nlp_analysis_completed(
        self,
        result_data: BatchNlpAnalysisCompletedV1,
        correlation_id: UUID,
        confirm_idempotency: Any = None,
    ) -> bool:
        """Delegate NLP analysis completion to NLPResultHandler."""
        return await self.nlp_handler.handle_nlp_analysis_completed(
            result_data, correlation_id, confirm_idempotency
        )
