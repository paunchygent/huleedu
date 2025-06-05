"""
BatchEssaysReady message handler implementation for Batch Orchestrator Service.

Handles BatchEssaysReady events from ELS to initiate pipeline processing.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from huleedu_service_libs.logging_utils import create_service_logger
from protocols import (
    BatchEventPublisherProtocol,
    BatchRepositoryProtocol,
    DataValidationError,
    InitiationError,
    PipelinePhaseInitiatorProtocol,
)

from common_core.events.batch_coordination_events import BatchEssaysReady
from common_core.events.envelope import EventEnvelope
from common_core.pipeline_models import PhaseName, PipelineExecutionStatus

logger = create_service_logger("bos.handlers.batch_essays_ready")


class BatchEssaysReadyHandler:
    """Handler for BatchEssaysReady events from ELS."""

    def __init__(
        self,
        event_publisher: BatchEventPublisherProtocol,
        batch_repo: BatchRepositoryProtocol,
        phase_initiators_map: dict[PhaseName, PipelinePhaseInitiatorProtocol],
    ) -> None:
        self.event_publisher = event_publisher
        self.batch_repo = batch_repo
        self.phase_initiators_map = phase_initiators_map

    async def handle_batch_essays_ready(self, msg: Any) -> None:
        """
        Handle a BatchEssaysReady event to initiate the first pipeline phase dynamically.

        ARCHITECTURE IMPLEMENTATION:
        ===========================
        This implementation uses dynamic phase resolution to initiate the first
        phase in the requested_pipelines list, replacing hardcoded spellcheck logic:

        1. Deserialize BatchEssaysReady event with essay content references
        2. Determine first phase from ProcessingPipelineState.requested_pipelines[0]
        3. Perform generic idempotency check using PipelineExecutionStatus
        4. Resolve and delegate to appropriate phase initiator from phase_initiators_map
        5. Handle errors with proper state updates and diagnostic logging
        """
        try:
            # Deserialize the message
            message_data = json.loads(msg.value.decode("utf-8"))
            envelope = EventEnvelope[BatchEssaysReady](**message_data)

            batch_essays_ready_data = envelope.data
            batch_id = batch_essays_ready_data.batch_id

            logger.info(
                f"Received BatchEssaysReady for batch {batch_id}",
                extra={"correlation_id": str(envelope.correlation_id)},
            )

            # 1. Get current pipeline state to determine requested pipelines
            current_pipeline_state = await self.batch_repo.get_processing_pipeline_state(batch_id)
            if not current_pipeline_state:
                logger.error(f"No pipeline state found for batch {batch_id}")
                return

            # Handle both dict and ProcessingPipelineState object cases for backwards compatibility
            if hasattr(current_pipeline_state, "requested_pipelines"):  # Pydantic object
                requested_pipelines = current_pipeline_state.requested_pipelines
            else:  # Dictionary
                requested_pipelines = current_pipeline_state.get("requested_pipelines")

            if not requested_pipelines:
                raise DataValidationError(f"No requested pipelines found for batch {batch_id}")

            # 2. Dynamic first phase determination
            try:
                first_phase_name = PhaseName(requested_pipelines[0])
            except ValueError as e:
                raise DataValidationError(f"Invalid phase name '{requested_pipelines[0]}': {e}")

            logger.info(
                f"Initiating first phase '{first_phase_name.value}' for batch {batch_id}",
                extra={"correlation_id": str(envelope.correlation_id)},
            )

            # 3. Generic idempotency check
            if hasattr(current_pipeline_state, "get_pipeline"):  # Pydantic object
                pipeline_detail = current_pipeline_state.get_pipeline(first_phase_name.value)
                if pipeline_detail and pipeline_detail.status in [
                    PipelineExecutionStatus.DISPATCH_INITIATED,
                    PipelineExecutionStatus.IN_PROGRESS,
                    PipelineExecutionStatus.COMPLETED_SUCCESSFULLY,
                    PipelineExecutionStatus.FAILED,
                ]:
                    logger.info(
                        f"Phase {first_phase_name.value} already initiated for batch {batch_id}, skipping",
                        extra={"current_status": pipeline_detail.status.value},
                    )
                    return
            else:  # Dictionary - backwards compatibility
                phase_status_key = f"{first_phase_name.value}_status"
                phase_status = current_pipeline_state.get(phase_status_key)
                if phase_status in [
                    "DISPATCH_INITIATED",
                    "IN_PROGRESS",
                    "COMPLETED_SUCCESSFULLY",
                    "FAILED",
                ]:
                    logger.info(
                        f"Phase {first_phase_name.value} already initiated for batch {batch_id}, skipping",
                        extra={"current_status": phase_status},
                    )
                    return

            # 4. Retrieve stored batch context
            batch_context = await self.batch_repo.get_batch_context(batch_id)
            if not batch_context:
                raise DataValidationError(f"No batch context found for batch {batch_id}")

            # 5. Extract essays_to_process from BatchEssaysReady.ready_essays
            essays_to_process = batch_essays_ready_data.ready_essays
            if not essays_to_process:
                raise DataValidationError(f"BatchEssaysReady for batch {batch_id} contains no ready_essays")

            logger.info(f"Processing {len(essays_to_process)} ready essays for batch {batch_id}")

            # 6. Retrieve and use generic initiator
            initiator = self.phase_initiators_map.get(first_phase_name)
            if not initiator:
                raise DataValidationError(f"No initiator found for phase {first_phase_name}")

            # 7. Delegate to phase initiator
            try:
                await initiator.initiate_phase(
                    batch_id=batch_id,
                    phase_to_initiate=first_phase_name,
                    correlation_id=envelope.correlation_id,
                    essays_for_processing=essays_to_process,
                    batch_context=batch_context,
                )
            except InitiationError as e:
                logger.error(f"Failed to initiate phase {first_phase_name} for batch {batch_id}: {e}")

                # Mark phase as FAILED and save state
                if hasattr(current_pipeline_state, "get_pipeline"):  # Pydantic object
                    pipeline_detail = current_pipeline_state.get_pipeline(first_phase_name.value)
                    if pipeline_detail:
                        pipeline_detail.status = PipelineExecutionStatus.FAILED
                        pipeline_detail.error_info = {
                            "error": str(e),
                            "timestamp": datetime.now(timezone.utc).isoformat()
                        }
                        await self.batch_repo.save_processing_pipeline_state(batch_id, current_pipeline_state)
                else:  # Dictionary - backwards compatibility
                    updated_pipeline_state = current_pipeline_state.copy()
                    updated_pipeline_state.update({
                        f"{first_phase_name.value}_status": "FAILED",
                        f"{first_phase_name.value}_error": str(e),
                        f"{first_phase_name.value}_failed_at": datetime.now(timezone.utc).isoformat(),
                    })
                    await self.batch_repo.save_processing_pipeline_state(batch_id, updated_pipeline_state)

                # TODO: Publish diagnostic event when error event models are available
                raise

            # 8. Generic state update - mark phase as DISPATCH_INITIATED
            if hasattr(current_pipeline_state, "get_pipeline"):  # Pydantic object
                pipeline_detail = current_pipeline_state.get_pipeline(first_phase_name.value)
                if pipeline_detail:
                    pipeline_detail.status = PipelineExecutionStatus.DISPATCH_INITIATED
                    pipeline_detail.started_at = datetime.now(timezone.utc)
                    await self.batch_repo.save_processing_pipeline_state(batch_id, current_pipeline_state)
            else:  # Dictionary - backwards compatibility
                updated_pipeline_state = current_pipeline_state.copy()
                updated_pipeline_state.update({
                    f"{first_phase_name.value}_status": "DISPATCH_INITIATED",
                    f"{first_phase_name.value}_initiated_at": datetime.now(timezone.utc).isoformat(),
                })
                await self.batch_repo.save_processing_pipeline_state(batch_id, updated_pipeline_state)

            logger.info(f"Successfully initiated {first_phase_name.value} pipeline for batch {batch_id}")

        except Exception as e:
            logger.error(f"Error handling BatchEssaysReady message: {e}", exc_info=True)
            raise
