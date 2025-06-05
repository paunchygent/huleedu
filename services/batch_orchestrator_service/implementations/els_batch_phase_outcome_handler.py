"""
ELSBatchPhaseOutcomeV1 message handler implementation for Batch Orchestrator Service.

Handles phase completion events from ELS for dynamic pipeline orchestration.
Implements Phase 3 data propagation and dynamic phase coordination.
"""

from __future__ import annotations

import json
from typing import Any

from huleedu_service_libs.logging_utils import create_service_logger
from protocols import PipelinePhaseCoordinatorProtocol

from common_core.metadata_models import EssayProcessingInputRefV1

logger = create_service_logger("bos.handlers.els_batch_phase_outcome")


class ELSBatchPhaseOutcomeHandler:
    """Handler for ELSBatchPhaseOutcomeV1 events from ELS."""

    def __init__(
        self,
        phase_coordinator: PipelinePhaseCoordinatorProtocol,
    ) -> None:
        self.phase_coordinator = phase_coordinator

    async def handle_els_batch_phase_outcome(self, msg: Any) -> None:
        """
        Handle ELSBatchPhaseOutcomeV1 events from ELS for dynamic pipeline orchestration.

        This implements Phase 3 Sub-task 2: Handle ELSBatchPhaseOutcomeV1 Event.
        Upon receiving phase completion, determines next phase and publishes appropriate command.

        PHASE 3 ENHANCEMENT: Data Propagation
        ====================================
        Extracts processed_essays from the event and passes them to the phase coordinator
        for proper text_storage_id propagation between pipeline phases.
        """
        try:
            # Deserialize the ELSBatchPhaseOutcomeV1 event
            message_data = json.loads(msg.value.decode("utf-8"))

            # Parse as EventEnvelope but access data directly since we don't have the
            # ELSBatchPhaseOutcomeV1 import in this file
            event_data = message_data.get("data", {})
            batch_id = event_data.get("batch_id")
            completed_phase = event_data.get("phase_name")
            phase_status = event_data.get("phase_status")
            processed_essays_data = event_data.get("processed_essays", [])
            failed_essay_ids = event_data.get("failed_essay_ids", [])
            correlation_id = message_data.get("correlation_id")

            if not batch_id or not completed_phase:
                logger.warning(
                    "Received ELSBatchPhaseOutcomeV1 event with missing batch_id or phase_name"
                )
                return

            logger.info(
                f"Received ELS batch phase outcome: batch={batch_id}, "
                f"phase={completed_phase}, status={phase_status}, "
                f"processed={len(processed_essays_data)}, failed={len(failed_essay_ids)}",
                extra={"correlation_id": str(correlation_id)},
            )

            # PHASE 3 ENHANCEMENT: Convert processed_essays to proper type
            processed_essays_for_next_phase = None
            if processed_essays_data:
                try:
                    processed_essays_for_next_phase = [
                        EssayProcessingInputRefV1(**essay_data)
                        for essay_data in processed_essays_data
                    ]
                    logger.info(
                        f"Extracted {len(processed_essays_for_next_phase)} processed essays "
                        f"for next phase propagation",
                        extra={"correlation_id": str(correlation_id)},
                    )
                except Exception as e:
                    logger.error(
                        f"Error parsing processed_essays data: {e}",
                        extra={"correlation_id": str(correlation_id)},
                    )
                    # Continue without processed essays - coordinator will handle gracefully

            # Delegate to phase coordinator for pipeline orchestration with data propagation
            await self.phase_coordinator.handle_phase_concluded(
                batch_id=batch_id,
                completed_phase=completed_phase,
                phase_status=phase_status,
                correlation_id=correlation_id,
                processed_essays_for_next_phase=processed_essays_for_next_phase,
            )

        except Exception as e:
            logger.error(f"Error handling ELSBatchPhaseOutcomeV1 event: {e}", exc_info=True)
            raise
