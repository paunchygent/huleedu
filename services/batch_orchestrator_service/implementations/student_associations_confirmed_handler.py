"""
Handler for StudentAssociationsConfirmedV1 events from Class Management Service.

Processes confirmed student-essay associations and transitions REGULAR batches
to READY_FOR_PIPELINE_EXECUTION state.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from common_core.events.envelope import EventEnvelope
from common_core.events.validation_events import StudentAssociationsConfirmedV1
from common_core.status_enums import BatchStatus
from huleedu_service_libs.error_handling import (
    raise_processing_error,
    raise_validation_error,
)
from huleedu_service_libs.logging_utils import create_service_logger

from services.batch_orchestrator_service.protocols import BatchRepositoryProtocol

logger = create_service_logger("bos.handlers.student_associations_confirmed")


class StudentAssociationsConfirmedHandler:
    """Handler for StudentAssociationsConfirmedV1 events from Class Management Service."""

    def __init__(
        self,
        batch_repo: BatchRepositoryProtocol,
    ) -> None:
        self.batch_repo = batch_repo
        self.logger = logger

    async def handle_student_associations_confirmed(self, msg: Any) -> None:
        """
        Handle StudentAssociationsConfirmedV1 event from Class Management Service.

        This event indicates that student-essay associations have been confirmed
        (either by human validation or timeout auto-confirmation) for a REGULAR batch.

        Workflow:
        1. Deserialize StudentAssociationsConfirmedV1 event
        2. Validate batch exists and is in correct state (AWAITING_STUDENT_VALIDATION)
        3. Store student associations for later use
        4. Update batch status to STUDENT_VALIDATION_COMPLETED
        5. Log completion of Phase 1 student matching

        After this handler completes, the batch awaits BatchEssaysReady event
        which will transition it to READY_FOR_PIPELINE_EXECUTION.
        """
        from huleedu_service_libs.observability import (
            get_tracer,
            trace_operation,
            use_trace_context,
        )

        try:
            # Deserialize the message using established EventEnvelope pattern
            raw_message = msg.value.decode("utf-8")
            envelope = EventEnvelope[StudentAssociationsConfirmedV1].model_validate_json(
                raw_message
            )
            associations_data = StudentAssociationsConfirmedV1.model_validate(envelope.data)

            batch_id = associations_data.batch_id

            # Define async function to process within trace context
            async def process_student_associations() -> None:
                tracer = get_tracer("batch_orchestrator_service")
                with trace_operation(
                    tracer,
                    "kafka.consume.student_associations_confirmed",
                    {
                        "messaging.system": "kafka",
                        "messaging.destination": msg.topic,
                        "messaging.operation": "consume",
                        "batch_id": batch_id,
                        "correlation_id": str(envelope.correlation_id),
                        "association_count": len(associations_data.associations),
                        "timeout_triggered": associations_data.timeout_triggered,
                    },
                ):
                    self.logger.info(
                        f"Processing student associations for batch {batch_id}",
                        extra={
                            "correlation_id": str(envelope.correlation_id),
                            "association_count": len(associations_data.associations),
                            "validation_summary": associations_data.validation_summary,
                        },
                    )

                    # Validate batch exists
                    batch_data = await self.batch_repo.get_batch_by_id(batch_id)
                    if not batch_data:
                        raise_validation_error(
                            service="batch_orchestrator_service",
                            operation="student_associations_confirmed_handling",
                            field="batch_id",
                            message=f"Batch not found: {batch_id}",
                            correlation_id=envelope.correlation_id,
                            batch_id=batch_id,
                        )

                    # Validate batch is in correct state
                    current_status = batch_data["status"]
                    if current_status != BatchStatus.AWAITING_STUDENT_VALIDATION.value:
                        self.logger.warning(
                            f"Batch {batch_id} is not in AWAITING_STUDENT_VALIDATION status",
                            extra={
                                "correlation_id": str(envelope.correlation_id),
                                "current_status": current_status,
                                "expected_status": BatchStatus.AWAITING_STUDENT_VALIDATION.value,
                            },
                        )
                        self.logger.warning(
                            f"Current status: {current_status}",
                            extra={
                                "correlation_id": str(envelope.correlation_id),
                                "batch_id": batch_id,
                            },
                        )
                        # Don't error - could be idempotent redelivery
                        return

                    # Store student associations for later use
                    # Note: The batch repository should handle storing these associations
                    # in a way that allows them to be retrieved during pipeline processing
                    stored_associations = [
                        {
                            "essay_id": assoc.essay_id,
                            "student_id": assoc.student_id,
                            "confidence_score": assoc.confidence_score,
                            "validation_method": assoc.validation_method,
                            "validated_by": assoc.validated_by,
                            "validated_at": assoc.validated_at.isoformat(),
                        }
                        for assoc in associations_data.associations
                    ]

                    # Student associations are stored in Class Management Service
                    # BOS only needs to track state transition, not store the data
                    self.logger.info(
                        f"Received {len(stored_associations)} confirmed associations for batch "
                        f"{batch_id}",
                        extra={
                            "correlation_id": str(envelope.correlation_id),
                            "associations_sample": stored_associations[:3]
                            if stored_associations
                            else [],
                        },
                    )

                    # Update batch status to STUDENT_VALIDATION_COMPLETED
                    # This intermediate state prevents race conditions where pipeline might
                    # start before essays are actually stored by BatchEssaysReadyHandler
                    success = await self.batch_repo.update_batch_status(
                        batch_id, BatchStatus.STUDENT_VALIDATION_COMPLETED
                    )

                    if success:
                        self.logger.info(
                            f"Batch {batch_id} transitioned to STUDENT_VALIDATION_COMPLETED",
                            extra={
                                "correlation_id": str(envelope.correlation_id),
                                "class_id": associations_data.class_id,
                                "association_count": len(associations_data.associations),
                                "timeout_triggered": associations_data.timeout_triggered,
                            },
                        )

                        # Log Phase 1 completion
                        self.logger.info(
                            f"Phase 1 student matching completed for batch {batch_id}",
                            extra={
                                "correlation_id": str(envelope.correlation_id),
                                "validation_summary": associations_data.validation_summary,
                            },
                        )
                    else:
                        raise_processing_error(
                            service="batch_orchestrator_service",
                            operation="student_associations_confirmed_handling",
                            message=f"Failed to update batch status for {batch_id}",
                            correlation_id=envelope.correlation_id,
                            batch_id=batch_id,
                        )

            # Check if envelope has trace context metadata and process accordingly
            if hasattr(envelope, "metadata") and envelope.metadata:
                with use_trace_context(envelope.metadata):
                    await process_student_associations()
            else:
                await process_student_associations()

        except Exception as e:
            # Check if it's a JSON or Pydantic validation error
            from pydantic_core import ValidationError as PydanticValidationError

            if isinstance(e, (json.JSONDecodeError, ValueError, PydanticValidationError)):
                # Handle JSON and Pydantic validation errors specifically
                self.logger.error(f"Failed to decode JSON message: {e}")
                raise_validation_error(
                    service="batch_orchestrator_service",
                    operation="student_associations_confirmed_handling",
                    field="message_format",
                    message=f"Invalid JSON in Kafka message: {e}",
                    correlation_id=uuid4(),  # Generate new correlation_id for error
                )
            # Extract batch_id if possible for better error context
            batch_id = "unknown"
            correlation_id = None
            try:
                raw_message = msg.value.decode("utf-8")
                envelope = EventEnvelope[StudentAssociationsConfirmedV1].model_validate_json(
                    raw_message
                )
                associations_data = StudentAssociationsConfirmedV1.model_validate(envelope.data)
                batch_id = associations_data.batch_id
                correlation_id = envelope.correlation_id
            except (json.JSONDecodeError, KeyError, TypeError):
                pass

            self.logger.error(
                f"Failed to process student associations for batch {batch_id}: {e}",
                extra={"correlation_id": str(correlation_id) if correlation_id else None},
            )
            raise_processing_error(
                service="batch_orchestrator_service",
                operation="student_associations_confirmed_handling",
                message=f"Failed to process student associations event: {e}",
                correlation_id=correlation_id or uuid4(),  # Generate if None
                batch_id=batch_id,
                error_details={"exception_type": type(e).__name__, "exception_message": str(e)},
            )
