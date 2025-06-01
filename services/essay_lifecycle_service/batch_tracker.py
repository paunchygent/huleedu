"""
Batch readiness tracking for Essay Lifecycle Service.

Implements count-based aggregation pattern for coordinating batch processing
between BOS (Batch Orchestrator Service) and File Service.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from typing import Any

from common_core.events.batch_coordination_events import (
    BatchEssaysReady,
    BatchEssaysRegistered,
    BatchReadinessTimeout,
)
from common_core.events.file_events import EssayContentReady
from common_core.metadata_models import EntityReference, SystemProcessingMetadata
from huleedu_service_libs.logging_utils import create_service_logger

logger = create_service_logger("batch_tracker")


class BatchExpectation:
    """
    Tracks expectations for a specific batch.

    Maintains the count-based coordination state between BOS and ELS.
    """

    def __init__(
        self,
        batch_id: str,
        expected_count: int,
        essay_ids: list[str],
        timeout_seconds: int = 300,  # 5 minutes default
    ) -> None:
        self.batch_id = batch_id
        self.expected_count = expected_count
        self.expected_essay_ids = set(essay_ids)
        self.ready_essay_ids: set[str] = set()
        self.created_at = datetime.utcnow()
        self.timeout_seconds = timeout_seconds
        self._timeout_task: asyncio.Task[None] | None = None

    @property
    def is_complete(self) -> bool:
        """Check if all expected essays are ready."""
        return len(self.ready_essay_ids) >= self.expected_count

    @property
    def is_timeout_due(self) -> bool:
        """Check if batch has exceeded timeout duration."""
        elapsed = datetime.utcnow() - self.created_at
        return elapsed > timedelta(seconds=self.timeout_seconds)

    @property
    def missing_essay_ids(self) -> list[str]:
        """Get list of essays still pending."""
        return list(self.expected_essay_ids - self.ready_essay_ids)

    def mark_essay_ready(self, essay_id: str) -> bool:
        """
        Mark an essay as ready.

        Returns:
            True if this completes the batch, False otherwise
        """
        if essay_id not in self.expected_essay_ids:
            logger.warning(f"Essay {essay_id} not expected in batch {self.batch_id}")
            return False

        self.ready_essay_ids.add(essay_id)
        logger.info(
            f"Essay {essay_id} ready for batch {self.batch_id}. "
            f"Progress: {len(self.ready_essay_ids)}/{self.expected_count}"
        )

        return self.is_complete


class BatchEssayTracker:
    """
    Manages batch readiness tracking across multiple batches.

    Implements the ELS side of count-based batch coordination pattern.
    """

    def __init__(self) -> None:
        self.batch_expectations: dict[str, BatchExpectation] = {}
        self._event_callbacks: dict[str, Callable[[Any], Awaitable[None]]] = {}

    def register_event_callback(
        self, event_type: str, callback: Callable[[Any], Awaitable[None]]
    ) -> None:
        """Register callback for batch coordination events."""
        self._event_callbacks[event_type] = callback

    async def register_batch(self, event: BatchEssaysRegistered) -> None:
        """
        Register batch expectations from BOS.

        Args:
            event: BatchEssaysRegistered event from BOS
        """
        batch_id = event.batch_id

        if batch_id in self.batch_expectations:
            logger.warning(f"Batch {batch_id} already registered, overwriting")

        expectation = BatchExpectation(
            batch_id=batch_id,
            expected_count=event.expected_essay_count,
            essay_ids=event.essay_ids,
        )

        self.batch_expectations[batch_id] = expectation

        # Start timeout monitoring
        await self._start_timeout_monitoring(expectation)

        logger.info(
            f"Registered batch {batch_id} expecting {event.expected_essay_count} essays: "
            f"{event.essay_ids}"
        )

    async def mark_essay_ready(self, event: EssayContentReady) -> BatchEssaysReady | None:
        """
        Mark essay as ready and check if batch is complete.

        Args:
            event: EssayContentReady event from File Service

        Returns:
            BatchEssaysReady event if batch is complete, None otherwise
        """
        batch_id = event.batch_id
        essay_id = event.essay_id

        if batch_id not in self.batch_expectations:
            logger.error(f"No expectation registered for batch {batch_id}")
            return None

        expectation = self.batch_expectations[batch_id]

        if expectation.mark_essay_ready(essay_id):
            # Batch is complete!
            logger.info(
                f"Batch {batch_id} is complete with {len(expectation.ready_essay_ids)} essays"
            )

            # Cancel timeout monitoring
            if expectation._timeout_task:
                expectation._timeout_task.cancel()

            # Create completion event
            # TODO: This is a temporary implementation for Phase 1 - will be updated in Phase 4
            # to properly populate EssayProcessingInputRefV1 objects with text_storage_id
            from common_core.metadata_models import EssayProcessingInputRefV1
            ready_essays = [
                EssayProcessingInputRefV1(
                    essay_id=essay_id,
                    text_storage_id=f"TODO-storage-{essay_id}",  # Will be properly mapped in Phase 4
                    student_name=None
                )
                for essay_id in expectation.ready_essay_ids
            ]

            batch_ready_event = BatchEssaysReady(
                batch_id=batch_id,
                ready_essays=ready_essays,
                batch_entity=EntityReference(
                    entity_id=batch_id,
                    entity_type="batch",
                ),
                metadata=SystemProcessingMetadata(
                    entity=EntityReference(entity_id=batch_id, entity_type="batch"),
                    timestamp=datetime.utcnow(),
                    event="batch.essays.ready",
                ),
            )

            # Clean up completed batch
            del self.batch_expectations[batch_id]

            return batch_ready_event

        return None

    async def _start_timeout_monitoring(self, expectation: BatchExpectation) -> None:
        """Start timeout monitoring for a batch expectation."""

        async def timeout_monitor() -> None:
            await asyncio.sleep(expectation.timeout_seconds)

            # Check if batch is still pending
            if expectation.batch_id in self.batch_expectations:
                logger.warning(
                    f"Batch {expectation.batch_id} timed out. "
                    f"Ready: {len(expectation.ready_essay_ids)}/{expectation.expected_count}"
                )

                # Create timeout event
                timeout_event = BatchReadinessTimeout(
                    batch_id=expectation.batch_id,
                    ready_essay_ids=list(expectation.ready_essay_ids),
                    missing_essay_ids=expectation.missing_essay_ids,
                    expected_count=expectation.expected_count,
                    actual_count=len(expectation.ready_essay_ids),
                    timeout_duration_seconds=expectation.timeout_seconds,
                    metadata=SystemProcessingMetadata(
                        entity=EntityReference(entity_id=expectation.batch_id, entity_type="batch"),
                        timestamp=datetime.utcnow(),
                        event="batch.readiness.timeout",
                    ),
                )

                # Emit timeout event if callback registered
                if "batch.readiness.timeout" in self._event_callbacks:
                    await self._event_callbacks["batch.readiness.timeout"](timeout_event)

                # Clean up timed out batch
                del self.batch_expectations[expectation.batch_id]

        expectation._timeout_task = asyncio.create_task(timeout_monitor())

    def get_batch_status(self, batch_id: str) -> dict[str, Any] | None:
        """Get current status of a batch."""
        if batch_id not in self.batch_expectations:
            return None

        expectation = self.batch_expectations[batch_id]
        return {
            "batch_id": batch_id,
            "expected_count": expectation.expected_count,
            "ready_count": len(expectation.ready_essay_ids),
            "ready_essay_ids": list(expectation.ready_essay_ids),
            "missing_essay_ids": expectation.missing_essay_ids,
            "is_complete": expectation.is_complete,
            "is_timeout_due": expectation.is_timeout_due,
            "created_at": expectation.created_at,
        }

    def list_active_batches(self) -> list[str]:
        """Get list of currently tracked batch IDs."""
        return list(self.batch_expectations.keys())
