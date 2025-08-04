"""
Student association handler for Essay Lifecycle Service.

Handles StudentAssociationsConfirmedV1 events from Class Management Service
to complete Phase 1 student matching for REGULAR batches.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from common_core.events.validation_events import StudentAssociationsConfirmedV1
    from sqlalchemy.ext.asyncio import async_sessionmaker

from common_core.events.batch_coordination_events import BatchEssaysReady
from common_core.metadata_models import SystemProcessingMetadata
from huleedu_service_libs.error_handling import raise_processing_error
from huleedu_service_libs.logging_utils import create_service_logger

from services.essay_lifecycle_service.protocols import (
    BatchEssayTracker,
    BatchLifecyclePublisherProtocol,
    EssayRepositoryProtocol,
)

logger = create_service_logger("student_association_handler")


class StudentAssociationHandler:
    """
    Handles STUDENT_ASSOCIATIONS_CONFIRMED from Class Management Service.

    This handler completes the Phase 1 student matching workflow by:
    1. Updating essay records with confirmed student associations
    2. Publishing BatchEssaysReady for REGULAR batches
    """

    def __init__(
        self,
        repository: EssayRepositoryProtocol,
        batch_tracker: BatchEssayTracker,
        batch_lifecycle_publisher: BatchLifecyclePublisherProtocol,
        session_factory: async_sessionmaker,
    ) -> None:
        self.repository = repository
        self.batch_tracker = batch_tracker
        self.batch_lifecycle_publisher = batch_lifecycle_publisher
        self.session_factory = session_factory

    async def handle_student_associations_confirmed(
        self,
        event_data: StudentAssociationsConfirmedV1,
        correlation_id: UUID,
    ) -> None:
        """
        Process confirmed student associations from Class Management Service.

        This completes Phase 1 for REGULAR batches by:
        1. Updating each essay with its student association
        2. Checking if all essays in batch have associations
        3. Publishing BatchEssaysReady when complete
        """
        batch_id = event_data.batch_id

        logger.info(
            "Processing student associations confirmed event",
            extra={
                "batch_id": batch_id,
                "class_id": event_data.class_id,
                "associations_count": len(event_data.associations),
                "timeout_triggered": event_data.timeout_triggered,
                "validation_summary": event_data.validation_summary,
                "correlation_id": str(correlation_id),
            },
        )

        # START UNIT OF WORK
        async with self.session_factory() as session:
            async with session.begin():
                try:
                    # Process each association
                    updated_essays = []

                    for association in event_data.associations:
                        essay_id = association.essay_id

                        # Get current essay state
                        essay_state = await self.repository.get_essay_state(essay_id)
                        if essay_state is None:
                            logger.error(
                                f"Essay {essay_id} not found for student association update",
                                extra={
                                    "batch_id": batch_id,
                                    "correlation_id": str(correlation_id),
                                },
                            )
                            continue

                        # Update essay with student association
                        await self.repository.update_student_association(
                            essay_id=essay_id,
                            student_id=association.student_id,
                            association_confirmed_at=association.validated_at,
                            association_method=association.validation_method,
                            correlation_id=correlation_id,
                            session=session,
                        )

                        # Update processing metadata
                        metadata_update = {
                            "awaiting_student_association": False,
                            "student_matching_phase": "completed",
                            "student_id": association.student_id,
                            "association_confidence": association.confidence_score,
                            "association_method": association.validation_method,
                            "validated_by": association.validated_by,
                        }

                        await self.repository.update_essay_processing_metadata(
                            essay_id=essay_id,
                            metadata_updates=metadata_update,
                            correlation_id=correlation_id,
                            session=session,
                        )

                        updated_essays.append(essay_state)

                        logger.debug(
                            f"Updated essay {essay_id} with student association",
                            extra={
                                "batch_id": batch_id,
                                "student_id": association.student_id,
                                "method": association.validation_method,
                                "correlation_id": str(correlation_id),
                            },
                        )

                    # Check if all essays in batch have associations
                    batch_status = await self.batch_tracker.get_batch_status(batch_id)
                    if not batch_status:
                        raise_processing_error(
                            service="essay_lifecycle_service",
                            operation="handle_student_associations_confirmed",
                            message=f"Batch status not found for batch {batch_id}",
                            correlation_id=correlation_id,
                            batch_id=batch_id,
                        )

                    # Prepare BatchEssaysReady event
                    # Get ALL ready essays from batch tracker (content provisioning already complete)
                    batch_ready_result = await self.batch_tracker.check_batch_completion(batch_id)
                    if not batch_ready_result:
                        raise_processing_error(
                            service="essay_lifecycle_service",
                            operation="handle_student_associations_confirmed",
                            message=f"Unable to get ready essays for batch {batch_id}",
                            correlation_id=correlation_id,
                            batch_id=batch_id,
                        )
                    
                    batch_ready_event_from_tracker, _ = batch_ready_result
                    ready_essays = batch_ready_event_from_tracker.ready_essays

                    # Create BatchEssaysReady event (only for REGULAR batches after associations)
                    from common_core.domain_enums import CourseCode, get_course_language

                    # Get course code from first essay's metadata
                    # (all essays in batch have same course)
                    first_essay = updated_essays[0] if updated_essays else None
                    course_code = CourseCode.ENG5  # Default, should get from batch context
                    if first_essay and first_essay.processing_metadata:
                        course_code_str = first_essay.processing_metadata.get("course_code", "ENG5")
                        course_code = CourseCode(course_code_str)

                    course_language = get_course_language(course_code).value

                    batch_ready_event = BatchEssaysReady(
                        batch_id=batch_id,
                        ready_essays=ready_essays,
                        metadata=SystemProcessingMetadata(
                            entity_id=batch_id,
                            entity_type="batch",
                            parent_id=None,
                            timestamp=datetime.now(UTC),
                            event="batch.essays.ready",
                        ),
                        course_code=course_code,
                        course_language=course_language,
                        essay_instructions="",  # Would get from batch context
                        class_type="REGULAR",  # Always REGULAR for this flow
                        teacher_first_name=None,  # Would get from class management
                        teacher_last_name=None,  # Would get from class management
                    )

                    # Publish BatchEssaysReady via batch lifecycle publisher
                    await self.batch_lifecycle_publisher.publish_batch_essays_ready(
                        event_data=batch_ready_event,
                        correlation_id=correlation_id,
                        session=session,
                    )

                    logger.info(
                        f"Published BatchEssaysReady for REGULAR batch {batch_id} "
                        "after student associations",
                        extra={
                            "batch_id": batch_id,
                            "ready_essays_count": len(ready_essays),
                            "correlation_id": str(correlation_id),
                        },
                    )

                    # Clean up Redis state for REGULAR batch after BatchEssaysReady publication
                    # This completes the REGULAR batch lifecycle: content → associations → ready → cleanup
                    await self.batch_tracker.cleanup_batch(batch_id)
                    logger.info(f"REGULAR batch {batch_id} Redis state cleaned up after BatchEssaysReady publication")

                    # Update batch tracking to indicate associations complete
                    if ready_essays:
                        await self.repository.update_essay_processing_metadata(
                            essay_id=ready_essays[0].essay_id,
                            metadata_updates={
                                "batch_student_associations_complete": True,
                                "associations_completed_at": datetime.now(UTC).isoformat(),
                            },
                            correlation_id=correlation_id,
                            session=session,
                        )

                    logger.info(
                        f"Successfully processed student associations for batch {batch_id}",
                        extra={
                            "batch_id": batch_id,
                            "updated_essays": len(updated_essays),
                            "correlation_id": str(correlation_id),
                        },
                    )

                except Exception as e:
                    logger.error(
                        f"Failed to process student associations for batch {batch_id}",
                        extra={
                            "error": str(e),
                            "batch_id": batch_id,
                            "correlation_id": str(correlation_id),
                        },
                    )
                    raise_processing_error(
                        service="essay_lifecycle_service",
                        operation="handle_student_associations_confirmed",
                        message=f"Failed to process student associations: {str(e)}",
                        correlation_id=correlation_id,
                        batch_id=batch_id,
                        error_type=type(e).__name__,
                    )
                # Transaction commits here
