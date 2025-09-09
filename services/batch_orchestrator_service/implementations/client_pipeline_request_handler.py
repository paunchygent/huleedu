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
from common_core.events.pipeline_events import PipelineDeniedV1
from common_core.pipeline_models import PhaseName, ProcessingPipelineState
from huleedu_service_libs.logging_utils import create_service_logger

from services.batch_orchestrator_service.domain.pipeline_cost_strategy import PipelineCostStrategy
from services.batch_orchestrator_service.domain.pipeline_credit_guard import (
    PipelineCreditGuard,
)
from services.batch_orchestrator_service.notification_projector import NotificationProjector
from services.batch_orchestrator_service.protocols import (
    BatchConductorClientProtocol,
    BatchEventPublisherProtocol,
    BatchRepositoryProtocol,
    EntitlementsServiceProtocol,
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
        entitlements_client: EntitlementsServiceProtocol,
        cost_strategy: PipelineCostStrategy | None = None,
        credit_guard: PipelineCreditGuard | None = None,
        notification_projector: NotificationProjector | None = None,
        event_publisher: BatchEventPublisherProtocol | None = None,
    ) -> None:
        """Initialize with required dependencies."""
        self.bcs_client = bcs_client
        self.batch_repo = batch_repo
        self.phase_coordinator = phase_coordinator
        self.entitlements_client = entitlements_client
        self.cost_strategy = cost_strategy or PipelineCostStrategy()
        self.credit_guard = credit_guard or PipelineCreditGuard(
            entitlements_client=self.entitlements_client,
            cost_strategy=self.cost_strategy,
        )
        self.notification_projector = notification_projector
        self.event_publisher = event_publisher

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
                            batch_id, requested_pipeline_enum, str(correlation_id)
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

                    # PHASE 4: Credit checking before pipeline execution
                    try:
                        outcome = await self.credit_guard.evaluate(
                            batch_id=batch_id,
                            resolved_pipeline=resolved_pipeline,
                            batch_context=batch_context,
                            correlation_id=str(correlation_id),
                        )
                    except Exception as e:
                        error_msg = f"Credit check failed for batch {batch_id}: {e}"
                        logger.error(
                            error_msg,
                            extra={
                                "batch_id": batch_id,
                                "correlation_id": correlation_id,
                            },
                            exc_info=True,
                        )
                        raise Exception(error_msg) from e

                    if not outcome.allowed:
                        logger.warning(
                            "Pipeline denied due to insufficient credits",
                            extra={
                                "batch_id": batch_id,
                                "required_credits": outcome.required_credits,
                                "available_credits": outcome.available_credits,
                                "correlation_id": correlation_id,
                            },
                        )

                        # Extract identity for event payload
                        user_id = self._require_non_empty_str(
                            getattr(batch_context, "user_id", None),
                            field="user_id",
                            batch_id=batch_id,
                        )
                        org_id = getattr(batch_context, "org_id", None)

                        await self._publish_pipeline_denied_event(
                            batch_id=batch_id,
                            user_id=user_id,
                            org_id=org_id,
                            requested_pipeline=requested_pipeline,
                            denial_reason=outcome.denial_reason or "insufficient_credits",
                            required_credits=outcome.required_credits,
                            available_credits=outcome.available_credits,
                            resource_breakdown=outcome.resource_breakdown,
                            correlation_id=str(correlation_id),
                        )

                        # Stop processing - do not initiate pipeline
                        return

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
                            notif_user_id: str | None = (
                                batch_context.user_id if batch_context else None
                            )

                            if notif_user_id:
                                await self.notification_projector.handle_batch_processing_started(
                                    batch_id=batch_id,
                                    requested_pipeline=requested_pipeline,
                                    resolved_pipeline=resolved_pipeline,
                                    user_id=notif_user_id,
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

    @staticmethod
    def _require_non_empty_str(value: object | None, *, field: str, batch_id: str) -> str:
        """Validate that a value is a non-empty string and return it.

        Raises ValueError with contextual information if validation fails.
        """
        if isinstance(value, str) and value:
            return value
        raise ValueError(f"Expected non-empty string for {field} in batch context of {batch_id}")

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
        """Check if batch has an active pipeline that would conflict with a new request.

        Returns True only if there are phases actively being processed that would
        conflict with a new pipeline request. Allows sequential pipelines when
        the current pipeline is in its final phase.
        """
        from common_core.pipeline_models import PipelineExecutionStatus

        try:
            # If no requested_pipelines, nothing is active
            if not pipeline_state.requested_pipelines:
                return False

            # Check which phases are truly active (not completed/failed/skipped)
            active_phases = []
            completed_phases = []

            for phase_name in pipeline_state.requested_pipelines:
                phase_detail = pipeline_state.get_pipeline(phase_name)
                if phase_detail:
                    if phase_detail.status in {
                        PipelineExecutionStatus.IN_PROGRESS,
                        PipelineExecutionStatus.DISPATCH_INITIATED,
                    }:
                        active_phases.append(phase_name)
                    elif phase_detail.status in {
                        PipelineExecutionStatus.COMPLETED_SUCCESSFULLY,
                        PipelineExecutionStatus.COMPLETED_WITH_PARTIAL_SUCCESS,
                        PipelineExecutionStatus.FAILED,
                    }:
                        completed_phases.append(phase_name)

            # If no active phases, pipeline is not active
            if not active_phases:
                return False

            # If all requested phases are complete, pipeline is not active
            if len(completed_phases) == len(pipeline_state.requested_pipelines):
                return False

            # Check if we're in the final phase (allowing sequential execution)
            # If only the last phase is active, consider the pipeline as "completing"
            if len(active_phases) == 1:
                last_requested_phase = pipeline_state.requested_pipelines[-1]
                if active_phases[0] == last_requested_phase:
                    # Last phase is active - allow sequential pipeline to queue
                    logger.info(
                        f"Pipeline in final phase ({last_requested_phase}), "
                        "allowing sequential pipeline request",
                        extra={"active_phase": last_requested_phase},
                    )
                    return False

            # Multiple phases active or non-final phase active - block new requests
            return True

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

    async def _publish_pipeline_denied_event(
        self,
        batch_id: str,
        user_id: str,
        org_id: str | None,
        requested_pipeline: str,
        denial_reason: str,
        required_credits: int,
        available_credits: int,
        resource_breakdown: dict[str, int],
        correlation_id: str,
    ) -> None:
        """Publish PipelineDeniedV1 event when pipeline is denied due to insufficient credits.

        This event will be consumed by:
        1. API Gateway - to return 402 Payment Required response
        2. NotificationProjector - to send real-time teacher notification

        Args:
            batch_id: ID of the batch whose pipeline was denied
            user_id: User who requested the pipeline
            org_id: Organization ID (if applicable)
            requested_pipeline: Name of the pipeline that was requested
            denial_reason: Reason for denial ("insufficient_credits" or "rate_limit_exceeded")
            required_credits: Total credits required for the pipeline
            available_credits: Credits currently available
            resource_breakdown: Breakdown of required resources by type
            correlation_id: Request correlation ID for tracing
        """
        # Import here to avoid circular imports
        from common_core.event_enums import ProcessingEvent, topic_name
        from common_core.events import EventEnvelope

        try:
            # Create PipelineDeniedV1 event
            pipeline_denied_event = PipelineDeniedV1(
                entity_id=batch_id,
                entity_type="batch",
                batch_id=batch_id,
                user_id=user_id,
                org_id=org_id,
                requested_pipeline=requested_pipeline,
                denial_reason=denial_reason,
                required_credits=required_credits,
                available_credits=available_credits,
                resource_breakdown=resource_breakdown,
                correlation_id=correlation_id,
            )

            # Create event envelope
            envelope = EventEnvelope[PipelineDeniedV1](
                event_type=topic_name(ProcessingEvent.PIPELINE_DENIED),
                source_service="batch_orchestrator_service",
                data=pipeline_denied_event.model_dump(),
                correlation_id=correlation_id,
            )

            # Publish event via outbox publisher if available; else fall back to KafkaBus
            topic = topic_name(ProcessingEvent.PIPELINE_DENIED)
            if self.event_publisher is not None:
                await self.event_publisher.publish_batch_event(envelope)
            else:
                # As a minimal fallback, use KafkaBus directly
                from huleedu_service_libs.kafka_client import KafkaBus

                kafka_bus = KafkaBus(
                    client_id="batch-service-producer",
                )
                await kafka_bus.start()
                try:
                    await kafka_bus.publish(
                        topic=topic,
                        envelope=envelope,
                        key=batch_id,
                    )
                finally:
                    await kafka_bus.stop()

            logger.info(
                "Published PipelineDeniedV1 event",
                extra={
                    "batch_id": batch_id,
                    "user_id": user_id,
                    "org_id": org_id,
                    "denial_reason": denial_reason,
                    "required_credits": required_credits,
                    "available_credits": available_credits,
                    "topic": topic,
                    "correlation_id": correlation_id,
                },
            )

        except Exception as e:
            # Event publishing failure should not block the denial logic
            # The pipeline is still denied, but downstream services won't be notified
            logger.error(
                f"Failed to publish PipelineDeniedV1 event for batch {batch_id}: {e}",
                extra={
                    "batch_id": batch_id,
                    "user_id": user_id,
                    "correlation_id": correlation_id,
                },
                exc_info=True,
            )
