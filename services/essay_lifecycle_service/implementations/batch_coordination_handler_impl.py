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

from huleedu_service_libs.error_handling import (
    raise_processing_error,
)
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

            # Create initial essay records in the database (atomic batch operation)
            from common_core.metadata_models import EntityReference

            logger.info(
                "Creating initial essay records in database for batch",
                extra={
                    "batch_id": event_data.batch_id,
                    "essay_count": len(event_data.essay_ids),
                    "correlation_id": str(correlation_id),
                },
            )

            # Create all essay references for atomic batch operation
            essay_refs = [
                EntityReference(
                    entity_id=essay_id, entity_type="essay", parent_id=event_data.batch_id
                )
                for essay_id in event_data.essay_ids
            ]

            # Create all essay records in single atomic transaction
            await self.repository.create_essay_records_batch(
                essay_refs, correlation_id=correlation_id
            )

            logger.info(
                "Successfully created initial essay records for batch",
                extra={
                    "batch_id": event_data.batch_id,
                    "correlation_id": str(correlation_id),
                },
            )

            return True

        except Exception as e:
            # Re-raise HuleEduError as-is, or wrap other exceptions
            if hasattr(e, "error_detail"):
                raise
            else:
                raise_processing_error(
                    service="essay_lifecycle_service",
                    operation="handle_batch_essays_registered",
                    message=f"Failed to process batch essays registration: {e.__class__.__name__}",
                    correlation_id=correlation_id,
                    batch_id=event_data.batch_id,
                    expected_count=event_data.expected_essay_count,
                    essay_count=len(event_data.essay_ids),
                    error_type=e.__class__.__name__,
                    error_details=str(e),
                )

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

            # **ELS-002 Phase 1: Atomic Content Provisioning**
            # Replace non-atomic idempotency check + slot assignment with database-level atomicity

            # Step 1: Try slot assignment first (maintains existing batch tracker logic)
            assigned_essay_id = await self.batch_tracker.assign_slot_to_content(
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

                return False

            # Step 2: Atomic content provisioning with database-level idempotency
            from common_core.status_enums import EssayStatus

            essay_data = {
                "internal_essay_id": assigned_essay_id,
                "initial_status": EssayStatus.READY_FOR_PROCESSING,
                "original_file_name": event_data.original_file_name,
                "file_size": event_data.file_size_bytes,
                "content_hash": event_data.content_md5_hash,
            }

            (
                was_created,
                final_essay_id,
            ) = await self.repository.create_essay_state_with_content_idempotency(
                batch_id=event_data.batch_id,
                text_storage_id=event_data.text_storage_id,
                essay_data=essay_data,
                correlation_id=correlation_id,
            )

            if was_created:
                # New assignment - persist to batch tracker
                await self.batch_tracker.persist_slot_assignment(
                    event_data.batch_id,
                    assigned_essay_id,
                    event_data.text_storage_id,
                    event_data.original_file_name,
                )

                logger.info(
                    "Successfully assigned content to slot with atomic creation",
                    extra={
                        "assigned_essay_id": final_essay_id,
                        "batch_id": event_data.batch_id,
                        "text_storage_id": event_data.text_storage_id,
                        "correlation_id": str(correlation_id),
                    },
                )
            else:
                # Idempotent case - content already assigned
                logger.info(
                    "Content already assigned to slot, acknowledging idempotently",
                    extra={
                        "batch_id": event_data.batch_id,
                        "text_storage_id": event_data.text_storage_id,
                        "assigned_essay_id": final_essay_id,
                        "correlation_id": str(correlation_id),
                    },
                )

            # **Step 3: Check Batch Completion**
            # At this point, final_essay_id should always be valid
            if final_essay_id is None:
                raise ValueError(
                    f"Unexpected None essay_id after content provisioning for batch {event_data.batch_id}"
                )

            batch_completion_result = await self.batch_tracker.mark_slot_fulfilled(
                event_data.batch_id, final_essay_id, event_data.text_storage_id
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

                # NOTE: Batch tracker record must persist for pipeline duration
                # Essays need batch_id for phase outcome coordination throughout spellcheck/CJ phases
                # Cleanup will happen at pipeline completion, not after content provisioning

            return True

        except Exception as e:
            # Re-raise HuleEduError as-is, or wrap other exceptions
            if hasattr(e, "error_detail"):
                raise
            else:
                raise_processing_error(
                    service="essay_lifecycle_service",
                    operation="handle_essay_content_provisioned",
                    message=f"Failed to process essay content provisioning: {e.__class__.__name__}",
                    correlation_id=correlation_id,
                    batch_id=event_data.batch_id,
                    text_storage_id=event_data.text_storage_id,
                    original_file_name=event_data.original_file_name,
                    error_type=e.__class__.__name__,
                    error_details=str(e),
                )

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
            # Re-raise HuleEduError as-is, or wrap other exceptions
            if hasattr(e, "error_detail"):
                raise
            else:
                raise_processing_error(
                    service="essay_lifecycle_service",
                    operation="handle_essay_validation_failed",
                    message=f"Failed to process essay validation failure: {e.__class__.__name__}",
                    correlation_id=correlation_id,
                    batch_id=event_data.batch_id,
                    original_file_name=event_data.original_file_name,
                    validation_error_code=event_data.validation_error_code,
                    error_type=e.__class__.__name__,
                    error_details=str(e),
                )
