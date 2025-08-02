"""
ELSBatchPhaseOutcomeV1 message handler implementation for Batch Orchestrator Service.

Handles phase completion events from ELS for dynamic pipeline orchestration.
Implements Phase 3 data propagation and dynamic phase coordination.
"""

from __future__ import annotations

from typing import Any

from common_core.events.els_bos_events import ELSBatchPhaseOutcomeV1
from common_core.events.envelope import EventEnvelope
from huleedu_service_libs.logging_utils import create_service_logger

from services.batch_orchestrator_service.protocols import PipelinePhaseCoordinatorProtocol

logger = create_service_logger("bos.handlers.els_batch_phase_outcome")


class ELSBatchPhaseOutcomeHandler:
    """Handler for ELSBatchPhaseOutcomeV1 events from ELS."""

    def __init__(
        self,
        phase_coordinator: PipelinePhaseCoordinatorProtocol,
    ) -> None:
        self.phase_coordinator = phase_coordinator
        self._phase_transition_metric = None  # Will be initialized with actual metric
        self._commands_metric = None  # Will be initialized with actual metric

    async def handle_els_batch_phase_outcome(self, msg: Any) -> None:
        """
        Handle ELSBatchPhaseOutcomeV1 events from ELS for dynamic pipeline orchestration.

        This implements Phase 3 Sub-task 2: Handle ELSBatchPhaseOutcomeV1 Event.
        Upon receiving phase completion, determines next phase and publishes appropriate command.

        PHASE 3 ENHANCEMENT: Data Propagation
        ====================================
        Extracts processed_essays from the event and passes them to the phase coordinator
        for proper text_storage_id propagation between pipeline phases.

        FIXED: Now uses proper EventEnvelope deserialization for architectural compliance.
        """
        from huleedu_service_libs.observability import (
            get_tracer,
            trace_operation,
            use_trace_context,
        )

        try:
            # FIXED: Use proper EventEnvelope deserialization like other services
            envelope = EventEnvelope[ELSBatchPhaseOutcomeV1].model_validate_json(msg.value)
            event_data = ELSBatchPhaseOutcomeV1.model_validate(envelope.data)  # envelope.data is dict
            correlation_id = envelope.correlation_id

            batch_id = event_data.batch_id
            completed_phase = event_data.phase_name
            phase_status = event_data.phase_status
            processed_essays_for_next_phase = event_data.processed_essays
            failed_essay_ids = event_data.failed_essay_ids

            # Define async function to process within trace context
            async def process_phase_outcome() -> None:
                tracer = get_tracer("batch_orchestrator_service")
                with trace_operation(
                    tracer,
                    "kafka.consume.els_batch_phase_outcome",
                    {
                        "messaging.system": "kafka",
                        "messaging.destination": msg.topic,
                        "messaging.operation": "consume",
                        "batch_id": batch_id,
                        "completed_phase": completed_phase,
                        "phase_status": phase_status,
                        "correlation_id": str(correlation_id),
                    },
                ):
                    # Note: No manual validation needed -
                    # Pydantic EventEnvelope parsing ensures required fields exist

                    processed_count = len(processed_essays_for_next_phase)
                    failed_count = len(failed_essay_ids)
                    logger.info(
                        f"Received ELS batch phase outcome: batch={batch_id}, "
                        f"phase={completed_phase}, status={phase_status}, "
                        f"processed={processed_count}, failed={failed_count}",
                        extra={"correlation_id": str(correlation_id)},
                    )

                    # Delegate to phase coordinator for pipeline orchestration with data propagation
                    await self.phase_coordinator.handle_phase_concluded(
                        batch_id=batch_id,
                        completed_phase=completed_phase,
                        phase_status=phase_status,
                        correlation_id=correlation_id,
                        processed_essays_for_next_phase=processed_essays_for_next_phase,
                    )

            # Check if envelope has trace context metadata and process accordingly
            if hasattr(envelope, "metadata") and envelope.metadata:
                with use_trace_context(envelope.metadata):
                    await process_phase_outcome()
            else:
                await process_phase_outcome()

        except Exception as e:
            logger.error(f"Error handling ELSBatchPhaseOutcomeV1 event: {e}", exc_info=True)
            raise
