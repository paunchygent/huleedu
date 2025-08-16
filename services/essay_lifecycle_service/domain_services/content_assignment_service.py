"""
Content Assignment Domain Service for Essay Lifecycle Service.

Handles atomic content-to-essay assignment operations that are shared between
normal content provisioning flow and pending content recovery flow.

This service ensures consistent state management across both flows following
DDD principles and maintaining single source of truth for assignment logic.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from common_core.status_enums import EssayStatus
from huleedu_service_libs.logging_utils import create_service_logger

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from services.essay_lifecycle_service.implementations.batch_lifecycle_publisher import (
        BatchLifecyclePublisher,
    )
    from services.essay_lifecycle_service.protocols import (
        BatchEssayTracker,
        EssayRepositoryProtocol,
    )

# Import protocol outside TYPE_CHECKING for runtime inheritance
from services.essay_lifecycle_service.protocols import ContentAssignmentProtocol

logger = create_service_logger("content_assignment_service")


class ContentAssignmentService(ContentAssignmentProtocol):
    """
    Domain service for handling content-to-essay assignment operations.

    Encapsulates the business logic for atomic content assignment that includes:
    - Redis slot assignment
    - Database essay state creation
    - Event publication
    - Batch completion coordination
    """

    def __init__(
        self,
        batch_tracker: BatchEssayTracker,
        repository: EssayRepositoryProtocol,
        batch_lifecycle_publisher: BatchLifecyclePublisher,
    ) -> None:
        self.batch_tracker = batch_tracker
        self.repository = repository
        self.batch_lifecycle_publisher = batch_lifecycle_publisher

    async def assign_content_to_essay(
        self,
        batch_id: str,
        text_storage_id: str,
        content_metadata: dict[str, Any],
        correlation_id: UUID,
        session: AsyncSession,
    ) -> tuple[bool, str | None]:
        """
        Perform atomic content-to-essay assignment with full state coordination.

        This method encapsulates the complete assignment flow used by both:
        1. Normal content provisioning (EssayContentProvisionedV1 events)
        2. Pending content recovery (during batch registration)

        Args:
            batch_id: The batch ID
            text_storage_id: Storage ID for the essay content
            content_metadata: Content metadata (file_name, size, hash, etc.)
            correlation_id: Operation correlation ID
            session: Database session for atomic operations

        Returns:
            Tuple of (was_created, final_essay_id)
            - was_created: True if new assignment, False if idempotent
            - final_essay_id: The essay ID that got the content
        """
        # Step 1: Try Redis slot assignment first
        assigned_essay_id = await self.batch_tracker.assign_slot_to_content(
            batch_id, text_storage_id, content_metadata.get("original_file_name", "unknown")
        )

        if assigned_essay_id is None:
            # No available slots - content should be handled as excess
            return False, None

        # Step 2: Create/update database record atomically
        essay_data = {
            "internal_essay_id": assigned_essay_id,
            "initial_status": EssayStatus.READY_FOR_PROCESSING,
            "original_file_name": content_metadata.get("original_file_name", "unknown"),
            "file_size": content_metadata.get("file_size_bytes", 0),
            "file_upload_id": content_metadata.get("file_upload_id"),
            "content_hash": content_metadata.get("content_md5_hash"),
        }

        (
            was_created,
            final_essay_id,
        ) = await self.repository.create_essay_state_with_content_idempotency(
            batch_id=batch_id,
            text_storage_id=text_storage_id,
            essay_data=essay_data,
            correlation_id=correlation_id,
            session=session,
        )

        # Step 3: Persist slot assignment if new
        if was_created:
            await self.batch_tracker.persist_slot_assignment(
                batch_id,
                assigned_essay_id,
                text_storage_id,
                content_metadata.get("original_file_name", "unknown"),
                session=session,
            )

        # Step 4: Publish slot assignment event for traceability
        from common_core.events.essay_lifecycle_events import EssaySlotAssignedV1

        slot_assigned_event = EssaySlotAssignedV1(
            batch_id=batch_id,
            essay_id=final_essay_id or assigned_essay_id,
            file_upload_id=content_metadata.get("file_upload_id", "unknown"),
            text_storage_id=text_storage_id,
            correlation_id=correlation_id,
        )

        await self.batch_lifecycle_publisher.publish_essay_slot_assigned(
            event_data=slot_assigned_event,
            correlation_id=correlation_id,
            session=session,
        )

        # Step 5: Mark slot as fulfilled and check batch completion
        batch_completion_result = await self.batch_tracker.mark_slot_fulfilled(
            batch_id, final_essay_id or assigned_essay_id, text_storage_id
        )

        if batch_completion_result is not None:
            batch_ready_event, original_correlation_id = batch_completion_result
            # Use original correlation ID from batch registration, fallback to current if none
            publish_correlation_id = original_correlation_id or correlation_id

            logger.info(
                "Batch completed during content assignment, publishing BatchContentProvisioningCompletedV1",
                extra={
                    "batch_id": batch_ready_event.batch_id,
                    "ready_count": len(batch_ready_event.ready_essays),
                    "correlation_id": str(publish_correlation_id),
                },
            )

            # Create BatchContentProvisioningCompletedV1 event
            from common_core.events.batch_coordination_events import (
                BatchContentProvisioningCompletedV1,
            )

            # Get user_id from batch tracker for this batch
            batch_status = await self.batch_tracker.get_batch_status(batch_ready_event.batch_id)
            user_id = batch_status.get("user_id") if batch_status else "unknown"

            content_completed_event = BatchContentProvisioningCompletedV1(
                batch_id=batch_ready_event.batch_id,
                provisioned_count=len(batch_ready_event.ready_essays),
                expected_count=len(batch_ready_event.ready_essays),  # All essays ready
                course_code=batch_ready_event.course_code,
                user_id=user_id,
                essays_for_processing=batch_ready_event.ready_essays,
                correlation_id=publish_correlation_id,
            )

            await self.batch_lifecycle_publisher.publish_batch_content_provisioning_completed(
                event_data=content_completed_event,
                correlation_id=publish_correlation_id,
                session=session,
            )

            # Clean up Redis state for GUEST batches after event publication
            if batch_ready_event.class_type == "GUEST":
                await self.batch_tracker.cleanup_batch(batch_ready_event.batch_id)
                logger.info(
                    f"GUEST batch {batch_ready_event.batch_id} Redis state cleaned up after BatchContentProvisioningCompleted publication"
                )

        logger.info(
            "Content assignment completed successfully",
            extra={
                "batch_id": batch_id,
                "text_storage_id": text_storage_id,
                "final_essay_id": final_essay_id,
                "was_created": was_created,
                "correlation_id": str(correlation_id),
            },
        )

        return was_created, final_essay_id
