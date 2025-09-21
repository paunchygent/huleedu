"""Event processor facade for Result Aggregator Service."""

from __future__ import annotations

from typing import TYPE_CHECKING

from huleedu_service_libs.logging_utils import create_service_logger

from services.result_aggregator_service.implementations.assessment_event_handler import (
    AssessmentEventHandler,
)
from services.result_aggregator_service.implementations.batch_completion_calculator import (
    BatchCompletionCalculator,
)
from services.result_aggregator_service.implementations.batch_lifecycle_handler import (
    BatchLifecycleHandler,
)
from services.result_aggregator_service.implementations.spellcheck_event_handler import (
    SpellcheckEventHandler,
)
from services.result_aggregator_service.protocols import EventProcessorProtocol

if TYPE_CHECKING:
    from common_core.events import (
        BatchEssaysRegistered,
        ELSBatchPhaseOutcomeV1,
        EventEnvelope,
        SpellcheckResultV1,
    )
    from common_core.events.batch_coordination_events import BatchPipelineCompletedV1
    from common_core.events.cj_assessment_events import AssessmentResultV1
    from common_core.events.essay_lifecycle_events import EssaySlotAssignedV1

    from services.result_aggregator_service.protocols import (
        BatchRepositoryProtocol,
        CacheManagerProtocol,
        EventPublisherProtocol,
        StateStoreProtocol,
    )

logger = create_service_logger("result_aggregator.event_processor")


class EventProcessorImpl(EventProcessorProtocol):
    """Facade for event processing that delegates to specialized handlers."""

    def __init__(
        self,
        batch_repository: "BatchRepositoryProtocol",
        state_store: "StateStoreProtocol",
        cache_manager: "CacheManagerProtocol",
        event_publisher: "EventPublisherProtocol",
    ):
        """Initialize with dependencies and create specialized handlers."""
        self.batch_repository = batch_repository
        self.state_store = state_store
        self.cache_manager = cache_manager
        self.event_publisher = event_publisher

        # Create completion calculator
        self.completion_calculator = BatchCompletionCalculator(batch_repository)

        # Initialize specialized handlers
        self.batch_lifecycle = BatchLifecycleHandler(
            batch_repository=batch_repository,
            state_store=state_store,
            cache_manager=cache_manager,
            event_publisher=event_publisher,
            completion_calculator=self.completion_calculator,
        )

        self.spellcheck_handler = SpellcheckEventHandler(
            batch_repository=batch_repository,
            state_store=state_store,
            cache_manager=cache_manager,
        )

        self.assessment_handler = AssessmentEventHandler(
            batch_repository=batch_repository,
            state_store=state_store,
            cache_manager=cache_manager,
            event_publisher=event_publisher,
        )

    async def process_batch_registered(
        self,
        envelope: "EventEnvelope[BatchEssaysRegistered]",
        data: "BatchEssaysRegistered",
    ) -> None:
        """Process batch registration event."""
        await self.batch_lifecycle.process_batch_registered(envelope, data)

    async def process_essay_slot_assigned(
        self,
        envelope: "EventEnvelope[EssaySlotAssignedV1]",
        data: "EssaySlotAssignedV1",
    ) -> None:
        """Process essay slot assignment event for file traceability."""
        await self.assessment_handler.process_essay_slot_assigned(envelope, data)

    async def process_batch_phase_outcome(
        self,
        envelope: "EventEnvelope[ELSBatchPhaseOutcomeV1]",
        data: "ELSBatchPhaseOutcomeV1",
    ) -> None:
        """Process batch phase outcome event."""
        await self.batch_lifecycle.process_batch_phase_outcome(envelope, data)

    async def process_spellcheck_result(
        self,
        envelope: "EventEnvelope[SpellcheckResultV1]",
        data: "SpellcheckResultV1",
    ) -> None:
        """Process rich spellcheck result event with business metrics."""
        await self.spellcheck_handler.process_spellcheck_result(envelope, data)

    async def process_assessment_result(
        self,
        envelope: "EventEnvelope[AssessmentResultV1]",
        data: "AssessmentResultV1",
    ) -> None:
        """Process assessment result event with rich business data from CJ Assessment Service."""
        await self.assessment_handler.process_assessment_result(envelope, data)

    async def process_pipeline_completed(
        self,
        event: "BatchPipelineCompletedV1",
    ) -> None:
        """Process pipeline completion for final result aggregation."""
        await self.batch_lifecycle.process_pipeline_completed(event)
