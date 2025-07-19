"""
Default implementation of BatchEssayTracker protocol.

Lean implementation following clean architecture principles with proper DI.
Database operations extracted to BatchTrackerPersistence for <400 LoC compliance.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from common_core.domain_enums import get_course_language
from common_core.events.batch_coordination_events import (
    BatchEssaysReady,
    BatchEssaysRegistered,
    BatchReadinessTimeout,
)
from common_core.events.file_events import EssayValidationFailedV1
from common_core.metadata_models import (
    EntityReference,
    SystemProcessingMetadata,
)
from huleedu_service_libs.logging_utils import create_service_logger

from services.essay_lifecycle_service.implementations.batch_expectation import BatchExpectation
from services.essay_lifecycle_service.implementations.batch_tracker_persistence import (
    BatchTrackerPersistence,
)
from services.essay_lifecycle_service.implementations.redis_batch_coordinator import (
    RedisBatchCoordinator,
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
        redis_coordinator: RedisBatchCoordinator
    ) -> None:
        self._logger = create_service_logger("batch_tracker")
        self._redis_coordinator = redis_coordinator
        self._persistence = persistence
        
        # Keep minimal in-memory state for legacy compatibility during migration
        self.batch_expectations: dict[str, BatchExpectation] = {}  # Deprecated - migrating to Redis
        self.validation_failures: dict[str, list[EssayValidationFailedV1]] = {}
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
        batch_id = batch_essays_registered.batch_id

        # **Idempotency Check: Redis existence first**
        existing_batch_status = await self._redis_coordinator.get_batch_status(batch_id)

        if existing_batch_status is not None:
            # Batch already exists in Redis - handle idempotently
            self._logger.info(
                f"Batch {batch_id} already registered in Redis, acknowledging idempotently",
                extra={
                    "batch_id": batch_id,
                    "new_correlation_id": str(correlation_id),
                    "total_slots": existing_batch_status["total_slots"],
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
            "correlation_id": correlation_id,
            "expected_count": len(batch_essays_registered.essay_ids),
            "created_at": datetime.now().isoformat(),
        }

        # Register batch in Redis coordinator with atomic slot initialization
        await self._redis_coordinator.register_batch_slots(
            batch_id=batch_id,
            essay_ids=batch_essays_registered.essay_ids,
            metadata=batch_metadata,
            timeout_seconds=300,  # 5 minutes default timeout
        )

        # **Legacy database persistence for migration compatibility**
        expectation = BatchExpectation.create_new(
            batch_id=batch_id,
            expected_essay_ids=batch_essays_registered.essay_ids,
            course_code=batch_essays_registered.course_code,
            essay_instructions=batch_essays_registered.essay_instructions,
            user_id=batch_essays_registered.user_id,
            correlation_id=correlation_id,
        )

        # Persist to database (migration compatibility)
        await self._persistence.persist_batch_expectation(expectation)

        # Keep minimal in-memory state for legacy timeout monitoring
        self.batch_expectations[batch_id] = expectation
        await self._start_timeout_monitoring(expectation)

        self._logger.info(
            f"Registered batch {batch_id} in Redis coordinator with "
            f"{len(batch_essays_registered.essay_ids)} slots, course: "
            f"{batch_essays_registered.course_code.value}"
        )

    def assign_slot_to_content(
        self, batch_id: str, text_storage_id: str, original_file_name: str
    ) -> str | None:
        """
        Assign an available slot to content using Redis coordinator for atomic operations.

        Migrated to Redis-based atomic slot assignment to eliminate race conditions
        in distributed deployments.

        Args:
            batch_id: The batch ID
            text_storage_id: Storage ID for the essay content
            original_file_name: Original name of uploaded file

        Returns:
            The assigned internal essay ID if successful, None if no slots available
        """
        # Note: This is a synchronous method in the protocol, but we need async for Redis
        # We'll handle the async call in the calling context for now
        # This is a design constraint that will need protocol updates in future iterations
        
        # For immediate migration compatibility, check Redis first, fallback to in-memory
        # In production, this should be fully async
        import asyncio
        
        try:
            # Create content metadata for Redis storage
            content_metadata = {
                "text_storage_id": text_storage_id,
                "original_file_name": original_file_name,
                "assigned_at": datetime.now().isoformat(),
            }
            
            # Use asyncio.create_task to handle async call in sync context
            # Note: This is a transitional approach - the protocol should be updated to async
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If we're already in an async context, we can't use asyncio.run
                # We'll need to handle this differently
                self._logger.warning(
                    f"Sync method called in async context for batch {batch_id}. "
                    "Using fallback to in-memory assignment."
                )
                # Fallback to legacy in-memory assignment during migration
                return self._assign_slot_legacy(batch_id, text_storage_id, original_file_name)
            else:
                # We're not in an async context, can use asyncio.run
                return asyncio.run(
                    self._redis_coordinator.assign_slot_atomic(batch_id, content_metadata)
                )
                
        except Exception as e:
            self._logger.error(
                f"Redis slot assignment failed for batch {batch_id}, falling back to legacy: {e}"
            )
            # Fallback to legacy in-memory assignment
            return self._assign_slot_legacy(batch_id, text_storage_id, original_file_name)

    def _assign_slot_legacy(
        self, batch_id: str, text_storage_id: str, original_file_name: str
    ) -> str | None:
        """Legacy in-memory slot assignment for fallback during migration."""
        if batch_id not in self.batch_expectations:
            self._logger.error(f"No expectation registered for batch {batch_id}")
            return None

        expectation = self.batch_expectations[batch_id]
        internal_essay_id = expectation.assign_next_slot(text_storage_id, original_file_name)

        # Note: Slot assignment persistence handled separately in async context
        return internal_essay_id

    def mark_slot_fulfilled(
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
        import asyncio
        
        try:
            # Check batch completion using Redis coordinator
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # In async context - use legacy fallback
                return self._mark_slot_fulfilled_legacy(batch_id, internal_essay_id, text_storage_id)
            else:
                # Check completion state in Redis
                is_complete = asyncio.run(
                    self._redis_coordinator.check_batch_completion(batch_id)
                )
                
                if is_complete:
                    # Get batch metadata from Redis for event creation
                    redis_status = asyncio.run(
                        self._redis_coordinator.get_batch_status(batch_id)
                    )
                    
                    if redis_status:
                        return self._create_batch_ready_event_from_redis(batch_id, redis_status)

                return None
                
        except Exception as e:
            self._logger.error(
                f"Redis batch completion check failed for batch {batch_id}, "
                f"falling back to legacy: {e}"
            )
            # Fallback to legacy implementation
            return self._mark_slot_fulfilled_legacy(batch_id, internal_essay_id, text_storage_id)

    def _mark_slot_fulfilled_legacy(
        self, batch_id: str, internal_essay_id: str, text_storage_id: str
    ) -> tuple[BatchEssaysReady, UUID] | None:
        """Legacy in-memory slot fulfillment for fallback during migration."""
        if batch_id not in self.batch_expectations:
            self._logger.error(f"No expectation registered for batch {batch_id}")
            return None

        expectation = self.batch_expectations[batch_id]

        # Mark slot as fulfilled
        expectation.mark_slot_fulfilled(internal_essay_id, text_storage_id)

        # Check completion: either all slots filled OR total processed meets expectation
        failure_count = len(self.validation_failures.get(batch_id, []))
        assigned_count = len(expectation.slot_assignments)
        total_processed = assigned_count + failure_count

        is_complete = expectation.is_complete or total_processed >= expectation.expected_count

        if is_complete:
            return self._create_batch_ready_event(batch_id, expectation)

        return None

    def get_batch_status(self, batch_id: str) -> dict[str, Any] | None:
        """Get current status of a batch using Redis coordinator."""
        import asyncio
        
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # In async context - use legacy fallback
                return self._get_batch_status_legacy(batch_id)
            else:
                # Get status from Redis coordinator
                redis_status = asyncio.run(
                    self._redis_coordinator.get_batch_status(batch_id)
                )
                
                if redis_status:
                    # Convert Redis status to expected format
                    assignments = redis_status.get("assignments", {})
                    ready_essays = []
                    for essay_id, metadata in assignments.items():
                        if isinstance(metadata, dict) and "text_storage_id" in metadata:
                            ready_essays.append({
                                "essay_id": essay_id,
                                "text_storage_id": metadata["text_storage_id"]
                            })
                    
                    return {
                        "batch_id": batch_id,
                        "expected_count": redis_status["total_slots"],
                        "ready_count": redis_status["assigned_slots"],
                        "ready_essays": ready_essays,
                        "missing_essay_ids": [],  # Redis doesn't track this the same way
                        "is_complete": redis_status["is_complete"],
                        "is_timeout_due": not redis_status["has_timeout"],
                        "created_at": redis_status.get("metadata", {}).get("created_at"),
                    }
                
                return None
                
        except Exception as e:
            self._logger.error(
                f"Redis batch status check failed for batch {batch_id}, falling back to legacy: {e}"
            )
            return self._get_batch_status_legacy(batch_id)

    def _get_batch_status_legacy(self, batch_id: str) -> dict[str, Any] | None:
        """Legacy in-memory batch status for fallback during migration."""
        if batch_id not in self.batch_expectations:
            return None

        expectation = self.batch_expectations[batch_id]
        return {
            "batch_id": batch_id,
            "expected_count": expectation.expected_count,
            "ready_count": len(expectation.slot_assignments),
            "ready_essays": expectation.get_ready_essays(),
            "missing_essay_ids": expectation.missing_slot_ids,
            "is_complete": expectation.is_complete,
            "is_timeout_due": expectation.is_timeout_due,
            "created_at": expectation.created_at,
        }

    def list_active_batches(self) -> list[str]:
        """Get list of currently tracked batch IDs."""
        return list(self.batch_expectations.keys())

    async def handle_validation_failure(
        self, event_data: Any
    ) -> Any | None:  # EssayValidationFailedV1 -> BatchEssaysReady | None
        """
        Handle validation failure by adjusting batch expectations.

        Prevents ELS from waiting indefinitely for content that will never arrive.
        """
        validation_failed = EssayValidationFailedV1.model_validate(event_data)
        batch_id = validation_failed.batch_id

        # Track validation failure
        if batch_id not in self.validation_failures:
            self.validation_failures[batch_id] = []
        self.validation_failures[batch_id].append(validation_failed)

        self._logger.info(
            f"Tracked validation failure for batch {batch_id}: "
            f"{validation_failed.validation_error_code} ({validation_failed.original_file_name}). "
            f"Total failures: {len(self.validation_failures[batch_id])}"
        )

        # Check if we should trigger early batch completion
        if batch_id in self.batch_expectations:
            expectation = self.batch_expectations[batch_id]
            failure_count = len(self.validation_failures[batch_id])
            assigned_count = len(expectation.slot_assignments)
            total_processed = assigned_count + failure_count

            self._logger.info(
                f"Batch {batch_id} processing status: {assigned_count} assigned + "
                f"{failure_count} failed = {total_processed}/{expectation.expected_count}"
            )

            # If processed count meets expectation, complete batch early
            if total_processed >= expectation.expected_count:
                self._logger.info(
                    f"Batch {batch_id} completing early: "
                    f"{assigned_count} assigned + {failure_count} failed = {total_processed}"
                )
                event_data, stored_correlation_id = self._create_batch_ready_event(
                    batch_id, expectation
                )
                return event_data, stored_correlation_id

        return None

    def check_batch_completion(self, batch_id: str) -> Any | None:  # BatchEssaysReady | None
        """
        Check if batch is complete and return BatchEssaysReady event if so.

        This is used to check completion after validation failures or other events
        that might complete a batch.
        """
        if batch_id not in self.batch_expectations:
            return None

        expectation = self.batch_expectations[batch_id]
        failure_count = len(self.validation_failures.get(batch_id, []))
        assigned_count = len(expectation.slot_assignments)
        total_processed = assigned_count + failure_count

        # Check if batch is complete (either all slots filled OR processed count meets expectation)
        if expectation.is_complete or total_processed >= expectation.expected_count:
            event_data, stored_correlation_id = self._create_batch_ready_event(
                batch_id, expectation
            )
            return event_data, stored_correlation_id

        return None

    def get_user_id_for_essay(self, essay_id: str) -> str | None:
        """Look up user_id for a given essay by searching through batch expectations."""
        for expectation in self.batch_expectations.values():
            if essay_id in expectation.expected_essay_ids:
                return expectation.user_id
        return None

    async def persist_slot_assignment(
        self, batch_id: str, internal_essay_id: str, text_storage_id: str, original_file_name: str
    ) -> None:
        """Persist slot assignment to database via persistence layer."""
        await self._persistence.persist_slot_assignment(
            batch_id, internal_essay_id, text_storage_id, original_file_name
        )

    async def remove_batch_from_database(self, batch_id: str) -> None:
        """Remove completed batch from database via persistence layer."""
        await self._persistence.remove_batch_from_database(batch_id)

    async def initialize_from_database(self) -> None:
        """Initialize batch expectations from database on startup (recovery mechanism)."""
        if self._initialized:
            return

        try:
            expectations = await self._persistence.initialize_from_database()

            for expectation in expectations:
                self.batch_expectations[expectation.batch_id] = expectation

                # Start timeout monitoring for recovered batches
                await self._start_timeout_monitoring(expectation)

                self._logger.info(
                    f"Recovered batch expectation: {expectation.batch_id} with {len(expectation.slot_assignments)} assignments"
                )

            self._logger.info(
                f"Initialized batch tracker with {len(self.batch_expectations)} active batches from database"
            )

        except Exception as e:
            self._logger.error(f"Failed to initialize from database: {e}")
            # Continue with empty state if database recovery fails

        finally:
            self._initialized = True

    def _create_batch_ready_event(
        self, batch_id: str, expectation: BatchExpectation
    ) -> tuple[BatchEssaysReady, UUID]:
        """Create BatchEssaysReady event and clean up completed batch."""
        # Get validation failures for this batch
        failures: list[EssayValidationFailedV1] = self.validation_failures.get(batch_id, [])

        # Cancel timeout monitoring
        if expectation.timeout_task:
            expectation.timeout_task.cancel()

        # Infer language from course code using helper function
        course_language = get_course_language(expectation.course_code).value

        # Create enhanced BatchEssaysReady event
        ready_event = BatchEssaysReady(
            batch_id=batch_id,
            ready_essays=expectation.get_ready_essays(),
            batch_entity=EntityReference(entity_id=batch_id, entity_type="batch"),
            metadata=SystemProcessingMetadata(
                entity=EntityReference(entity_id=batch_id, entity_type="batch"),
                timestamp=datetime.now(UTC),
                event="batch.essays.ready",
            ),
            # Enhanced lean registration fields from batch context
            course_code=expectation.course_code,
            course_language=course_language,
            essay_instructions=expectation.essay_instructions,
            class_type="GUEST",  # Placeholder - until Class Management Service integration
            teacher_first_name=None,  # No teacher info for GUEST classes
            teacher_last_name=None,  # No teacher info for GUEST classes
            validation_failures=failures if failures else None,
            total_files_processed=len(expectation.slot_assignments) + len(failures),
        )

        successful_count = len(expectation.slot_assignments)
        failed_count = len(failures)
        total_processed = successful_count + failed_count
        course_code = expectation.course_code.value

        summary_msg = (
            f"Batch {batch_id} completed: {successful_count} successful, {failed_count} failed, {total_processed} total processed,"
            f" course: {course_code}"
        )
        self._logger.info(summary_msg)

        # Store correlation ID before cleanup
        original_correlation_id = expectation.correlation_id

        # Clean up completed batch from memory (database cleanup handled separately)
        del self.batch_expectations[batch_id]
        if batch_id in self.validation_failures:
            del self.validation_failures[batch_id]

        return ready_event, original_correlation_id

    def _create_batch_ready_event_from_redis(
        self, batch_id: str, redis_status: dict[str, Any]
    ) -> tuple[BatchEssaysReady, UUID]:
        """Create BatchEssaysReady event from Redis batch status data."""
        from common_core.domain_enums import CourseCode
        from common_core.metadata_models import EssayProcessingInputRefV1
        
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
                        essay_id=essay_id,
                        text_storage_id=assignment_data["text_storage_id"]
                    )
                )
        
        # Get validation failures (still tracked in memory during migration)
        failures: list[EssayValidationFailedV1] = self.validation_failures.get(batch_id, [])
        
        # Create BatchEssaysReady event
        ready_event = BatchEssaysReady(
            batch_id=batch_id,
            ready_essays=ready_essays,
            batch_entity=EntityReference(entity_id=batch_id, entity_type="batch"),
            metadata=SystemProcessingMetadata(
                entity=EntityReference(entity_id=batch_id, entity_type="batch"),
                timestamp=datetime.now(UTC),
                event="batch.essays.ready",
            ),
            course_code=course_code,
            course_language=course_language,
            essay_instructions=metadata.get("essay_instructions", ""),
            class_type="GUEST",  # Placeholder
            teacher_first_name=None,
            teacher_last_name=None,
            validation_failures=failures if failures else None,
            total_files_processed=len(ready_essays) + len(failures),
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
            f"{len(ready_essays)} successful, {len(failures)} failed"
        )

        # Clean up in-memory state
        if batch_id in self.batch_expectations:
            del self.batch_expectations[batch_id]
        if batch_id in self.validation_failures:
            del self.validation_failures[batch_id]

        return ready_event, correlation_id

    async def _start_timeout_monitoring(self, expectation: BatchExpectation) -> None:
        """Start timeout monitoring for a batch expectation."""

        async def timeout_monitor() -> None:
            await asyncio.sleep(expectation.timeout_seconds)

            # Check if batch is still pending
            if expectation.batch_id in self.batch_expectations:
                self._logger.warning(
                    f"Batch {expectation.batch_id} timed out. "
                    f"Ready: {len(expectation.slot_assignments)}/{expectation.expected_count}"
                )

                # Create timeout event
                ready_essays = expectation.get_ready_essays()
                timeout_event = BatchReadinessTimeout(
                    batch_id=expectation.batch_id,
                    ready_essays=ready_essays,
                    missing_essay_ids=expectation.missing_slot_ids,
                    expected_count=expectation.expected_count,
                    actual_count=len(expectation.slot_assignments),
                    timeout_duration_seconds=expectation.timeout_seconds,
                    metadata=SystemProcessingMetadata(
                        entity=EntityReference(entity_id=expectation.batch_id, entity_type="batch"),
                        timestamp=datetime.now(UTC),
                        event="batch.readiness.timeout",
                    ),
                )

                # Emit timeout event if callback registered
                if "batch.readiness.timeout" in self._event_callbacks:
                    await self._event_callbacks["batch.readiness.timeout"](timeout_event)

                # Clean up timed out batch
                del self.batch_expectations[expectation.batch_id]

        expectation.timeout_task = asyncio.create_task(timeout_monitor())
