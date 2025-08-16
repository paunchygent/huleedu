"""
Handler for ClientBatchPipelineRequestV1 Kafka events from API Gateway.

Processes client pipeline requests by coordinating with BCS for pipeline resolution
and initiating the resolved pipeline through the existing orchestration system.
"""

from __future__ import annotations

import json
from typing import Any

from common_core.events.client_commands import ClientBatchPipelineRequestV1
from common_core.events.envelope import EventEnvelope
from common_core.pipeline_models import PhaseName, ProcessingPipelineState
from huleedu_service_libs.logging_utils import create_service_logger

from services.batch_orchestrator_service.notification_projector import NotificationProjector
from services.batch_orchestrator_service.protocols import (
    BatchConductorClientProtocol,
    BatchRepositoryProtocol,
    PipelinePhaseCoordinatorProtocol,
)

logger = create_service_logger("bos.handlers.client_pipeline_request")


class ClientPipelineRequestHandler:
    """Handler for ClientBatchPipelineRequestV1 events from API Gateway.

    CRITICAL: This is the ONLY entry point for pipeline initiation.
    Pipelines are NEVER auto-triggered - always require explicit teacher action.
    """

    def __init__(
        self,
        bcs_client: BatchConductorClientProtocol,
        batch_repo: BatchRepositoryProtocol,
        phase_coordinator: PipelinePhaseCoordinatorProtocol,
        notification_projector: NotificationProjector | None = None,
    ) -> None:
        """Initialize with required dependencies."""
        self.bcs_client = bcs_client
        self.batch_repo = batch_repo
        self.phase_coordinator = phase_coordinator
        self.notification_projector = notification_projector

    async def handle_client_pipeline_request(self, msg: Any) -> None:
        """
        Process ClientBatchPipelineRequestV1 message from API Gateway.

        Coordinates pipeline resolution with BCS and initiates the resolved pipeline.

        Flow: Teacher clicks "Start Processing" → API Gateway → This handler → Pipeline starts

        Args:
            msg: Kafka message containing ClientBatchPipelineRequestV1 event

        Raises:
            ValueError: If message processing fails due to invalid data
            Exception: If BCS communication or pipeline initiation fails
        """
        from huleedu_service_libs.observability import (
            get_tracer,
            trace_operation,
            use_trace_context,
        )

        try:
            # Parse and validate message envelope
            envelope = self._parse_message_envelope(msg)
            # FIXED: Properly deserialize the data field following established pattern
            request_data = ClientBatchPipelineRequestV1.model_validate(envelope.data)

            batch_id = request_data.batch_id
            requested_pipeline = request_data.requested_pipeline
            correlation_id = envelope.correlation_id or request_data.client_correlation_id

            # Extract trace context if present and wrap all processing
            async def process_message() -> None:
                tracer = get_tracer("batch_orchestrator_service")
                with trace_operation(
                    tracer,
                    "kafka.consume.client_pipeline_request",
                    {
                        "messaging.system": "kafka",
                        "messaging.destination": msg.topic,
                        "messaging.operation": "consume",
                        "batch_id": batch_id,
                        "requested_pipeline": requested_pipeline,
                        "correlation_id": correlation_id,
                    },
                ):
                    logger.info(
                        "Processing client pipeline request",
                        extra={
                            "batch_id": batch_id,
                            "requested_pipeline": requested_pipeline,
                            "correlation_id": correlation_id,
                            "event_id": str(envelope.event_id),
                        },
                    )

                    # Validate batch exists and get context
                    batch_context = await self.batch_repo.get_batch_context(batch_id)
                    if not batch_context:
                        error_msg = f"Batch not found: {batch_id}"
                        logger.error(
                            error_msg,
                            extra={
                                "batch_id": batch_id,
                                "requested_pipeline": requested_pipeline,
                                "correlation_id": correlation_id,
                            },
                        )
                        raise ValueError(error_msg)

                    # Guard: Ensure batch is ready (prevents premature triggers)
                    batch_data = await self.batch_repo.get_batch_by_id(batch_id)
                    if not batch_data:
                        error_msg = f"Batch data not found: {batch_id}"
                        logger.error(
                            error_msg,
                            extra={
                                "batch_id": batch_id,
                                "requested_pipeline": requested_pipeline,
                                "correlation_id": correlation_id,
                            },
                        )
                        raise ValueError(error_msg)

                    from common_core.status_enums import BatchStatus

                    current_status = batch_data.get("status")
                    if current_status != BatchStatus.READY_FOR_PIPELINE_EXECUTION.value:
                        from huleedu_service_libs.error_handling import raise_validation_error

                        logger.error(
                            f"Batch {batch_id} not ready for pipeline execution",
                            extra={
                                "batch_id": batch_id,
                                "current_status": current_status,
                                "expected_status": BatchStatus.READY_FOR_PIPELINE_EXECUTION.value,
                                "requested_pipeline": requested_pipeline,
                                "correlation_id": correlation_id,
                            },
                        )

                        raise_validation_error(
                            service="batch_orchestrator_service",
                            operation="client_pipeline_request_handling",
                            field="batch_status",
                            message=(
                                f"Batch {batch_id} is not ready for pipeline execution. "
                                f"Current status: {current_status}"
                            ),
                            correlation_id=correlation_id,
                            batch_id=batch_id,
                            current_status=current_status,
                            expected_status=BatchStatus.READY_FOR_PIPELINE_EXECUTION.value,
                        )

                    # Check if batch already has a pipeline in progress
                    pipeline_state = await self.batch_repo.get_processing_pipeline_state(batch_id)
                    if pipeline_state and self._has_active_pipeline(pipeline_state):
                        logger.warning(
                            f"Pipeline already active for batch {batch_id}, skipping request",
                            extra={
                                "batch_id": batch_id,
                                "requested_pipeline": requested_pipeline,
                                "correlation_id": correlation_id,
                                "current_pipeline_state": pipeline_state,
                            },
                        )
                        return

                    # Convert string pipeline name to PhaseName enum for BCS client
                    try:
                        requested_pipeline_enum = PhaseName(requested_pipeline)
                    except ValueError:
                        error_msg = f"Invalid pipeline name: {requested_pipeline}"
                        logger.error(
                            error_msg,
                            extra={
                                "batch_id": batch_id,
                                "requested_pipeline": requested_pipeline,
                                "correlation_id": correlation_id,
                            },
                        )
                        raise ValueError(error_msg)

                    # Request pipeline resolution from BCS
                    try:
                        bcs_response = await self.bcs_client.resolve_pipeline(
                            batch_id, requested_pipeline_enum
                        )
                    except Exception as e:
                        error_msg = f"BCS pipeline resolution failed: {e}"
                        logger.error(
                            error_msg,
                            extra={
                                "batch_id": batch_id,
                                "requested_pipeline": requested_pipeline,
                                "correlation_id": correlation_id,
                            },
                            exc_info=True,
                        )
                        raise Exception(error_msg) from e

                    # Extract resolved pipeline from BCS response
                    resolved_pipeline_strings = bcs_response.get("final_pipeline", [])
                    if not resolved_pipeline_strings:
                        error_msg = f"BCS returned empty pipeline for {requested_pipeline}"
                        logger.error(
                            error_msg,
                            extra={
                                "batch_id": batch_id,
                                "requested_pipeline": requested_pipeline,
                                "correlation_id": correlation_id,
                                "bcs_response": bcs_response,
                            },
                        )
                        raise ValueError(error_msg)

                    # Convert string pipeline to PhaseName enums
                    resolved_pipeline = []
                    for phase_str in resolved_pipeline_strings:
                        try:
                            # Map string values to PhaseName enum
                            phase_enum = PhaseName(phase_str)
                            resolved_pipeline.append(phase_enum)
                        except ValueError:
                            logger.warning(
                                f"Unknown phase name '{phase_str}' in resolved pipeline, skipping",
                                extra={"batch_id": batch_id},
                            )
                            continue

                    logger.info(
                        "BCS resolved pipeline successfully",
                        extra={
                            "batch_id": batch_id,
                            "requested_pipeline": requested_pipeline,
                            "resolved_pipeline": [phase.value for phase in resolved_pipeline],
                            "pipeline_length": len(resolved_pipeline),
                            "correlation_id": correlation_id,
                        },
                    )

                    # Update batch with resolved pipeline
                    await self._update_batch_with_resolved_pipeline(
                        batch_id,
                        resolved_pipeline,
                        batch_context,
                    )

                    # Initiate first phase of resolved pipeline
                    try:
                        await self.phase_coordinator.initiate_resolved_pipeline(
                            batch_id=batch_id,
                            resolved_pipeline=resolved_pipeline,
                            correlation_id=correlation_id,
                            batch_context=batch_context,
                        )

                        logger.info(
                            f"Pipeline initiation completed for batch {batch_id}",
                            extra={
                                "batch_id": batch_id,
                                "requested_pipeline": requested_pipeline,
                                "resolved_pipeline": resolved_pipeline,
                                "first_phase_initiated": resolved_pipeline[0]
                                if resolved_pipeline
                                else None,
                                "correlation_id": correlation_id,
                            },
                        )

                        # CRITICAL UX: Notify teacher their "Start Processing" action succeeded
                        if self.notification_projector:
                            # Get user_id from batch context for teacher notification
                            user_id = batch_context.user_id if batch_context else None

                            if user_id:
                                await self.notification_projector.handle_batch_processing_started(
                                    batch_id=batch_id,
                                    requested_pipeline=requested_pipeline,
                                    resolved_pipeline=resolved_pipeline,
                                    user_id=user_id,
                                    correlation_id=correlation_id,
                                )
                            else:
                                logger.warning(
                                    f"No user_id found in batch context for batch {batch_id}, "
                                    "skipping notification",
                                    extra={"batch_id": batch_id, "correlation_id": correlation_id},
                                )
                    except Exception as e:
                        error_msg = (
                            f"Failed to initiate resolved pipeline for batch {batch_id}: {e}"
                        )
                        logger.error(
                            error_msg,
                            extra={
                                "batch_id": batch_id,
                                "resolved_pipeline": resolved_pipeline,
                                "correlation_id": correlation_id,
                            },
                            exc_info=True,
                        )
                        raise Exception(error_msg) from e

            # Check if envelope has trace context metadata
            if hasattr(envelope, "metadata") and envelope.metadata:
                # Use the trace context from the envelope
                with use_trace_context(envelope.metadata):
                    await process_message()
            else:
                # No trace context, process without it
                await process_message()

        except Exception as e:
            logger.error(
                f"Error processing client pipeline request: {e}",
                extra={
                    "topic": msg.topic,
                    "partition": msg.partition,
                    "offset": msg.offset,
                },
                exc_info=True,
            )
            raise

    def _parse_message_envelope(self, msg: Any) -> EventEnvelope[ClientBatchPipelineRequestV1]:
        """Parse and validate Kafka message envelope."""
        try:
            raw_message = msg.value.decode("utf-8")
            envelope = EventEnvelope[ClientBatchPipelineRequestV1].model_validate_json(raw_message)
            return envelope
        except json.JSONDecodeError as e:
            error_msg = f"Invalid JSON in client pipeline request message: {e}"
            logger.error(error_msg)
            raise ValueError(error_msg) from e
        except Exception as e:
            error_msg = f"Failed to parse client pipeline request envelope: {e}"
            logger.error(error_msg)
            raise ValueError(error_msg) from e

    def _has_active_pipeline(self, pipeline_state: ProcessingPipelineState) -> bool:
        """Check if batch has an active pipeline in progress.

        Returns True only if there are phases actively being processed.
        Completed pipelines and pending pipelines should not block new pipeline requests.
        """
        from common_core.pipeline_models import PipelineExecutionStatus

        try:
            # Direct Pydantic model access - no conversion needed
            state_obj = pipeline_state

            # Check if any phase is currently in active processing
            # PENDING_DEPENDENCIES means configured but not started - should not block
            active_statuses = {
                PipelineExecutionStatus.IN_PROGRESS,
                PipelineExecutionStatus.DISPATCH_INITIATED,
            }

            # Check all phases to see if any are actively processing
            for phase_name in PhaseName:
                phase_detail = state_obj.get_pipeline(phase_name.value)
                if phase_detail and phase_detail.status in active_statuses:
                    return True

            return False

        except Exception as e:
            logger.warning(f"Error checking pipeline state, assuming not active: {e}")
            return False

    async def _update_batch_with_resolved_pipeline(
        self,
        batch_id: str,
        resolved_pipeline: list[PhaseName],
        batch_context: Any,
    ) -> None:
        """Update batch processing state with BCS-resolved pipeline."""
        from common_core.pipeline_models import (
            PipelineExecutionStatus,
            PipelineStateDetail,
            ProcessingPipelineState,
        )

        # Fetch existing pipeline state or create a new one if it doesn't exist
        existing_state = await self.batch_repo.get_processing_pipeline_state(batch_id)
        if existing_state:
            # If state exists, update it
            updated_pipeline_state = existing_state
            # CRITICAL: Set requested_pipelines to the CURRENT pipeline execution order
            # This replaces any previous pipeline execution order
            updated_pipeline_state.requested_pipelines = [p.value for p in resolved_pipeline]

            # Update status for newly resolved phases
            for phase in resolved_pipeline:
                phase_detail = updated_pipeline_state.get_pipeline(phase.value)
                # If a phase was previously skipped or not started, set it to pending.
                if phase_detail and phase_detail.status in [
                    PipelineExecutionStatus.SKIPPED_BY_USER_CONFIG,
                    PipelineExecutionStatus.REQUESTED_BY_USER,  # Default status
                ]:
                    phase_detail.status = PipelineExecutionStatus.PENDING_DEPENDENCIES
        else:
            # If no state exists, create a new one from scratch
            pipeline_details = {}
            for phase in PhaseName:
                status = (
                    PipelineExecutionStatus.PENDING_DEPENDENCIES
                    if phase in resolved_pipeline
                    else PipelineExecutionStatus.REQUESTED_BY_USER  # Default state
                )
                pipeline_details[phase.value] = PipelineStateDetail(status=status)

            updated_pipeline_state = ProcessingPipelineState(
                batch_id=batch_id,
                requested_pipelines=[p.value for p in resolved_pipeline],
                **pipeline_details,
            )

        # Save updated state - direct Pydantic model
        await self.batch_repo.save_processing_pipeline_state(
            batch_id,
            updated_pipeline_state,
        )

        logger.info(
            "Updated batch pipeline state with BCS resolution",
            extra={
                "batch_id": batch_id,
                "resolved_pipeline": [p.value for p in resolved_pipeline],
                "requested_pipelines": updated_pipeline_state.requested_pipelines,
            },
        )
