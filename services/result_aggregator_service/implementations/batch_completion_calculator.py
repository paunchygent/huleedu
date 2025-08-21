"""Calculates batch completion and statistics for Result Aggregator Service."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from common_core.events.result_events import PhaseResultSummary
from common_core.status_enums import BatchStatus, ProcessingStage
from huleedu_service_libs.logging_utils import create_service_logger

if TYPE_CHECKING:
    from services.result_aggregator_service.protocols import BatchRepositoryProtocol

logger = create_service_logger("result_aggregator.completion_calculator")


class BatchCompletionCalculator:
    """Calculates batch completion status and phase statistics."""

    def __init__(self, batch_repository: "BatchRepositoryProtocol"):
        """Initialize with batch repository."""
        self.batch_repository = batch_repository

    async def check_batch_completion(self, batch_id: str) -> bool:
        """Check if all phases are complete for a batch."""
        batch = await self.batch_repository.get_batch(batch_id)
        if not batch:
            return False

        # Check if all essays have been processed for both phases
        essays = await self.batch_repository.get_batch_essays(batch_id)
        if not essays:
            return False

        # Check spellcheck phase
        spellcheck_complete = all(
            essay.spellcheck_status in [ProcessingStage.COMPLETED, ProcessingStage.FAILED]
            for essay in essays
        )

        # Check CJ assessment phase
        cj_complete = all(
            essay.cj_assessment_status in [ProcessingStage.COMPLETED, ProcessingStage.FAILED]
            for essay in essays
        )

        # Both phases must be complete
        return spellcheck_complete and cj_complete

    async def calculate_phase_results(self, batch_id: str) -> dict[str, PhaseResultSummary]:
        """Calculate phase result summaries for a batch."""
        essays = await self.batch_repository.get_batch_essays(batch_id)

        # Calculate spellcheck phase results
        spellcheck_completed = sum(
            1 for e in essays if e.spellcheck_status == ProcessingStage.COMPLETED
        )
        spellcheck_failed = sum(1 for e in essays if e.spellcheck_status == ProcessingStage.FAILED)

        # Calculate CJ assessment phase results
        cj_completed = sum(1 for e in essays if e.cj_assessment_status == ProcessingStage.COMPLETED)
        cj_failed = sum(1 for e in essays if e.cj_assessment_status == ProcessingStage.FAILED)

        # Calculate processing times if available
        spellcheck_times = [e.spellcheck_completed_at for e in essays if e.spellcheck_completed_at]
        spellcheck_duration = None
        if spellcheck_times:
            batch = await self.batch_repository.get_batch(batch_id)
            if batch and batch.processing_started_at:
                # Normalize timestamps to timezone-naive for arithmetic safety
                normalized_times = [
                    t.replace(tzinfo=None) if getattr(t, "tzinfo", None) is not None else t
                    for t in spellcheck_times
                ]
                start_time = (
                    batch.processing_started_at.replace(tzinfo=None)
                    if getattr(batch.processing_started_at, "tzinfo", None) is not None
                    else batch.processing_started_at
                )
                spellcheck_duration = (max(normalized_times) - start_time).total_seconds()

        cj_times = [e.cj_assessment_completed_at for e in essays if e.cj_assessment_completed_at]
        cj_duration = None
        if cj_times:
            batch = await self.batch_repository.get_batch(batch_id)
            if batch and batch.processing_started_at:
                # Normalize timestamps to timezone-naive for arithmetic safety
                normalized_times = [
                    t.replace(tzinfo=None) if getattr(t, "tzinfo", None) is not None else t
                    for t in cj_times
                ]
                start_time = (
                    batch.processing_started_at.replace(tzinfo=None)
                    if getattr(batch.processing_started_at, "tzinfo", None) is not None
                    else batch.processing_started_at
                )
                cj_duration = (max(normalized_times) - start_time).total_seconds()

        return {
            "spellcheck": PhaseResultSummary(
                phase_name="spellcheck",
                status="completed" if spellcheck_failed == 0 else "completed_with_failures",
                completed_count=spellcheck_completed,
                failed_count=spellcheck_failed,
                processing_time_seconds=spellcheck_duration,
            ),
            "cj_assessment": PhaseResultSummary(
                phase_name="cj_assessment",
                status="completed" if cj_failed == 0 else "completed_with_failures",
                completed_count=cj_completed,
                failed_count=cj_failed,
                processing_time_seconds=cj_duration,
            ),
        }

    def determine_overall_status(self, phase_results: dict[str, PhaseResultSummary]) -> BatchStatus:
        """Determine overall batch status from phase results."""
        has_failures = any(phase.failed_count > 0 for phase in phase_results.values())

        if has_failures:
            return BatchStatus.COMPLETED_WITH_FAILURES
        return BatchStatus.COMPLETED_SUCCESSFULLY

    async def calculate_duration(self, batch_id: str) -> float:
        """Calculate total processing duration for a batch."""
        batch = await self.batch_repository.get_batch(batch_id)
        if not batch or not batch.processing_started_at:
            return 0.0

        # Use completed_at if available, otherwise use current time
        # Both timestamps should be timezone-naive for consistency with database storage
        end_time = batch.processing_completed_at or datetime.now(timezone.utc).replace(tzinfo=None)
        duration = (end_time - batch.processing_started_at).total_seconds()
        return max(0.0, duration)  # Ensure non-negative
