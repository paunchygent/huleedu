"""Comparison repository implementation for CJ Assessment Service."""

from __future__ import annotations

from uuid import UUID

from common_core.models.error_models import ErrorDetail as CanonicalErrorDetail
from huleedu_service_libs.logging_utils import create_service_logger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from services.cj_assessment_service.models_api import ComparisonResult
from services.cj_assessment_service.models_db import ComparisonPair, ProcessedEssay
from services.cj_assessment_service.protocols import CJComparisonRepositoryProtocol

logger = create_service_logger("cj_assessment_service.repositories.comparison")


class PostgreSQLCJComparisonRepository(CJComparisonRepositoryProtocol):
    """PostgreSQL implementation for comparison persistence."""

    async def get_comparison_pair_by_essays(
        self,
        session: AsyncSession,
        cj_batch_id: int,
        essay_a_els_id: str,
        essay_b_els_id: str,
    ) -> ComparisonPair | None:
        """Get existing comparison pair between two essays in a batch."""
        stmt = select(ComparisonPair).where(
            (ComparisonPair.cj_batch_id == cj_batch_id)
            & (
                (
                    (ComparisonPair.essay_a_els_id == essay_a_els_id)
                    & (ComparisonPair.essay_b_els_id == essay_b_els_id)
                )
                | (
                    (ComparisonPair.essay_a_els_id == essay_b_els_id)
                    & (ComparisonPair.essay_b_els_id == essay_a_els_id)
                )
            ),
        )
        result = await session.execute(stmt)
        return result.scalars().first()

    async def get_comparison_pair_by_correlation_id(
        self,
        session: AsyncSession,
        correlation_id: UUID,
    ) -> ComparisonPair | None:
        """Retrieve a comparison pair by its callback correlation ID."""
        stmt = select(ComparisonPair).where(ComparisonPair.request_correlation_id == correlation_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def store_comparison_results(
        self,
        session: AsyncSession,
        results: list[ComparisonResult],
        cj_batch_id: int,
    ) -> None:
        """Store multiple comparison results in the database."""
        for result in results:
            essay_a_id = result.task.essay_a.id
            essay_b_id = result.task.essay_b.id
            prompt_text = result.task.prompt

            winner = None
            confidence = None
            justification = None
            if result.llm_assessment:
                winner = result.llm_assessment.winner
                confidence = result.llm_assessment.confidence
                justification = result.llm_assessment.justification

            error_code = None
            error_correlation_id = None
            error_timestamp = None
            error_service = None
            error_details = None
            if result.error_detail:
                error_code = result.error_detail.error_code
                error_correlation_id = result.error_detail.correlation_id
                error_timestamp = result.error_detail.timestamp
                error_service = result.error_detail.service
                error_details = result.error_detail.details

            comparison_pair = ComparisonPair(
                cj_batch_id=cj_batch_id,
                essay_a_els_id=essay_a_id,
                essay_b_els_id=essay_b_id,
                prompt_text=prompt_text,
                winner=winner,
                confidence=confidence,
                justification=justification,
                raw_llm_response=None,
                error_code=error_code,
                error_correlation_id=error_correlation_id,
                error_timestamp=error_timestamp,
                error_service=error_service,
                error_details=error_details,
                processing_metadata={},
            )
            session.add(comparison_pair)

        await session.flush()

    @staticmethod
    def _can_reconstruct_error(pair: ComparisonPair) -> bool:
        return (
            pair.error_code is not None
            and pair.error_correlation_id is not None
            and pair.error_timestamp is not None
            and pair.error_service is not None
        )

    @staticmethod
    def _reconstruct_error_detail(pair: ComparisonPair) -> CanonicalErrorDetail:
        assert pair.error_code is not None
        assert pair.error_correlation_id is not None
        assert pair.error_timestamp is not None
        assert pair.error_service is not None

        return CanonicalErrorDetail(
            error_code=pair.error_code,
            message=pair.error_details.get("message", "") if pair.error_details else "",
            correlation_id=pair.error_correlation_id,
            timestamp=pair.error_timestamp,
            service=pair.error_service,
            operation=(
                pair.error_details.get("operation", "unknown") if pair.error_details else "unknown"
            ),
            details=pair.error_details or {},
            stack_trace=None,
            trace_id=None,
            span_id=None,
        )

    async def get_comparison_pairs_for_batch(
        self,
        session: AsyncSession,
        batch_id: int,
    ) -> list[tuple[str, str]]:
        """Get all comparison pair IDs (essay_a_id, essay_b_id) for a batch.

        Args:
            session: Database session
            batch_id: CJ batch identifier

        Returns:
            List of tuples containing (essay_a_els_id, essay_b_els_id)
        """
        stmt = select(
            ComparisonPair.essay_a_els_id,
            ComparisonPair.essay_b_els_id,
        ).where(ComparisonPair.cj_batch_id == batch_id)
        result = await session.execute(stmt)
        return [(row[0], row[1]) for row in result.all()]

    async def get_valid_comparisons_for_batch(
        self,
        session: AsyncSession,
        batch_id: int,
    ) -> list[ComparisonPair]:
        """Get all valid (non-error) comparison pairs for a batch.

        Args:
            session: Database session
            batch_id: CJ batch identifier

        Returns:
            List of ComparisonPair records without errors
        """
        stmt = select(ComparisonPair).where(
            ComparisonPair.cj_batch_id == batch_id,
            ComparisonPair.error_code.is_(None),
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def get_coverage_metrics_for_batch(
        self,
        session: AsyncSession,
        batch_id: int,
    ) -> tuple[int, int]:
        """Return (max_possible_pairs, successful_pairs_count) for the batch.

        max_possible_pairs:
            n-choose-2 over all ProcessedEssay nodes participating in this batch,
            including anchors.

        successful_pairs_count:
            Number of unordered essay pairs with at least one successful comparison
            (winner in {"essay_a", "essay_b"}) and no error_code set.
        """
        # Count distinct essays in the CJ graph for this batch.
        stmt_n = select(func.count(func.distinct(ProcessedEssay.els_essay_id))).where(
            ProcessedEssay.cj_batch_id == batch_id,
        )
        n_raw = await session.execute(stmt_n)
        n_val = n_raw.scalar_one()
        n = int(n_val or 0)
        max_possible_pairs = (n * (n - 1)) // 2 if n > 1 else 0

        # Build a subquery of normalized successful pairs to avoid double counting.
        normalized_a = func.least(ComparisonPair.essay_a_els_id, ComparisonPair.essay_b_els_id)
        normalized_b = func.greatest(ComparisonPair.essay_a_els_id, ComparisonPair.essay_b_els_id)

        successful_pairs_subq = (
            select(
                normalized_a.label("essay_a_els_id"),
                normalized_b.label("essay_b_els_id"),
            )
            .where(
                ComparisonPair.cj_batch_id == batch_id,
                ComparisonPair.error_code.is_(None),
                ComparisonPair.winner.in_(("essay_a", "essay_b")),
            )
            .distinct()
            .subquery()
        )

        stmt_success = select(func.count()).select_from(successful_pairs_subq)
        success_raw = await session.execute(stmt_success)
        success_val = success_raw.scalar_one()
        successful_pairs_count = int(success_val or 0)

        logger.debug(
            "Computed coverage metrics for batch",
            extra={
                "cj_batch_id": batch_id,
                "essay_count": n,
                "max_possible_pairs": max_possible_pairs,
                "successful_pairs_count": successful_pairs_count,
            },
        )

        return max_possible_pairs, successful_pairs_count
