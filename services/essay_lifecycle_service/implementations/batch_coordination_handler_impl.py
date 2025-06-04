"""
Batch coordination handler implementation for Essay Lifecycle Service.

Handles batch coordination events like batch registration and content provisioning.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from common_core.events.batch_coordination_events import (
        BatchEssaysRegistered,
        EssayContentProvisionedV1,
    )

from huleedu_service_libs.logging_utils import create_service_logger

from protocols import (
    BatchCoordinationHandler,
    BatchEssayTracker,
    EssayStateStore,
    EventPublisher,
)

logger = create_service_logger("batch_coordination_handler")


class DefaultBatchCoordinationHandler(BatchCoordinationHandler):
    """Default implementation of BatchCoordinationHandler protocol."""

    def __init__(
        self,
        batch_tracker: BatchEssayTracker,
        state_store: EssayStateStore,
        event_publisher: EventPublisher,
    ) -> None:
        self.batch_tracker = batch_tracker
        self.state_store = state_store
        self.event_publisher = event_publisher

    async def handle_batch_essays_registered(
        self,
        event_data: BatchEssaysRegistered,
        correlation_id: UUID | None = None,
    ) -> bool:
        """Handle BatchEssaysRegistered event."""
        try:
            logger.info(
                "Processing BatchEssaysRegistered event",
                extra={
                    "batch_id": event_data.batch_id,
                    "expected_count": event_data.expected_essay_count,
                    "correlation_id": str(correlation_id),
                },
            )

            # Register batch with tracker
            await self.batch_tracker.register_batch(event_data)

            return True

        except Exception as e:
            logger.error(
                "Error handling BatchEssaysRegistered event",
                extra={"error": str(e), "correlation_id": str(correlation_id)},
            )
            return False

    async def handle_essay_content_provisioned(
        self,
        event_data: EssayContentProvisionedV1,
        correlation_id: UUID | None = None,
    ) -> bool:
        """Handle EssayContentProvisionedV1 event for slot assignment."""
        try:
            logger.info(
                "Processing EssayContentProvisionedV1 event",
                extra={
                    "batch_id": event_data.batch_id,
                    "text_storage_id": event_data.text_storage_id,
                    "original_file_name": event_data.original_file_name,
                    "correlation_id": str(correlation_id),
                },
            )

            # **Step 1: Idempotency Check**
            existing_essay = await self.state_store.get_essay_by_text_storage_id_and_batch_id(
                event_data.batch_id, event_data.text_storage_id
            )

            if existing_essay is not None:
                logger.warning(
                    "Content already assigned to slot, acknowledging idempotently",
                    extra={
                        "batch_id": event_data.batch_id,
                        "text_storage_id": event_data.text_storage_id,
                        "assigned_essay_id": existing_essay.essay_id,
                        "correlation_id": str(correlation_id),
                    },
                )
                return True

            # **Step 2: Slot Assignment**
            assigned_essay_id = self.batch_tracker.assign_slot_to_content(
                event_data.batch_id, event_data.text_storage_id, event_data.original_file_name
            )

            if assigned_essay_id is None:
                # No slots available - publish ExcessContentProvisionedV1 event
                logger.warning(
                    "No available slots for content, publishing excess content event",
                    extra={
                        "batch_id": event_data.batch_id,
                        "text_storage_id": event_data.text_storage_id,
                        "original_file_name": event_data.original_file_name,
                        "correlation_id": str(correlation_id),
                    },
                )

                from datetime import UTC, datetime

                from common_core.events.batch_coordination_events import ExcessContentProvisionedV1

                excess_event = ExcessContentProvisionedV1(
                    batch_id=event_data.batch_id,
                    original_file_name=event_data.original_file_name,
                    text_storage_id=event_data.text_storage_id,
                    reason="NO_AVAILABLE_SLOT",
                    correlation_id=correlation_id,
                    timestamp=datetime.now(UTC),
                )

                await self.event_publisher.publish_excess_content_provisioned(
                    event_data=excess_event,
                    correlation_id=correlation_id,
                )

                return True

            # **Step 3: Persist Slot Assignment**
            from common_core.enums import EssayStatus

            await self.state_store.create_or_update_essay_state_for_slot_assignment(
                internal_essay_id=assigned_essay_id,
                batch_id=event_data.batch_id,
                text_storage_id=event_data.text_storage_id,
                original_file_name=event_data.original_file_name,
                file_size=event_data.file_size_bytes,
                content_hash=event_data.content_md5_hash,
                initial_status=EssayStatus.READY_FOR_PROCESSING,
            )

            logger.info(
                "Successfully assigned content to slot",
                extra={
                    "assigned_essay_id": assigned_essay_id,
                    "batch_id": event_data.batch_id,
                    "text_storage_id": event_data.text_storage_id,
                    "correlation_id": str(correlation_id),
                },
            )

            # **Step 4: Check Batch Completion**
            batch_ready_event = self.batch_tracker.mark_slot_fulfilled(
                event_data.batch_id, assigned_essay_id, event_data.text_storage_id
            )

            # **Step 5: Publish BatchEssaysReady if complete**
            if batch_ready_event is not None:
                logger.info(
                    "Batch is complete, publishing BatchEssaysReady event",
                    extra={
                        "batch_id": batch_ready_event.batch_id,
                        "ready_count": len(batch_ready_event.ready_essays),
                        "correlation_id": str(correlation_id),
                    },
                )

                await self.event_publisher.publish_batch_essays_ready(
                    event_data=batch_ready_event,
                    correlation_id=correlation_id,
                )

            return True

        except Exception as e:
            logger.error(
                "Error handling EssayContentProvisionedV1 event",
                extra={"error": str(e), "correlation_id": str(correlation_id)},
            )
            return False
