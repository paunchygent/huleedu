"""
Default implementation of BatchEssayTracker protocol.

Lean implementation following clean architecture principles with proper DI.
Database operations extracted to BatchTrackerPersistence for <400 LoC compliance.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from common_core.domain_enums import get_course_language
from common_core.events.batch_coordination_events import (
    BatchEssaysReady,
    BatchEssaysRegistered,
)
from common_core.events.file_events import EssayValidationFailedV1
from common_core.metadata_models import (
    # EntityReference removed - using primitive parameters
    EssayProcessingInputRefV1,
    SystemProcessingMetadata,
)
from huleedu_service_libs.logging_utils import create_service_logger
from sqlalchemy.ext.asyncio import AsyncSession

from services.essay_lifecycle_service.implementations.batch_expectation import BatchExpectation
from services.essay_lifecycle_service.implementations.batch_tracker_persistence import (
    BatchTrackerPersistence,
)
from services.essay_lifecycle_service.implementations.redis_batch_queries import RedisBatchQueries
from services.essay_lifecycle_service.implementations.redis_batch_state import RedisBatchState
from services.essay_lifecycle_service.implementations.redis_failure_tracker import (
    RedisFailureTracker,
)
from services.essay_lifecycle_service.implementations.redis_pending_content_ops import (
    RedisPendingContentOperations,
)
from services.essay_lifecycle_service.implementations.redis_slot_operations import (
    RedisSlotOperations,
)
from services.essay_lifecycle_service.protocols import BatchEssayTracker


class DefaultBatchEssayTracker(BatchEssayTracker):
    """
    Default implementation of BatchEssayTracker protocol.

    Manages batch slot assignment and readiness tracking across multiple batches.
    Implements the ELS side of slot-based batch coordination pattern.
    Enhanced to handle validation failures and prevent infinite waits.
    """

    def __init__(
        self,
        persistence: BatchTrackerPersistence,
        batch_state: RedisBatchState,
        batch_queries: RedisBatchQueries,
        failure_tracker: RedisFailureTracker,
        slot_operations: RedisSlotOperations,
        pending_content_ops: RedisPendingContentOperations,
    ) -> None:
        self._logger = create_service_logger("batch_tracker")
        self._batch_state = batch_state
        self._batch_queries = batch_queries
        self._failure_tracker = failure_tracker
        self._slot_operations = slot_operations
        self._pending_content_ops = pending_content_ops
        self._persistence = persistence
        self._event_callbacks: dict[str, Callable[[Any], Awaitable[None]]] = {}
        self._initialized = False

    def register_event_callback(
        self, event_type: str, callback: Callable[[Any], Awaitable[None]]
    ) -> None:
        """Register callback for batch coordination events."""
        self._event_callbacks[event_type] = callback

    async def register_batch(
        self, event: Any, correlation_id: UUID
    ) -> None:  # BatchEssaysRegistered
        """
        Register batch slot expectations using Redis coordinator for distributed coordination.

        Migrated from in-memory state to Redis-based distributed coordination to eliminate
        race conditions in multi-instance deployments.

        Args:
            event: BatchEssaysRegistered from BOS containing essay-ID slots and course context
        """
        batch_essays_registered = BatchEssaysRegistered.model_validate(event)
        batch_id = batch_essays_registered.entity_id

        # **Idempotency Check: Redis existence first**
        existing_batch_status = await self._batch_queries.get_batch_status(batch_id)

        if existing_batch_status is not None:
            # Batch already exists in Redis - handle idempotently
            self._logger.info(
                f"Batch {batch_id} already registered in Redis, acknowledging idempotently",
                extra={
                    "batch_id": batch_id,
                    "new_correlation_id": str(correlation_id),
                    "expected_count": existing_batch_status["total_slots"],
                    "available_slots": existing_batch_status["available_slots"],
                },
            )
            return

        # **Database idempotency check for migration compatibility**
        existing_db_batch = await self._persistence.get_batch_from_database(batch_id)
        if existing_db_batch is not None:
            self._logger.info(
                f"Batch {batch_id} exists in database, migrating to Redis coordinator"
            )

        # **New Batch Registration in Redis**
        # Prepare batch metadata for Redis storage
        batch_metadata = {
            "batch_id": batch_id,
            "course_code": batch_essays_registered.course_code.value,
            "essay_instructions": batch_essays_registered.essay_instructions,
            "user_id": batch_essays_registered.user_id,
            "correlation_id": str(correlation_id),  # Convert UUID to string for Redis storage
            "expected_count": len(batch_essays_registered.essay_ids),
            "class_type": "REGULAR" if batch_essays_registered.class_id else "GUEST",
            "created_at": datetime.now().isoformat(),
        }

        # Register batch in Redis coordinator with atomic slot initialization
        await self._batch_state.register_batch_slots(
            batch_id=batch_id,
            essay_ids=batch_essays_registered.essay_ids,
            metadata=batch_metadata,
            timeout_seconds=86400,  # 24 hours for complex processing including overnight LLM batches
        )

        # **Create BatchExpectation for database persistence**
        expectation = BatchExpectation(
            batch_id=batch_id,
            expected_essay_ids=frozenset(batch_essays_registered.essay_ids),
            expected_count=len(batch_essays_registered.essay_ids),
            course_code=batch_essays_registered.course_code,
            essay_instructions=batch_essays_registered.essay_instructions,
            user_id=batch_essays_registered.user_id,
            correlation_id=correlation_id,
            created_at=datetime.now(UTC),
            timeout_seconds=86400,  # 24 hours for complex processing
        )

        # Persist to database
        await self._persistence.persist_batch_expectation(expectation)

        # Timeout monitoring is handled by Redis TTL in register_batch_slots

        self._logger.info(
            f"Registered batch {batch_id} in Redis coordinator with "
            f"{len(batch_essays_registered.essay_ids)} slots, course: "
            f"{batch_essays_registered.course_code.value}"
        )

    async def assign_slot_to_content(
        self, batch_id: str, text_storage_id: str, original_file_name: str
    ) -> str | None:
        """
        Assign an available slot to content using Redis coordinator for atomic operations.

        Uses Redis-based atomic slot assignment to eliminate race conditions
        in distributed deployments.

        Args:
            batch_id: The batch ID
            text_storage_id: Storage ID for the essay content
            original_file_name: Original name of uploaded file

        Returns:
            The assigned internal essay ID if successful, None if no slots available
        """
        try:
            # Create content metadata for Redis storage
            content_metadata = {
                "text_storage_id": text_storage_id,
                "original_file_name": original_file_name,
                "assigned_at": datetime.now(UTC).isoformat(),
            }

            # Use Redis coordinator for atomic slot assignment
            return await self._slot_operations.assign_slot_atomic(batch_id, content_metadata)

        except Exception as e:
            self._logger.error(
                f"Redis slot assignment failed for batch {batch_id}: {e}", exc_info=True
            )
            # Re-raise to let caller handle the error
            raise

    async def mark_slot_fulfilled(
        self, batch_id: str, internal_essay_id: str, text_storage_id: str
    ) -> tuple[BatchEssaysReady, UUID] | None:  # (BatchEssaysReady, correlation_id) | None
        """
        Mark a slot as fulfilled and check if batch is complete.

        Uses Redis coordinator to check batch completion state for distributed coordination.

        Args:
            batch_id: The batch ID
            internal_essay_id: The internal essay ID slot that was fulfilled
            text_storage_id: The text storage ID that fulfilled the slot

        Returns:
            BatchEssaysReady event if batch is complete, None otherwise
        """
        try:
            # Check completion state in Redis using atomic coordinator
            is_complete = await self._batch_state.check_batch_completion(batch_id)

            if is_complete:
                # Atomically mark as completed to prevent double-completion
                marked_complete = await self._batch_state.mark_batch_completed_atomically(batch_id)
                if marked_complete:
                    # Get batch metadata from Redis for event creation
                    redis_status = await self._batch_queries.get_batch_status(batch_id)
                    if redis_status:
                        return await self._create_batch_ready_event_from_redis(
                            batch_id, redis_status
                        )

            return None

        except Exception as e:
            self._logger.error(
                f"Redis batch completion check failed for batch {batch_id}: {e}", exc_info=True
            )
            # Re-raise to let caller handle the error
            raise

    async def get_batch_status(self, batch_id: str) -> dict[str, Any] | None:
        """Get current status of a batch using Redis coordinator."""
        try:
            # Get status from Redis coordinator
            redis_status = await self._batch_queries.get_batch_status(batch_id)

            if redis_status:
                # Convert Redis status to expected format
                assignments = redis_status.get("assignments", {})
                ready_essays = []
                for essay_id, metadata in assignments.items():
                    if isinstance(metadata, dict) and "text_storage_id" in metadata:
                        ready_essays.append(
                            {"essay_id": essay_id, "text_storage_id": metadata["text_storage_id"]}
                        )

                # Get missing slots from Redis
                missing_slots = await self._batch_queries.get_missing_slots(batch_id)

                return {
                    "batch_id": batch_id,
                    "expected_count": redis_status["total_slots"],
                    "ready_count": redis_status["assigned_slots"],
                    "ready_essays": ready_essays,
                    "missing_essay_ids": missing_slots,
                    "is_complete": redis_status["is_complete"],
                    "is_timeout_due": not redis_status["has_timeout"],
                    "created_at": redis_status.get("metadata", {}).get("created_at"),
                    "user_id": redis_status.get("metadata", {}).get("user_id"),
                }

            return None

        except Exception as e:
            self._logger.error(
                f"Redis batch status check failed for batch {batch_id}: {e}", exc_info=True
            )
            # Re-raise to let caller handle the error
            raise

    async def list_active_batches(self) -> list[str]:
        """Get list of currently tracked batch IDs from Redis."""
        try:
            # Use Redis coordinator to scan for active batch metadata keys
            active_batch_ids = await self._batch_queries.list_active_batch_ids()
            return active_batch_ids

        except Exception as e:
            self._logger.error(f"Failed to list active batches: {e}", exc_info=True)
            raise

    async def handle_validation_failure(
        self, event_data: Any
    ) -> Any | None:  # EssayValidationFailedV1 -> BatchEssaysReady | None
        """
        Handle validation failure by adjusting batch expectations.

        Prevents ELS from waiting indefinitely for content that will never arrive.
        If batch doesn't exist yet, stores failure as pending.
        """
        validation_failed = EssayValidationFailedV1.model_validate(event_data)
        batch_id = validation_failed.entity_id

        # Track validation failure in Redis
        failure_data = {
            "batch_id": batch_id,
            "file_upload_id": validation_failed.file_upload_id,
            "original_file_name": validation_failed.original_file_name,
            "validation_error_code": validation_failed.validation_error_code.value,
            "validation_error_detail": validation_failed.validation_error_detail.model_dump(
                mode="json"
            ),
            "file_size_bytes": validation_failed.file_size_bytes,
            "raw_file_storage_id": validation_failed.raw_file_storage_id,
            "correlation_id": str(validation_failed.correlation_id)
            if validation_failed.correlation_id
            else None,
            "timestamp": datetime.now(UTC).isoformat(),
        }

        await self._failure_tracker.track_validation_failure(batch_id, failure_data)

        # Check if batch exists before attempting completion check
        batch_status = await self._batch_queries.get_batch_status(batch_id)
        if batch_status is None:
            # Batch not registered yet - failure stored as pending
            self._logger.info(
                f"Stored pending validation failure for unregistered batch {batch_id}: "
                f"{validation_failed.validation_error_code} ({validation_failed.original_file_name})"
            )
            return None

        # Get current failure count
        failure_count = await self._failure_tracker.get_validation_failure_count(batch_id)

        self._logger.info(
            f"Tracked validation failure for batch {batch_id}: "
            f"{validation_failed.validation_error_code} ({validation_failed.original_file_name}). "
            f"Total failures: {failure_count}"
        )

        # Check if batch is now complete after this failure
        return await self.check_batch_completion(batch_id)

    async def check_batch_completion(self, batch_id: str) -> tuple[Any, UUID] | None:
        """
        Check if batch is complete and return BatchEssaysReady event with correlation ID if so.

        This is used to check completion after validation failures or other events
        that might complete a batch.

        Returns:
            tuple[BatchEssaysReady, UUID] if batch is complete, None otherwise
        """
        # Check if batch is complete using Redis coordinator
        batch_status = await self._batch_queries.get_batch_status(batch_id)
        if not batch_status:
            return None

        # Use atomic completion check that considers all scenarios
        is_complete = await self._batch_state.check_batch_completion(batch_id)
        if is_complete:
            # Try to atomically mark as completed, but return event regardless of whether
            # we marked it or it was already marked (e.g., during pending failure processing)
            await self._batch_state.mark_batch_completed_atomically(batch_id)
            return await self._create_batch_ready_event_from_redis(batch_id, batch_status)

        return None

    async def get_user_id_for_essay(self, essay_id: str) -> str | None:
        """Look up user_id for a given essay by searching through batch expectations."""
        try:
            # Use Redis coordinator to find the batch containing this essay
            result = await self._batch_queries.find_batch_for_essay(essay_id)

            if result is not None:
                _, user_id = result  # Only need user_id, ignore batch_id
                return user_id

            return None

        except Exception as e:
            self._logger.error(f"Failed to get user_id for essay {essay_id}: {e}", exc_info=True)
            raise

    async def persist_slot_assignment(
        self,
        batch_id: str,
        internal_essay_id: str,
        text_storage_id: str,
        original_file_name: str,
        session: AsyncSession | None = None,
    ) -> None:
        """Persist slot assignment to database via persistence layer."""
        await self._persistence.persist_slot_assignment(
            batch_id, internal_essay_id, text_storage_id, original_file_name, session=session
        )

    async def remove_batch_from_database(self, batch_id: str) -> None:
        """Remove completed batch from database via persistence layer."""
        await self._persistence.remove_batch_from_database(batch_id)

    async def process_pending_content_for_batch(self, batch_id: str) -> int:
        """
        Process any pending content for a newly registered batch.

        This method handles only Redis-level slot assignment operations.
        Database coordination is handled separately by the ContentAssignmentService.

        Returns:
            Number of pending content items successfully assigned to slots
        """
        # Get all pending content
        pending_content = await self._pending_content_ops.get_pending_content(batch_id)

        if not pending_content:
            return 0

        assigned_count = 0

        for content_metadata in pending_content:
            text_storage_id = content_metadata["text_storage_id"]

            # Try to assign to available slot (Redis operation only)
            assigned_essay_id = await self._slot_operations.assign_slot_atomic(
                batch_id, content_metadata
            )

            if assigned_essay_id:
                # Successfully assigned - remove from pending
                await self._pending_content_ops.remove_pending_content(batch_id, text_storage_id)
                assigned_count += 1

                self._logger.info(
                    f"Assigned pending content to Redis slot: {text_storage_id} -> {assigned_essay_id}",
                    extra={
                        "batch_id": batch_id,
                        "text_storage_id": text_storage_id,
                        "assigned_essay_id": assigned_essay_id,
                    },
                )
            else:
                # No slots available - content remains as excess
                self._logger.warning(
                    f"No slots for pending content {text_storage_id} in batch {batch_id}",
                    extra={"batch_id": batch_id, "text_storage_id": text_storage_id},
                )

        self._logger.info(
            f"Processed {assigned_count} pending content items for batch {batch_id}",
            extra={"batch_id": batch_id, "assigned_count": assigned_count},
        )

        return assigned_count

    async def initialize_from_database(self) -> None:
        """Initialize batch expectations from database on startup (recovery mechanism)."""
        if self._initialized:
            return

        try:
            expectations = await self._persistence.initialize_from_database()

            for expectation in expectations:
                # Migrate recovered batch to Redis coordinator
                batch_metadata = {
                    "batch_id": expectation.batch_id,
                    "course_code": expectation.course_code.value,
                    "essay_instructions": expectation.essay_instructions,
                    "user_id": expectation.user_id,
                    "correlation_id": str(expectation.correlation_id),
                    "expected_count": expectation.expected_count,
                    "created_at": expectation.created_at.isoformat(),
                }

                # Register in Redis if not already there
                existing_status = await self._batch_queries.get_batch_status(expectation.batch_id)
                if not existing_status:
                    await self._batch_state.register_batch_slots(
                        batch_id=expectation.batch_id,
                        essay_ids=list(expectation.expected_essay_ids),
                        metadata=batch_metadata,
                        timeout_seconds=expectation.timeout_seconds,
                    )

                self._logger.info(
                    f"Recovered batch expectation: {expectation.batch_id} to Redis coordinator"
                )

            self._logger.info(
                f"Initialized batch tracker with {len(expectations)} batches migrated to Redis"
            )

        except Exception as e:
            self._logger.error(f"Failed to initialize from database: {e}")
            # Continue with empty state if database recovery fails

        finally:
            self._initialized = True

    async def _create_batch_ready_event_from_redis(
        self, batch_id: str, redis_status: dict[str, Any]
    ) -> tuple[BatchEssaysReady, UUID]:
        """Create BatchEssaysReady event from Redis batch status data."""
        from common_core.domain_enums import CourseCode

        # Extract metadata from Redis status
        metadata = redis_status.get("metadata", {})
        assignments = redis_status.get("assignments", {})

        # Parse course code from metadata
        course_code_str = metadata.get("course_code", "ENGLISH_INTERMEDIATE")
        course_code = CourseCode(course_code_str)
        course_language = get_course_language(course_code).value

        # Convert Redis assignments to EssayProcessingInputRefV1 format
        ready_essays = []
        for essay_id, assignment_data in assignments.items():
            if isinstance(assignment_data, dict) and "text_storage_id" in assignment_data:
                ready_essays.append(
                    EssayProcessingInputRefV1(
                        essay_id=essay_id, text_storage_id=assignment_data["text_storage_id"]
                    )
                )

        # NOTE: Validation failures are now handled via separate BatchValidationErrorsV1 events
        # following structured error handling principles. Legacy validation_failures field removed.

        # Extract class_type from metadata with explicit validation
        class_type = metadata.get("class_type")
        if class_type not in ["GUEST", "REGULAR"]:
            raise ValueError(f"Invalid or missing class_type in batch metadata: {class_type}")

        # Create clean BatchEssaysReady event with NO legacy validation fields
        ready_event = BatchEssaysReady(
            batch_id=batch_id,
            ready_essays=ready_essays,
            # batch_entity removed - using primitive parameters in event model
            metadata=SystemProcessingMetadata(
                entity_id=batch_id,
                entity_type="batch",
                parent_id=None,
                timestamp=datetime.now(UTC),
                event="batch.essays.ready",
            ),
            course_code=course_code,
            course_language=course_language,
            essay_instructions=metadata.get("essay_instructions", ""),
            class_type=class_type,
        )

        # Extract correlation ID from metadata
        correlation_id_str = metadata.get("correlation_id")
        if correlation_id_str:
            try:
                correlation_id = UUID(correlation_id_str)
            except (ValueError, TypeError):
                # Fallback to generating new correlation ID
                from uuid import uuid4

                correlation_id = uuid4()
        else:
            from uuid import uuid4

            correlation_id = uuid4()

        self._logger.info(
            f"Batch {batch_id} completed via Redis coordinator: "
            f"{len(ready_essays)} essays ready for processing, class_type: {class_type}"
        )

        # NOTE: Redis cleanup moved to handler AFTER event publication
        # GUEST batches: cleaned up in batch_coordination_handler after BatchContentProvisioningCompleted
        # REGULAR batches: cleaned up in student_association_handler after BatchEssaysReady
        if class_type == "GUEST":
            self._logger.info(
                f"GUEST batch {batch_id} Redis state will be cleaned up after event publication"
            )
        else:
            self._logger.info(
                f"REGULAR batch {batch_id} Redis state preserved for student association confirmation"
            )

        return ready_event, correlation_id

    async def cleanup_batch(self, batch_id: str) -> None:
        """Clean up Redis state for completed batch."""
        await self._batch_state.cleanup_batch(batch_id)
