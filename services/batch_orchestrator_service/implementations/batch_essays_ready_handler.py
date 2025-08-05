"""
BatchEssaysReady message handler implementation for Batch Orchestrator Service.

Handles BatchEssaysReady events from ELS to initiate pipeline processing.
"""

from __future__ import annotations

from typing import Any

from common_core.events.batch_coordination_events import BatchEssaysReady
from common_core.events.envelope import EventEnvelope
from common_core.status_enums import BatchStatus
from huleedu_service_libs.error_handling import (
    raise_validation_error,
)
from huleedu_service_libs.logging_utils import create_service_logger

from services.batch_orchestrator_service.protocols import (
    BatchEventPublisherProtocol,
    BatchRepositoryProtocol,
)

logger = create_service_logger("bos.handlers.batch_essays_ready")


class BatchEssaysReadyHandler:
    """Handler for BatchEssaysReady events from ELS."""

    def __init__(
        self,
        event_publisher: BatchEventPublisherProtocol,
        batch_repo: BatchRepositoryProtocol,
    ) -> None:
        self.event_publisher = event_publisher
        self.batch_repo = batch_repo
        self.logger = logger

    async def handle_batch_essays_ready(self, msg: Any) -> None:
        """
        Handle a BatchEssaysReady event by storing essays for later client-triggered processing.

        UPDATED ARCHITECTURE:
        ====================
        This handler stores essay data and transitions batch state based on type:
        - GUEST batches: Already in READY_FOR_PIPELINE_EXECUTION (no action)
        - REGULAR batches: Transition from STUDENT_VALIDATION_COMPLETED to READY

        1. Deserialize BatchEssaysReady event with essay content references
        2. Store essays in batch repository for later pipeline processing
        3. Check batch status and transition if needed (REGULAR batches only)
        4. Log that batch is ready and awaiting client trigger
        """
        from huleedu_service_libs.observability import (
            get_tracer,
            trace_operation,
            use_trace_context,
        )

        try:
            # Deserialize the message
            raw_message = msg.value.decode("utf-8")
            envelope = EventEnvelope[BatchEssaysReady].model_validate_json(raw_message)

            batch_essays_ready_data = BatchEssaysReady.model_validate(envelope.data)
            batch_id = batch_essays_ready_data.batch_id

            # Define async function to process within trace context
            async def process_batch_ready() -> None:
                tracer = get_tracer("batch_orchestrator_service")
                with trace_operation(
                    tracer,
                    "kafka.consume.batch_essays_ready",
                    {
                        "messaging.system": "kafka",
                        "messaging.destination": msg.topic,
                        "messaging.operation": "consume",
                        "batch_id": batch_id,
                        "correlation_id": str(envelope.correlation_id),
                    },
                ):
                    self.logger.info(
                        f"Received BatchEssaysReady for batch {batch_id}",
                        extra={"correlation_id": str(envelope.correlation_id)},
                    )

                    # Store essays from BatchEssaysReady for later client-triggered processing
                    ready_essays = batch_essays_ready_data.ready_essays
                    if not ready_essays:
                        raise_validation_error(
                            service="batch_orchestrator_service",
                            operation="handle_batch_essays_ready",
                            field="ready_essays",
                            message=(
                                f"BatchEssaysReady for batch {batch_id} contains no ready_essays"
                            ),
                            correlation_id=envelope.correlation_id,
                            batch_id=batch_id,
                        )

                    # Store essays for later pipeline processing
                    essays_data = ready_essays
                    self.logger.info(
                        f"Batch {batch_id} ready for processing with "
                        f"{len(essays_data)} essays - awaiting client trigger",
                        extra={"correlation_id": str(envelope.correlation_id)},
                    )

                    # Debug logging for essay storage
                    self.logger.debug(
                        f"About to store {len(essays_data)} essays for batch {batch_id}"
                    )

                    # Store essays in repository for client-triggered pipeline processing
                    storage_success = await self.batch_repo.store_batch_essays(
                        batch_id, essays_data
                    )

                    # Log educational context for debugging and observability
                    # This context is already stored during batch registration
                    # and will be retrieved when the pipeline is triggered
                    self.logger.info(
                        "Batch educational context from ELS",
                        extra={
                            "batch_id": batch_id,
                            "course_code": str(batch_essays_ready_data.course_code),
                            "course_language": batch_essays_ready_data.course_language,
                            "class_type": batch_essays_ready_data.class_type,
                            "teacher_first_name": getattr(
                                batch_essays_ready_data, "teacher_first_name", None
                            ),
                            "teacher_last_name": getattr(
                                batch_essays_ready_data, "teacher_last_name", None
                            ),
                        },
                    )

                    if storage_success:
                        self.logger.info(
                            f"Successfully stored {len(essays_data)} essays for batch {batch_id}",
                        )
                    else:
                        self.logger.error(f"Failed to store essays for batch {batch_id}")

                    self.logger.debug(
                        f"Essay storage completed for batch {batch_id}, success: {storage_success}",
                    )

                    # Check current batch status and transition if needed
                    batch_data = await self.batch_repo.get_batch_by_id(batch_id)
                    if batch_data:
                        current_status = batch_data.get("status")

                        # For REGULAR batches coming from student validation
                        if current_status == BatchStatus.STUDENT_VALIDATION_COMPLETED.value:
                            state_success = await self.batch_repo.update_batch_status(
                                batch_id, BatchStatus.READY_FOR_PIPELINE_EXECUTION
                            )
                            if state_success:
                                self.logger.info(
                                    f"REGULAR batch {batch_id} transitioned to "
                                    "READY_FOR_PIPELINE_EXECUTION after receiving essays",
                                    extra={"correlation_id": str(envelope.correlation_id)},
                                )
                        # For GUEST batches, already in READY state - no action needed
                        elif current_status == BatchStatus.READY_FOR_PIPELINE_EXECUTION.value:
                            self.logger.debug(
                                f"GUEST batch {batch_id} already in "
                                "READY_FOR_PIPELINE_EXECUTION state",
                                extra={"correlation_id": str(envelope.correlation_id)},
                            )
                        else:
                            self.logger.warning(
                                f"Batch {batch_id} in unexpected state: {current_status}",
                                extra={"correlation_id": str(envelope.correlation_id)},
                            )

            # Check if envelope has trace context metadata and process accordingly
            if hasattr(envelope, "metadata") and envelope.metadata:
                with use_trace_context(envelope.metadata):
                    await process_batch_ready()
            else:
                await process_batch_ready()

        except Exception as e:
            self.logger.error(f"Error handling BatchEssaysReady message: {e}", exc_info=True)
            raise
