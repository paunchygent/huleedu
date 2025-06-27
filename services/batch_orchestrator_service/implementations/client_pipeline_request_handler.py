"""
Handler for ClientBatchPipelineRequestV1 Kafka events from API Gateway.

Processes client pipeline requests by coordinating with BCS for pipeline resolution
and initiating the resolved pipeline through the existing orchestration system.
"""

from __future__ import annotations

import json
from typing import Any

from huleedu_service_libs.logging_utils import create_service_logger
from protocols import (
    BatchConductorClientProtocol,
    BatchRepositoryProtocol,
    PipelinePhaseCoordinatorProtocol,
)

from common_core.events.client_commands import ClientBatchPipelineRequestV1
from common_core.events.envelope import EventEnvelope
from common_core.pipeline_models import PhaseName

logger = create_service_logger("bos.handlers.client_pipeline_request")


class ClientPipelineRequestHandler:
    """Handler for ClientBatchPipelineRequestV1 events from API Gateway."""

    def __init__(
        self,
        bcs_client: BatchConductorClientProtocol,
        batch_repo: BatchRepositoryProtocol,
        phase_coordinator: PipelinePhaseCoordinatorProtocol,
    ) -> None:
        """Initialize with required dependencies."""
        self.bcs_client = bcs_client
        self.batch_repo = batch_repo
        self.phase_coordinator = phase_coordinator

    async def handle_client_pipeline_request(self, msg: Any) -> None:
        """
        Process ClientBatchPipelineRequestV1 message from API Gateway.

        Coordinates pipeline resolution with BCS and initiates the resolved pipeline.

        Args:
            msg: Kafka message containing ClientBatchPipelineRequestV1 event

        Raises:
            ValueError: If message processing fails due to invalid data
            Exception: If BCS communication or pipeline initiation fails
        """
        try:
            # Parse and validate message envelope
            envelope = self._parse_message_envelope(msg)
            request_data = envelope.data

            batch_id = request_data.batch_id
            requested_pipeline = request_data.requested_pipeline
            correlation_id = str(envelope.correlation_id or request_data.client_correlation_id)

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
            except Exception as e:
                error_msg = f"Failed to initiate resolved pipeline for batch {batch_id}: {e}"
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
            message_data = json.loads(msg.value.decode("utf-8"))
            envelope = EventEnvelope[ClientBatchPipelineRequestV1].model_validate(message_data)
            return envelope
        except json.JSONDecodeError as e:
            error_msg = f"Invalid JSON in client pipeline request message: {e}"
            logger.error(error_msg)
            raise ValueError(error_msg) from e
        except Exception as e:
            error_msg = f"Failed to parse client pipeline request envelope: {e}"
            logger.error(error_msg)
            raise ValueError(error_msg) from e

    def _has_active_pipeline(self, pipeline_state: dict) -> bool:
        """Check if batch has an active pipeline in progress."""
        from common_core.pipeline_models import PipelineExecutionStatus, ProcessingPipelineState

        try:
            # Convert to Pydantic model for type-safe checking
            if isinstance(pipeline_state, dict):
                state_obj = ProcessingPipelineState.model_validate(pipeline_state)
            else:
                state_obj = pipeline_state

            # Check if any phase is currently in progress
            active_statuses = {
                PipelineExecutionStatus.IN_PROGRESS,
                PipelineExecutionStatus.DISPATCH_INITIATED,
            }

            # Check all phases using the enum values
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

        # Initialize pipeline state details based on resolved pipeline
        spellcheck_detail = PipelineStateDetail(
            status=(
                PipelineExecutionStatus.PENDING_DEPENDENCIES
                if PhaseName.SPELLCHECK in resolved_pipeline
                else PipelineExecutionStatus.SKIPPED_BY_USER_CONFIG
            ),
        )
        cj_assessment_detail = PipelineStateDetail(
            status=(
                PipelineExecutionStatus.PENDING_DEPENDENCIES
                if PhaseName.CJ_ASSESSMENT in resolved_pipeline
                else PipelineExecutionStatus.SKIPPED_BY_USER_CONFIG
            ),
        )
        ai_feedback_detail = PipelineStateDetail(
            status=(
                PipelineExecutionStatus.PENDING_DEPENDENCIES
                if PhaseName.AI_FEEDBACK in resolved_pipeline
                else PipelineExecutionStatus.SKIPPED_BY_USER_CONFIG
            ),
        )
        nlp_metrics_detail = PipelineStateDetail(
            status=(
                PipelineExecutionStatus.PENDING_DEPENDENCIES
                if PhaseName.NLP in resolved_pipeline
                else PipelineExecutionStatus.SKIPPED_BY_USER_CONFIG
            ),
        )

        # Create updated pipeline state
        updated_pipeline_state = ProcessingPipelineState(
            batch_id=batch_id,
            requested_pipelines=[
                phase.value for phase in resolved_pipeline
            ],  # Convert enums to strings
            spellcheck=spellcheck_detail,
            cj_assessment=cj_assessment_detail,
            ai_feedback=ai_feedback_detail,
            nlp_metrics=nlp_metrics_detail,
        )

        # Save updated state
        await self.batch_repo.save_processing_pipeline_state(
            batch_id,
            updated_pipeline_state.model_dump(mode="json"),
        )

        logger.info(
            "Updated batch pipeline state with BCS resolution",
            extra={
                "batch_id": batch_id,
                "resolved_pipeline": resolved_pipeline,
            },
        )
