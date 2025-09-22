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

        This handler acts as a stateless event router during Phase 1.
        It simply publishes BatchEssaysReady for REGULAR batches after
        associations are confirmed, without updating any essay state.

        1. Retrieve ready essays from batch tracker
        2. Create and publish BatchEssaysReady event
        3. Clean up Redis state
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
                    # Retrieve batch status and ready essays
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
                    from common_core.domain_enums import get_course_language

                    # Get course code from the event data
                    course_code = event_data.course_code
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
                        essay_instructions="Instructions pending context integration.",
                        class_type="REGULAR",  # Always REGULAR for this flow
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

                    # Mark batch completed (DB) for REGULAR after associations (no immediate deletion)
                    await self.batch_tracker.mark_batch_completed(batch_id, session)

                    logger.info(
                        f"Successfully routed student associations for batch {batch_id} to BOS",
                        extra={
                            "batch_id": batch_id,
                            "ready_essays_count": len(ready_essays),
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
