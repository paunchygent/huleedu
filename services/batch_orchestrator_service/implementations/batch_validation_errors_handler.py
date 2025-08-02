"""
BatchValidationErrors message handler implementation for Batch Orchestrator Service.

Handles BatchValidationErrorsV1 events from ELS following structured error handling.
Part of the new dual-event architecture that separates success and error flows.
"""

from __future__ import annotations

from typing import Any

from common_core.events.batch_coordination_events import BatchValidationErrorsV1
from common_core.events.envelope import EventEnvelope
from huleedu_service_libs.logging_utils import create_service_logger

from services.batch_orchestrator_service.protocols import (
    BatchEventPublisherProtocol,
    BatchRepositoryProtocol,
)

logger = create_service_logger("bos.handlers.batch_validation_errors")


class BatchValidationErrorsHandler:
    """Handler for BatchValidationErrorsV1 events from ELS.

    This handler processes validation errors separately from success events,
    following the new structured error handling architecture.
    """

    def __init__(
        self,
        event_publisher: BatchEventPublisherProtocol,
        batch_repo: BatchRepositoryProtocol,
    ) -> None:
        self.event_publisher = event_publisher
        self.batch_repo = batch_repo
        self.logger = logger

    async def handle_batch_validation_errors(self, msg: Any) -> None:
        """
        Handle a BatchValidationErrorsV1 event by processing structured validation errors.

        DUAL-EVENT ARCHITECTURE:
        ========================
        This handler is part of the new dual-event pattern that separates
        error handling from success flows. It processes structured validation
        errors with proper categorization and observability.

        1. Deserialize BatchValidationErrorsV1 event with structured error details
        2. Process error categories for metrics and alerting
        3. Update batch status based on critical failure flag
        4. Log detailed error information for debugging
        """
        from huleedu_service_libs.observability import (
            get_tracer,
            trace_operation,
            use_trace_context,
        )

        try:
            # Deserialize the message
            raw_message = msg.value.decode("utf-8")
            envelope = EventEnvelope[BatchValidationErrorsV1].model_validate_json(raw_message)

            batch_validation_errors_data = BatchValidationErrorsV1.model_validate(envelope.data)
            batch_id = batch_validation_errors_data.batch_id

            # Define async function to process within trace context
            async def process_batch_validation_errors() -> None:
                tracer = get_tracer("batch_orchestrator_service")
                with trace_operation(
                    tracer,
                    "kafka.consume.batch_validation_errors",
                    {
                        "messaging.system": "kafka",
                        "messaging.destination": msg.topic,
                        "messaging.operation": "consume",
                        "batch_id": batch_id,
                        "correlation_id": str(envelope.correlation_id),
                    },
                ):
                    self.logger.info(
                        f"Received BatchValidationErrors for batch {batch_id}",
                        extra={
                            "correlation_id": str(envelope.correlation_id),
                            "error_count": len(batch_validation_errors_data.failed_essays),
                        },
                    )

                    # Process error summary for observability
                    error_summary = batch_validation_errors_data.error_summary
                    critical_failure = error_summary.critical_failure
                    error_categories = error_summary.error_categories

                    self.logger.warning(
                        f"Batch {batch_id} validation errors summary",
                        extra={
                            "batch_id": batch_id,
                            "total_errors": error_summary.total_errors,
                            "error_categories": error_categories,
                            "critical_failure": critical_failure,
                            "correlation_id": str(envelope.correlation_id),
                        },
                    )

                    # Log individual validation errors for debugging
                    for failed_essay in batch_validation_errors_data.failed_essays:
                        error_detail = failed_essay.error_detail
                        self.logger.error(
                            f"Essay validation failed for batch {batch_id}",
                            extra={
                                "batch_id": batch_id,
                                "essay_id": failed_essay.essay_id,
                                "file_name": failed_essay.file_name,
                                "error_code": error_detail.error_code,
                                "error_message": error_detail.message,
                                "error_service": error_detail.service,
                                "error_operation": error_detail.operation,
                                "correlation_id": str(envelope.correlation_id),
                            },
                        )

                    # Update batch status based on critical failure
                    if critical_failure:
                        self.logger.critical(
                            f"Batch {batch_id} encountered critical failure - no essays succeeded",
                            extra={
                                "batch_id": batch_id,
                                "correlation_id": str(envelope.correlation_id),
                            },
                        )
                        # Update batch status to FAILED_CRITICALLY
                        from common_core.status_enums import BatchStatus

                        await self.batch_repo.update_batch_status(
                            batch_id, BatchStatus.FAILED_CRITICALLY
                        )
                    else:
                        self.logger.warning(
                            f"Batch {batch_id} has partial validation failures",
                            extra={
                                "batch_id": batch_id,
                                "failed_count": error_summary.total_errors,
                                "correlation_id": str(envelope.correlation_id),
                            },
                        )
                        # For partial failures, batch can continue processing successful essays
                        # The validation errors are logged for observability and debugging

                    # TODO: Emit metrics for monitoring
                    # - Increment validation_failures_total counter
                    # - Record error categories for alerting
                    # - Track critical failure rate

            # Check if envelope has trace context metadata and process accordingly
            if hasattr(envelope, "metadata") and envelope.metadata:
                with use_trace_context(envelope.metadata):
                    await process_batch_validation_errors()
            else:
                await process_batch_validation_errors()

        except Exception as e:
            self.logger.error(f"Error handling BatchValidationErrors message: {e}", exc_info=True)
            raise
