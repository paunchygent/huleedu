"""
Batch coordination handler implementation for Essay Lifecycle Service.

Handles batch coordination events like batch registration and content provisioning.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

if TYPE_CHECKING:
    from common_core.events.batch_coordination_events import BatchEssaysRegistered
    from common_core.events.file_events import EssayContentProvisionedV1, EssayValidationFailedV1


from huleedu_service_libs.error_handling import (
    HuleEduError,
    raise_processing_error,
)
from huleedu_service_libs.logging_utils import create_service_logger
from sqlalchemy.ext.asyncio import async_sessionmaker

from services.essay_lifecycle_service.implementations.batch_lifecycle_publisher import (
    BatchLifecyclePublisher,
)
from services.essay_lifecycle_service.implementations.db_pending_content_ops import (
    DBPendingContentOperations,
)
from services.essay_lifecycle_service.config import settings
from services.essay_lifecycle_service.implementations.assignment_sql import (
    assign_via_essay_states_immediate_commit,
)
from services.essay_lifecycle_service.protocols import (
    BatchCoordinationHandler,
    BatchEssayTracker,
    ContentAssignmentProtocol,
    EssayRepositoryProtocol,
)

logger = create_service_logger("batch_coordination_handler")


class DefaultBatchCoordinationHandler(BatchCoordinationHandler):
    """Default implementation of BatchCoordinationHandler protocol."""

    def __init__(
        self,
        batch_tracker: BatchEssayTracker,
        repository: EssayRepositoryProtocol,
        batch_lifecycle_publisher: BatchLifecyclePublisher,
        pending_content_ops: DBPendingContentOperations,
        content_assignment_service: ContentAssignmentProtocol,
        session_factory: async_sessionmaker,
    ) -> None:
        self.batch_tracker = batch_tracker
        self.repository = repository
        self.batch_lifecycle_publisher = batch_lifecycle_publisher
        self.pending_content_ops = pending_content_ops
        self.content_assignment_service = content_assignment_service
        self.session_factory = session_factory

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
                    "batch_id": event_data.entity_id,
                    "expected_count": event_data.expected_essay_count,
                    "correlation_id": str(correlation_id),
                },
            )

            # START UNIT OF WORK
            async with self.session_factory() as session:
                async with session.begin():  # Auto commit/rollback
                    # Register batch with tracker, preserving correlation ID
                    await self.batch_tracker.register_batch(event_data, correlation_id)

                    # Create initial essay records in the database (atomic batch operation)
                    # EntityReference removed - using primitive parameters

                    logger.info(
                        "Creating initial essay records in database for batch",
                        extra={
                            "batch_id": event_data.entity_id,
                            "essay_count": len(event_data.essay_ids),
                            "correlation_id": str(correlation_id),
                        },
                    )

                    # Create all essay data dictionaries for atomic batch operation
                    # Note: Protocol expects str | None values, but in this context
                    # all values are guaranteed non-None
                    typed_essay_data: list[dict[str, str | None]] = [
                        {
                            "entity_id": essay_id,
                            "parent_id": event_data.entity_id,
                            "entity_type": "essay",
                        }
                        for essay_id in event_data.essay_ids
                    ]

                    # Create all essay records in single atomic transaction
                    await self.repository.create_essay_records_batch(
                        typed_essay_data, correlation_id=correlation_id, session=session
                    )

                    logger.info(
                        "Successfully created initial essay records for batch",
                        extra={
                            "batch_id": event_data.entity_id,
                            "correlation_id": str(correlation_id),
                        },
                    )

                    # Process pending content using proper domain service coordination
                    pending_content_list = await self.pending_content_ops.get_pending_content(
                        event_data.entity_id
                    )

                    if pending_content_list:
                        assigned_count = 0
                        for content_metadata in pending_content_list:
                            text_storage_id = content_metadata["text_storage_id"]

                            # Use injected domain service for proper atomic content assignment
                            (
                                was_created,
                                _,
                            ) = await self.content_assignment_service.assign_content_to_essay(
                                batch_id=event_data.entity_id,
                                text_storage_id=text_storage_id,
                                content_metadata=content_metadata,
                                correlation_id=correlation_id,
                                session=session,
                            )

                            if was_created:
                                assigned_count += 1
                                # Remove from pending since successfully assigned
                                await self.pending_content_ops.remove_pending_content(
                                    event_data.entity_id, text_storage_id
                                )

                        if assigned_count > 0:
                            logger.info(
                                f"Processed {assigned_count} pending content items for batch "
                                f"using ContentAssignmentService",
                                extra={
                                    "batch_id": event_data.entity_id,
                                    "assigned_count": assigned_count,
                                    "correlation_id": str(correlation_id),
                                },
                            )

                    # Check if batch is immediately complete due to pending failures
                    batch_completion_result = await self.batch_tracker.check_batch_completion(
                        event_data.entity_id
                    )
                    if batch_completion_result is not None:
                        batch_ready_event, original_correlation_id = batch_completion_result
                        # Use original correlation ID from batch registration
                        publish_correlation_id = original_correlation_id or correlation_id

                        logger.info(
                            "Batch is immediately complete, publishing "
                            "BatchContentProvisioningCompletedV1 event",
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

                        content_completed_event = BatchContentProvisioningCompletedV1(
                            batch_id=batch_ready_event.batch_id,
                            provisioned_count=len(batch_ready_event.ready_essays),
                            expected_count=event_data.expected_essay_count,
                            course_code=batch_ready_event.course_code,
                            user_id=event_data.user_id,
                            essays_for_processing=batch_ready_event.ready_essays,
                            correlation_id=publish_correlation_id,
                        )

                        await self.batch_lifecycle_publisher.publish_batch_content_provisioning_completed(
                            event_data=content_completed_event,
                            correlation_id=publish_correlation_id,
                            session=session,
                        )

                        # No immediate DB cleanup; batch remains for audit. A retention job can purge later.
                    # Transaction commits here automatically

            return True

        except HuleEduError:
            # Re-raise HuleEdu errors to preserve error type (EXTERNAL_SERVICE_ERROR, etc.)
            raise
        except Exception as e:
            # Only wrap unexpected exceptions as PROCESSING_ERROR
            raise_processing_error(
                service="essay_lifecycle_service",
                operation="handle_batch_essays_registered",
                message=f"Unexpected error in batch essays registration: {e.__class__.__name__}",
                correlation_id=correlation_id,
                batch_id=event_data.entity_id,
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
                    "batch_id": event_data.entity_id,
                    "text_storage_id": event_data.text_storage_id,
                    "original_file_name": event_data.original_file_name,
                    "correlation_id": str(correlation_id),
                },
            )

            # Step 1: If batch not registered yet, store as pending. Otherwise, proceed.
            batch_status = await self.batch_tracker.get_batch_status(event_data.entity_id)

            if batch_status is None:
                logger.info(
                    "Batch not registered yet, storing content as pending",
                    extra={
                        "batch_id": event_data.entity_id,
                        "text_storage_id": event_data.text_storage_id,
                        "correlation_id": str(correlation_id),
                    },
                )

                content_metadata = {
                    "original_file_name": event_data.original_file_name,
                    "file_upload_id": event_data.file_upload_id,
                    "raw_file_storage_id": event_data.raw_file_storage_id,
                    "file_size_bytes": event_data.file_size_bytes,
                    "content_md5_hash": event_data.content_md5_hash,
                    "correlation_id": str(event_data.correlation_id),
                }

                await self.pending_content_ops.store_pending_content(
                    event_data.entity_id, event_data.text_storage_id, content_metadata
                )
                return True

            # Step 2: Content assignment and side effects
            content_metadata = {
                "original_file_name": event_data.original_file_name,
                "file_size_bytes": event_data.file_size_bytes,
                "file_upload_id": event_data.file_upload_id,
                "content_md5_hash": event_data.content_md5_hash,
            }

            if settings.ELS_USE_ESSAY_STATES_AS_INVENTORY:
                # Perform assignment first (immediate-commit) to avoid overlapping DB connections
                was_created, final_essay_id = await assign_via_essay_states_immediate_commit(
                    session_factory=self.session_factory,
                    batch_id=event_data.entity_id,
                    text_storage_id=event_data.text_storage_id,
                    original_file_name=event_data.original_file_name,
                    file_size=event_data.file_size_bytes,
                    content_hash=event_data.content_md5_hash,
                    correlation_id=correlation_id,
                )

                if final_essay_id is None:
                    # No slot: publish excess content event
                    logger.warning(
                        "No available slots for content, publishing excess content event",
                        extra={
                            "batch_id": event_data.entity_id,
                            "text_storage_id": event_data.text_storage_id,
                            "original_file_name": event_data.original_file_name,
                            "correlation_id": str(correlation_id),
                        },
                    )
                    async with self.session_factory() as session:
                        async with session.begin():
                            from datetime import UTC, datetime
                            from common_core.events.batch_coordination_events import (
                                ExcessContentProvisionedV1,
                            )

                            excess_event = ExcessContentProvisionedV1(
                                batch_id=event_data.entity_id,
                                original_file_name=event_data.original_file_name,
                                text_storage_id=event_data.text_storage_id,
                                reason="NO_AVAILABLE_SLOT",
                                correlation_id=correlation_id,
                                timestamp=datetime.now(UTC),
                            )

                            await self.batch_lifecycle_publisher.publish_excess_content_provisioned(
                                event_data=excess_event,
                                correlation_id=correlation_id,
                                session=session,
                            )
                    return False

                # Post-assignment side effects in separate transaction
                async with self.session_factory() as session:
                    async with session.begin():
                        was_created2, final2 = await self.content_assignment_service.assign_content_to_essay(
                            batch_id=event_data.entity_id,
                            text_storage_id=event_data.text_storage_id,
                            content_metadata=content_metadata,
                            correlation_id=correlation_id,
                            session=session,
                            preassigned_essay_id=final_essay_id,
                            preassigned_was_created=was_created,
                        )
                        logger.info(
                            "Content assignment post-effects completed",
                            extra={
                                "batch_id": event_data.entity_id,
                                "text_storage_id": event_data.text_storage_id,
                                "final_essay_id": final2,
                                "was_created": was_created2,
                                "correlation_id": str(correlation_id),
                            },
                        )
                return True
            else:
                # Legacy path within one transaction
                async with self.session_factory() as session:
                    async with session.begin():
                        was_created, final_essay_id = await self.content_assignment_service.assign_content_to_essay(
                            batch_id=event_data.entity_id,
                            text_storage_id=event_data.text_storage_id,
                            content_metadata=content_metadata,
                            correlation_id=correlation_id,
                            session=session,
                        )
                        logger.info(
                            "Content assignment completed via ContentAssignmentService",
                            extra={
                                "batch_id": event_data.entity_id,
                                "text_storage_id": event_data.text_storage_id,
                                "final_essay_id": final_essay_id,
                                "was_created": was_created,
                                "correlation_id": str(correlation_id),
                            },
                        )
                return True

        except HuleEduError:
            # Re-raise HuleEdu errors to preserve error type (EXTERNAL_SERVICE_ERROR, etc.)
            raise
        except Exception as e:
            # Only wrap unexpected exceptions as PROCESSING_ERROR
            import traceback

            stack_trace = traceback.format_exc()
            logger.error(
                f"Unexpected error in handle_essay_content_provisioned: {e.__class__.__name__}: {e}",
                extra={
                    "stack_trace": stack_trace,
                    "batch_id": event_data.entity_id,
                    "text_storage_id": event_data.text_storage_id,
                },
            )
            raise_processing_error(
                service="essay_lifecycle_service",
                operation="handle_essay_content_provisioned",
                message=f"Unexpected error in essay content provisioning: {e.__class__.__name__}",
                correlation_id=correlation_id,
                batch_id=event_data.entity_id,
                text_storage_id=event_data.text_storage_id,
                original_file_name=event_data.original_file_name,
                error_type=e.__class__.__name__,
                error_details=str(e),
                stack_trace=stack_trace,
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
                    "batch_id": event_data.entity_id,
                    "original_file_name": event_data.original_file_name,
                    "error_code": event_data.validation_error_code,
                    "correlation_id": str(correlation_id),
                },
            )

            # Handle validation failure in batch tracker
            validation_result = await self.batch_tracker.handle_validation_failure(event_data)

            # Publish BatchContentProvisioningCompletedV1 if batch is now complete
            if validation_result is not None:
                batch_ready_event, original_correlation_id = validation_result
                # Use original correlation ID from batch registration, fallback to current if none
                publish_correlation_id = original_correlation_id or correlation_id

                logger.info(
                    "Batch is complete after validation failure, publishing BatchContentProvisioningCompletedV1 event",
                    extra={
                        "batch_id": batch_ready_event.batch_id,
                        "ready_count": len(batch_ready_event.ready_essays),
                        "original_correlation_id": original_correlation_id,
                        "using_correlation_id": str(publish_correlation_id),
                    },
                )

                # START UNIT OF WORK for event publishing
                async with self.session_factory() as session:
                    async with session.begin():
                        # Create BatchContentProvisioningCompletedV1 event
                        from common_core.events.batch_coordination_events import (
                            BatchContentProvisioningCompletedV1,
                        )

                        # Get user_id from batch tracker for this batch
                        batch_status = await self.batch_tracker.get_batch_status(
                            batch_ready_event.batch_id
                        )
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

                        # Mark batch completed for GUEST batches after event publication
                        # REGULAR batches are marked complete in student_association_handler
                        if batch_ready_event.class_type == "GUEST":
                            await self.batch_tracker.mark_batch_completed(batch_ready_event.batch_id, session)
                            logger.info(
                                f"GUEST batch {batch_ready_event.batch_id} marked as completed after validation failure BatchContentProvisioningCompleted publication"
                            )
                        # Transaction commits here

            logger.info(
                "Successfully processed validation failure",
                extra={
                    "batch_id": event_data.entity_id,
                    "original_file_name": event_data.original_file_name,
                    "correlation_id": str(correlation_id),
                },
            )

            return True

        except HuleEduError:
            # Re-raise HuleEdu errors to preserve error type (EXTERNAL_SERVICE_ERROR, etc.)
            raise
        except Exception as e:
            # Only wrap unexpected exceptions as PROCESSING_ERROR
            raise_processing_error(
                service="essay_lifecycle_service",
                operation="handle_essay_validation_failed",
                message=f"Unexpected error in essay validation failure handling: {e.__class__.__name__}",
                correlation_id=correlation_id,
                batch_id=event_data.entity_id,
                original_file_name=event_data.original_file_name,
                validation_error_code=event_data.validation_error_code,
                error_type=e.__class__.__name__,
                error_details=str(e),
            )

    async def handle_student_associations_confirmed(
        self,
        event_data: Any,  # StudentAssociationsConfirmedV1
        correlation_id: UUID,
    ) -> bool:
        """Handle Phase 1 student associations confirmed from Class Management.

        This method satisfies the BatchCoordinationHandler protocol requirement
        while delegating the actual work through event publishing to avoid
        circular dependencies.
        """
        try:
            logger.info(
                "BatchCoordinationHandler received student associations confirmed event",
                extra={
                    "batch_id": event_data.batch_id,
                    "class_id": event_data.class_id,
                    "associations_count": len(event_data.associations),
                    "correlation_id": str(correlation_id),
                },
            )

            # Instead of directly calling StudentAssociationHandler (which would create
            # a circular dependency), we publish an internal command event for
            # proper decoupling. The ELS worker will handle this through proper routing.

            # For now, since the StudentAssociationHandler doesn't create circular
            # dependencies anymore (it only depends on repository, batch_tracker, and
            # batch_lifecycle_publisher), we can actually use it directly.

            # Import here to avoid circular import at module level
            from services.essay_lifecycle_service.implementations.student_association_handler import (
                StudentAssociationHandler,
            )

            # Create handler instance with our dependencies
            # The session_factory is the correct type, no casting needed

            student_handler = StudentAssociationHandler(
                self.repository,
                self.batch_tracker,
                self.batch_lifecycle_publisher,
                self.session_factory,
            )

            # Delegate to the specialized handler
            await student_handler.handle_student_associations_confirmed(event_data, correlation_id)

            return True

        except HuleEduError:
            # Re-raise HuleEdu errors to preserve error type
            raise
        except Exception as e:
            # Only wrap unexpected exceptions as PROCESSING_ERROR
            raise_processing_error(
                service="essay_lifecycle_service",
                operation="handle_student_associations_confirmed",
                message=f"Unexpected error in student associations handling: {e.__class__.__name__}",
                correlation_id=correlation_id,
                batch_id=event_data.batch_id,
                class_id=event_data.class_id,
                error_type=e.__class__.__name__,
                error_details=str(e),
            )
