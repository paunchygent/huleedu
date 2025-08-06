"""
Association timeout monitor for auto-confirming pending associations after 24 hours.

This handler monitors pending student-essay associations and automatically confirms
high-confidence matches after the 24-hour validation timeout expires.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from common_core.error_enums import ErrorCode
from common_core.status_enums import AssociationValidationMethod
from huleedu_service_libs.error_handling import (
    HuleEduError,
    create_error_detail_with_context,
    raise_processing_error,
)
from huleedu_service_libs.logging_utils import create_service_logger
from sqlalchemy import and_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import joinedload

from services.class_management_service.models_db import EssayStudentAssociation, Student, UserClass

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from services.class_management_service.protocols import ClassEventPublisherProtocol

logger = create_service_logger("class_management_service.timeout_monitor")

# Constants
TIMEOUT_HOURS = 24
HIGH_CONFIDENCE_THRESHOLD = 0.7
CHECK_INTERVAL_MINUTES = 60  # Check every hour


class AssociationTimeoutMonitor:
    """
    Monitors pending associations and auto-confirms after timeout.

    This service runs periodically to check for associations that have been
    pending validation for more than 24 hours and automatically confirms
    high-confidence matches.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        event_publisher: ClassEventPublisherProtocol,
    ) -> None:
        self.session_factory = session_factory
        self.event_publisher = event_publisher
        self._running = False
        self._monitor_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Start the timeout monitor background task."""
        if self._running:
            logger.warning("Timeout monitor already running")
            return

        self._running = True
        logger.info("Starting association timeout monitor")

        # Run the monitor in a background task
        self._monitor_task = asyncio.create_task(self._monitor_loop())

    async def stop(self) -> None:
        """Stop the timeout monitor."""
        logger.info("Stopping association timeout monitor")
        self._running = False

        # Wait for the monitor task to complete if it exists
        if self._monitor_task and not self._monitor_task.done():
            try:
                await asyncio.wait_for(self._monitor_task, timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning("Timeout monitor task did not complete within 5 seconds")
                self._monitor_task.cancel()
                try:
                    await self._monitor_task
                except asyncio.CancelledError:
                    pass

    async def _monitor_loop(self) -> None:
        """Main monitoring loop that runs periodically."""
        while self._running:
            try:
                await self._check_and_process_timeouts()
            except HuleEduError:
                # Structured errors are already logged by the error handling system
                # Just continue the monitoring loop
                pass
            except (SQLAlchemyError, ConnectionError, OSError) as e:
                # Infrastructure errors that should not stop the monitor
                logger.error(
                    f"Infrastructure error in timeout monitor loop: {e}",
                    exc_info=True,
                    extra={"error_type": type(e).__name__},
                )
            except Exception as e:
                # Unexpected errors - raise as structured error
                error_detail = create_error_detail_with_context(
                    error_code=ErrorCode.PROCESSING_ERROR,
                    message=f"Unexpected error in timeout monitor loop: {e}",
                    service="class_management_service",
                    operation="timeout_monitor_loop",
                )
                logger.error(
                    f"Unexpected error in timeout monitor loop: {e}",
                    exc_info=True,
                    extra={"correlation_id": str(error_detail.correlation_id)},
                )

            # Wait before next check
            await asyncio.sleep(CHECK_INTERVAL_MINUTES * 60)

    async def _check_and_process_timeouts(self) -> None:
        """Check for timed-out associations and process them."""
        # Generate correlation ID for this monitoring cycle
        correlation_id = uuid4()

        async with self.session_factory() as session:
            try:
                # Find associations pending for more than 24 hours
                # Use timezone-naive datetime to match database schema (TIMESTAMP WITHOUT TIME ZONE)
                timeout_threshold = datetime.now(UTC).replace(tzinfo=None) - timedelta(
                    hours=TIMEOUT_HOURS
                )

                stmt = (
                    select(EssayStudentAssociation)
                    .options(
                        joinedload(EssayStudentAssociation.user_class).joinedload(UserClass.course)
                    )
                    .where(
                        and_(
                            EssayStudentAssociation.validation_status == "pending_validation",
                            EssayStudentAssociation.created_at <= timeout_threshold,
                        )
                    )
                )

                result = await session.execute(stmt)
                pending_associations = result.unique().scalars().all()

                if not pending_associations:
                    logger.debug("No associations found requiring timeout processing")
                    return

                # Group associations by batch_id and class_id
                batch_associations: dict[tuple[UUID, UUID], list[EssayStudentAssociation]] = {}

                for assoc in pending_associations:
                    key = (assoc.batch_id, assoc.class_id)
                    if key not in batch_associations:
                        batch_associations[key] = []
                    batch_associations[key].append(assoc)

                logger.info(
                    f"Found {len(pending_associations)} associations in "
                    f"{len(batch_associations)} batches requiring timeout processing",
                    extra={"correlation_id": str(correlation_id)},
                )

                # Process each batch
                for (batch_id, class_id), associations in batch_associations.items():
                    await self._process_batch_timeout(
                        session, batch_id, class_id, associations, correlation_id
                    )

            except SQLAlchemyError as e:
                # Database-specific errors with detailed context
                raise_processing_error(
                    service="class_management_service",
                    operation="check_and_process_timeouts",
                    message=f"Database error during timeout processing: {e}",
                    correlation_id=correlation_id,
                    error_type="database_error",
                    sql_error=str(e),
                )
            except Exception as e:
                # Unexpected errors during timeout processing
                raise_processing_error(
                    service="class_management_service",
                    operation="check_and_process_timeouts",
                    message=f"Failed to check and process timeouts: {e}",
                    correlation_id=correlation_id,
                    error_type="unexpected_error",
                    original_error=str(e),
                )

    async def _process_batch_timeout(
        self,
        session: AsyncSession,
        batch_id: UUID,
        class_id: UUID,
        associations: list[EssayStudentAssociation],
        correlation_id: UUID,
    ) -> None:
        """Process timeout for associations in a single batch."""
        try:
            logger.info(
                f"Processing timeout for batch {batch_id} with {len(associations)} associations",
                extra={"correlation_id": str(correlation_id), "batch_id": str(batch_id)},
            )

            # Get course_code from the first association (all should have same class)
            if not associations[0].user_class or not associations[0].user_class.course:
                logger.error(
                    f"No class or course found for associations in batch {batch_id}",
                    extra={"correlation_id": str(correlation_id), "batch_id": str(batch_id)},
                )
                return

            course_code = associations[0].user_class.course.course_code

            # Prepare confirmed associations
            confirmed_associations = []
            validation_summary = {
                "total_associations": len(associations),
                "confirmed": 0,
                "rejected": 0,
            }

            # Auto-confirm high-confidence matches or create UNKNOWN associations
            for assoc in associations:
                if assoc.confidence_score and assoc.confidence_score >= HIGH_CONFIDENCE_THRESHOLD:
                    # Update association as confirmed for high-confidence
                    assoc.validation_status = "confirmed"
                    assoc.validation_method = AssociationValidationMethod.TIMEOUT.value
                    assoc.validated_at = datetime.now(UTC).replace(tzinfo=None)
                    assoc.validated_by = "SYSTEM_TIMEOUT"

                    confirmed_associations.append(
                        {
                            "essay_id": str(assoc.essay_id),
                            "student_id": str(assoc.student_id),
                            "confidence_score": assoc.confidence_score,
                            "validation_method": AssociationValidationMethod.TIMEOUT.value,
                            "validated_by": "SYSTEM_TIMEOUT",
                            "validated_at": assoc.validated_at,
                        }
                    )
                    validation_summary["confirmed"] += 1
                else:
                    # For low-confidence matches, create UNKNOWN student association
                    # First, we need to create or get an UNKNOWN student for this class
                    # Update the association to point to UNKNOWN student

                    # Get or create UNKNOWN student for this class
                    unknown_student = await self._get_or_create_unknown_student(session, class_id)

                    # Update association to UNKNOWN student
                    assoc.student_id = unknown_student.id
                    assoc.validation_status = "confirmed"
                    assoc.validation_method = AssociationValidationMethod.TIMEOUT.value
                    assoc.validated_at = datetime.now(UTC).replace(tzinfo=None)
                    assoc.validated_by = "SYSTEM_TIMEOUT"

                    confirmed_associations.append(
                        {
                            "essay_id": str(assoc.essay_id),
                            "student_id": str(unknown_student.id),
                            "confidence_score": 0.0,  # No confidence for UNKNOWN
                            "validation_method": AssociationValidationMethod.TIMEOUT.value,
                            "validated_by": "SYSTEM_TIMEOUT",
                            "validated_at": assoc.validated_at,
                        }
                    )
                    validation_summary["confirmed"] += 1

            # Commit the updates
            await session.commit()

            # Publish StudentAssociationsConfirmedV1 event
            if confirmed_associations:
                await self.event_publisher.publish_student_associations_confirmed(
                    batch_id=str(batch_id),
                    class_id=str(class_id),
                    course_code=course_code,
                    associations=confirmed_associations,
                    timeout_triggered=True,
                    validation_summary=validation_summary,
                    correlation_id=correlation_id,
                )

                logger.info(
                    f"Published timeout confirmations for batch {batch_id}: "
                    f"{validation_summary['confirmed']} confirmed, "
                    f"{validation_summary['rejected']} rejected"
                )

        except SQLAlchemyError as e:
            # Database-specific batch processing errors
            logger.error(
                f"Database error processing batch timeout for {batch_id}: {e}",
                exc_info=True,
                extra={"correlation_id": str(correlation_id), "batch_id": str(batch_id)},
            )
            # Rollback this batch's changes
            await session.rollback()
            # Don't raise - continue with other batches
        except Exception as e:
            # Other errors during batch processing (event publishing, validation, etc.)
            logger.error(
                f"Failed to process batch timeout for {batch_id}: {e}",
                exc_info=True,
                extra={
                    "correlation_id": str(correlation_id),
                    "batch_id": str(batch_id),
                    "error_type": type(e).__name__,
                },
            )
            # Rollback this batch's changes
            await session.rollback()
            # Don't raise - continue with other batches

    async def _get_or_create_unknown_student(
        self,
        session: AsyncSession,
        class_id: UUID,
    ) -> Student:
        """Get or create an UNKNOWN student for the class."""
        # Check if UNKNOWN student already exists for this class
        stmt = select(Student).where(
            and_(
                Student.first_name == "UNKNOWN",
                Student.last_name == "STUDENT",
                Student.classes.any(UserClass.id == class_id),
            )
        )

        result = await session.execute(stmt)
        unknown_student = result.scalar_one_or_none()

        if unknown_student:
            return unknown_student

        # Create new UNKNOWN student
        # Use class ID in email to make it unique across different classes
        unknown_student = Student(
            first_name="UNKNOWN",
            last_name="STUDENT",
            email=f"unknown.{class_id}@huleedu.system",
            created_by_user_id="SYSTEM_TIMEOUT",
        )

        # Add to the class
        class_stmt = select(UserClass).where(UserClass.id == class_id)
        class_result = await session.execute(class_stmt)
        user_class = class_result.scalar_one_or_none()

        if user_class:
            unknown_student.classes.append(user_class)

        session.add(unknown_student)
        await session.flush()  # Get the ID without committing

        logger.info(f"Created UNKNOWN student {unknown_student.id} for class {class_id}")

        return unknown_student
