"""
Batch coordination handler implementation for Essay Lifecycle Service.

Handles batch coordination events like batch registration and content provisioning.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from common_core.events.batch_coordination_events import BatchEssaysRegistered
    from common_core.events.file_events import EssayContentProvisionedV1, EssayValidationFailedV1

from huleedu_service_libs.logging_utils import create_service_logger

from services.essay_lifecycle_service.protocols import (
    BatchCoordinationHandler,
    BatchEssayTracker,
    EssayRepositoryProtocol,
    EventPublisher,
)

logger = create_service_logger("batch_coordination_handler")


class DefaultBatchCoordinationHandler(BatchCoordinationHandler):
    """Default implementation of BatchCoordinationHandler protocol."""

    def __init__(
        self,
        batch_tracker: BatchEssayTracker,
        repository: EssayRepositoryProtocol,
        event_publisher: EventPublisher,
    ) -> None:
        self.batch_tracker = batch_tracker
        self.repository = repository
        self.event_publisher = event_publisher

    async def handle_batch_essays_registered(
        self,
        event_data: BatchEssaysRegistered,
        correlation_id: UUID,
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

            # Register batch with tracker, preserving correlation ID
            await self.batch_tracker.register_batch(event_data, correlation_id)

            # Create initial essay records in the database
            from common_core.metadata_models import EntityReference

            logger.info(
                "Creating initial essay records in database for batch",
                extra={
                    "batch_id": event_data.batch_id,
                    "essay_count": len(event_data.essay_ids),
                    "correlation_id": str(correlation_id),
                },
            )
            for essay_id in event_data.essay_ids:
                essay_ref = EntityReference(
                    entity_id=essay_id, entity_type="essay", parent_id=event_data.batch_id
                )
                await self.repository.create_essay_record(essay_ref)

            logger.info(
                "Successfully created initial essay records for batch",
                extra={
                    "batch_id": event_data.batch_id,
                    "correlation_id": str(correlation_id),
                },
            )

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
        correlation_id: UUID,
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
            existing_essay = await self.repository.get_essay_by_text_storage_id_and_batch_id(
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

            # Persist slot assignment to database if successful
            if assigned_essay_id is not None:
                await self.batch_tracker.persist_slot_assignment(
                    event_data.batch_id,
                    assigned_essay_id,
                    event_data.text_storage_id,
                    event_data.original_file_name,
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
            from common_core.status_enums import EssayStatus

            await self.repository.create_or_update_essay_state_for_slot_assignment(
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
            batch_completion_result = self.batch_tracker.mark_slot_fulfilled(
                event_data.batch_id, assigned_essay_id, event_data.text_storage_id
            )

            # **Step 5: Publish BatchEssaysReady if complete**
            if batch_completion_result is not None:
                batch_ready_event, original_correlation_id = batch_completion_result
                # Use original correlation ID from batch registration, fallback to current if none
                publish_correlation_id = original_correlation_id or correlation_id

                logger.info(
                    "Batch is complete, publishing BatchEssaysReady event",
                    extra={
                        "batch_id": batch_ready_event.batch_id,
                        "ready_count": len(batch_ready_event.ready_essays),
                        "original_correlation_id": original_correlation_id,
                        "using_correlation_id": str(publish_correlation_id),
                    },
                )

                await self.event_publisher.publish_batch_essays_ready(
                    event_data=batch_ready_event,
                    correlation_id=publish_correlation_id,
                )

                # Clean up completed batch from database
                await self.batch_tracker.remove_batch_from_database(batch_ready_event.batch_id)

            return True

        except Exception as e:
            logger.error(
                "Error handling EssayContentProvisionedV1 event",
                extra={"error": str(e), "correlation_id": str(correlation_id)},
            )
            return False

    async def handle_essay_validation_failed(
        self,
        event_data: EssayValidationFailedV1,
        correlation_id: UUID,
    ) -> bool:
        """Handle EssayValidationFailedV1 event for validation coordination."""
        try:
            logger.info(
                "Processing EssayValidationFailedV1 event",
                extra={
                    "batch_id": event_data.batch_id,
                    "original_file_name": event_data.original_file_name,
                    "error_code": event_data.validation_error_code,
                    "correlation_id": str(correlation_id),
                },
            )

            # Handle validation failure in batch tracker
            validation_result = await self.batch_tracker.handle_validation_failure(event_data)

            # Publish BatchEssaysReady if batch is now complete
            if validation_result is not None:
                batch_ready_event, original_correlation_id = validation_result
                # Use original correlation ID from batch registration, fallback to current if none
                publish_correlation_id = original_correlation_id or correlation_id

                logger.info(
                    "Batch is complete after validation failure, publishing BatchEssaysReady event",
                    extra={
                        "batch_id": batch_ready_event.batch_id,
                        "ready_count": len(batch_ready_event.ready_essays),
                        "validation_failures": len(batch_ready_event.validation_failures or []),
                        "original_correlation_id": original_correlation_id,
                        "using_correlation_id": str(publish_correlation_id),
                    },
                )
                await self.event_publisher.publish_batch_essays_ready(
                    batch_ready_event, correlation_id=publish_correlation_id
                )

            logger.info(
                "Successfully processed validation failure",
                extra={
                    "batch_id": event_data.batch_id,
                    "original_file_name": event_data.original_file_name,
                    "correlation_id": str(correlation_id),
                },
            )

            return True

        except Exception as e:
            logger.error(
                "Error handling EssayValidationFailedV1 event",
                extra={"error": str(e), "correlation_id": str(correlation_id)},
            )
            return False
