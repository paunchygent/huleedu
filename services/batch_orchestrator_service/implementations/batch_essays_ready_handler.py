"""
BatchEssaysReady message handler implementation for Batch Orchestrator Service.

Handles BatchEssaysReady events from ELS to initiate pipeline processing.
"""

from __future__ import annotations

import json
from typing import Any

from common_core.events.batch_coordination_events import BatchEssaysReady
from common_core.events.envelope import EventEnvelope
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

        SIMPLIFIED ARCHITECTURE:
        ========================
        This handler no longer automatically initiates pipeline processing.
        Instead, it stores essay data for later use when clients trigger pipelines.

        1. Deserialize BatchEssaysReady event with essay content references
        2. Store essays in batch repository for later pipeline processing
        3. Log that batch is ready and awaiting client trigger
        """
        from huleedu_service_libs.observability import (
            get_tracer,
            trace_operation,
            use_trace_context,
        )

        try:
            # Deserialize the message
            message_data = json.loads(msg.value.decode("utf-8"))
            envelope = EventEnvelope[BatchEssaysReady](**message_data)

            batch_essays_ready_data = envelope.data
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

                    if storage_success:
                        self.logger.info(
                            f"Successfully stored {len(essays_data)} essays for batch {batch_id}",
                        )
                    else:
                        self.logger.error(f"Failed to store essays for batch {batch_id}")

                    self.logger.debug(
                        f"Essay storage completed for batch {batch_id}, success: {storage_success}",
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
