"""
BatchContentProvisioningCompleted event handler for Phase 1 Student Matching Integration.

Handles BatchContentProvisioningCompletedV1 events from ELS to determine if student matching
is required and initiate the appropriate Phase 1 workflow.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from common_core.events.batch_coordination_events import BatchContentProvisioningCompletedV1
from common_core.events.envelope import EventEnvelope
from common_core.pipeline_models import PhaseName
from common_core.status_enums import BatchStatus
from huleedu_service_libs.error_handling import (
    raise_processing_error,
    raise_validation_error,
)
from huleedu_service_libs.logging_utils import create_service_logger

from services.batch_orchestrator_service.protocols import (
    BatchRepositoryProtocol,
    PipelinePhaseInitiatorProtocol,
)

logger = create_service_logger("bos.handlers.content_provisioning_completed")


class BatchContentProvisioningCompletedHandler:
    """Handler for BatchContentProvisioningCompleted events from ELS."""

    def __init__(
        self,
        batch_repo: BatchRepositoryProtocol,
        phase_initiators_map: dict[PhaseName, PipelinePhaseInitiatorProtocol],
    ) -> None:
        self.batch_repo = batch_repo
        self.phase_initiators_map = phase_initiators_map
        self.logger = logger

    async def handle_batch_content_provisioning_completed(self, msg: Any) -> None:
        """
        Handle BatchContentProvisioningCompleted event for Phase 1 student matching.

        PHASE 1 STUDENT MATCHING WORKFLOW:
        ===============================
        1. Deserialize BatchContentProvisioningCompletedV1 event
        2. Retrieve batch context to determine GUEST vs REGULAR batch type
        3. For REGULAR batches (class_id present): Initiate student matching phase
        4. For GUEST batches (class_id None): No action needed - ELS handles readiness

        Note: ELS is responsible for publishing BatchEssaysReady for both GUEST and REGULAR
        batches. For REGULAR batches, ELS waits for student associations. For GUEST batches,
        ELS publishes immediately after content provisioning.
        """
        from huleedu_service_libs.observability import (
            get_tracer,
            trace_operation,
            use_trace_context,
        )

        try:
            # Deserialize the message
            message_data = json.loads(msg.value.decode("utf-8"))
            envelope = EventEnvelope[BatchContentProvisioningCompletedV1](**message_data)

            content_completed_data = envelope.data
            batch_id = content_completed_data.batch_id

            # Define async function to process within trace context
            async def process_content_provisioning_completed() -> None:
                tracer = get_tracer("batch_orchestrator_service")
                with trace_operation(
                    tracer,
                    "kafka.consume.batch_content_provisioning_completed",
                    {
                        "messaging.system": "kafka",
                        "messaging.destination": msg.topic,
                        "messaging.operation": "consume",
                        "batch_id": batch_id,
                        "correlation_id": str(envelope.correlation_id),
                    },
                ):
                    self.logger.info(
                        f"Processing content provisioning completed for batch {batch_id}",
                        extra={"correlation_id": str(envelope.correlation_id)},
                    )

                    # Retrieve batch context to determine batch type (GUEST vs REGULAR)
                    batch_context = await self.batch_repo.get_batch_context(batch_id)
                    if batch_context is None:
                        raise_validation_error(
                            service="batch_orchestrator_service",
                            operation="content_provisioning_completed_handling",
                            field="batch_context",
                            message=f"Batch context not found for batch {batch_id}",
                            correlation_id=envelope.correlation_id,
                            batch_id=batch_id,
                        )

                    # Determine batch type based on class_id presence
                    is_regular_batch = batch_context.class_id is not None
                    batch_type = "REGULAR" if is_regular_batch else "GUEST"

                    self.logger.info(
                        f"Batch {batch_id} identified as {batch_type} batch "
                        f"(class_id: {batch_context.class_id})",
                        extra={"correlation_id": str(envelope.correlation_id)},
                    )

                    if is_regular_batch:
                        # REGULAR batch: Update status and initiate Phase 1 student matching
                        self.logger.info(
                            f"Updating REGULAR batch {batch_id} status to "
                            "AWAITING_STUDENT_VALIDATION",
                            extra={"correlation_id": str(envelope.correlation_id)},
                        )

                        # Update batch status to indicate awaiting student validation
                        await self.batch_repo.update_batch_status(
                            batch_id, BatchStatus.AWAITING_STUDENT_VALIDATION
                        )

                        self.logger.info(
                            f"Initiating Phase 1 student matching for REGULAR batch {batch_id}",
                            extra={"correlation_id": str(envelope.correlation_id)},
                        )

                        # Retrieve essays from batch repository
                        batch_essays = await self.batch_repo.get_batch_essays(batch_id)
                        if not batch_essays:
                            raise_validation_error(
                                service="batch_orchestrator_service",
                                operation="content_provisioning_completed_handling",
                                field="batch_essays",
                                message=f"No essays found for batch {batch_id}",
                                correlation_id=envelope.correlation_id,
                                batch_id=batch_id,
                            )

                        # Get the student matching initiator
                        student_matching_initiator = self.phase_initiators_map.get(
                            PhaseName.STUDENT_MATCHING
                        )

                        if not student_matching_initiator:
                            raise_processing_error(
                                service="batch_orchestrator_service",
                                operation="content_provisioning_completed_handling",
                                message=(
                                    "Student matching initiator not found in phase initiators map"
                                ),
                                correlation_id=envelope.correlation_id,
                                batch_id=batch_id,
                            )

                        await student_matching_initiator.initiate_phase(
                            batch_id=batch_id,
                            phase_to_initiate=PhaseName.STUDENT_MATCHING,
                            correlation_id=envelope.correlation_id,
                            essays_for_processing=batch_essays,
                            batch_context=batch_context,
                        )
                    else:
                        # GUEST batch: Update status to ready for pipeline and store essays
                        self.logger.info(
                            f"GUEST batch {batch_id} content provisioning completed. "
                            "Updating status to READY_FOR_PIPELINE_EXECUTION",
                            extra={"correlation_id": str(envelope.correlation_id)},
                        )

                        # Update batch status to ready for pipeline execution
                        await self.batch_repo.update_batch_status(
                            batch_id, BatchStatus.READY_FOR_PIPELINE_EXECUTION
                        )

                        # Store essays from the event for later pipeline processing
                        if content_completed_data.essays_for_processing:
                            await self.batch_repo.store_batch_essays(
                                batch_id, content_completed_data.essays_for_processing
                            )
                            self.logger.info(
                                f"Stored {len(content_completed_data.essays_for_processing)} "
                                f"essays for GUEST batch {batch_id}",
                                extra={"correlation_id": str(envelope.correlation_id)},
                            )

            # Check if envelope has trace context metadata and process accordingly
            if hasattr(envelope, "metadata") and envelope.metadata:
                with use_trace_context(envelope.metadata):
                    await process_content_provisioning_completed()
            else:
                await process_content_provisioning_completed()

        except json.JSONDecodeError as e:
            self.logger.error(f"Failed to decode JSON message: {e}")
            raise_validation_error(
                service="batch_orchestrator_service",
                operation="content_provisioning_completed_handling",
                field="message_format",
                message=f"Invalid JSON in Kafka message: {e}",
                correlation_id=uuid4(),  # Generate new correlation_id for error
            )

        except Exception as e:
            # Extract batch_id if possible for better error context
            batch_id = "unknown"
            correlation_id = None
            try:
                message_data = json.loads(msg.value.decode("utf-8"))
                envelope = EventEnvelope[BatchContentProvisioningCompletedV1](**message_data)
                batch_id = envelope.data.batch_id
                correlation_id = envelope.correlation_id
            except (json.JSONDecodeError, KeyError, TypeError):
                pass

            self.logger.error(
                f"Failed to process content provisioning completed for batch {batch_id}: {e}",
                extra={"correlation_id": str(correlation_id) if correlation_id else None},
            )
            raise_processing_error(
                service="batch_orchestrator_service",
                operation="content_provisioning_completed_handling",
                message=f"Failed to process content provisioning completed event: {e}",
                correlation_id=correlation_id or uuid4(),  # Generate if None
                batch_id=batch_id,
                error_details={"exception_type": type(e).__name__, "exception_message": str(e)},
            )
