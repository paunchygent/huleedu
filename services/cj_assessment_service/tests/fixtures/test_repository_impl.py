"""
Test-specific repository implementation for CJ Assessment Service.

Uses SQLite-compatible models and operations for testing.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from services.cj_assessment_service.enums_db import CJBatchStatusEnum
from services.cj_assessment_service.models_api import ComparisonResult
from services.cj_assessment_service.protocols import CJRepositoryProtocol
from services.cj_assessment_service.tests.fixtures.test_models_db import (
    TestBase,
    TestCJBatchUpload,
    TestComparisonPair,
    TestProcessedEssay,
)


class TestCJRepositoryImpl(CJRepositoryProtocol):
    """Test repository implementation using SQLite-compatible models."""

    def __init__(self, session_maker: Any) -> None:
        """Initialize with session maker."""
        self.session_maker = session_maker

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        """Context manager for database sessions."""
        session = self.session_maker()
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

    async def initialize_db_schema(self) -> None:
        """Create database tables if they don't exist."""
        # This is handled by the fixture

    async def create_new_cj_batch(
        self,
        session: AsyncSession,
        bos_batch_id: str,
        event_correlation_id: str,
        language: str,
        course_code: str,
        essay_instructions: str,
        initial_status: CJBatchStatusEnum,
        expected_essay_count: int,
    ) -> TestCJBatchUpload:
        """Create a new CJ assessment batch."""
        cj_batch = TestCJBatchUpload(
            bos_batch_id=bos_batch_id,
            event_correlation_id=event_correlation_id,
            language=language,
            course_code=course_code,
            essay_instructions=essay_instructions,
            status=initial_status,
            expected_essay_count=expected_essay_count,
            processing_metadata={},
        )
        session.add(cj_batch)
        await session.flush()
        return cj_batch

    async def create_or_update_cj_processed_essay(
        self,
        session: AsyncSession,
        cj_batch_id: int,
        els_essay_id: str,
        text_storage_id: str,
        assessment_input_text: str,
    ) -> TestProcessedEssay:
        """Create or update a processed essay in CJ batch."""
        # Check if essay already exists
        existing_essay = await session.get(TestProcessedEssay, els_essay_id)

        if existing_essay:
            # Update existing essay
            existing_essay.cj_batch_id = cj_batch_id
            existing_essay.text_storage_id = text_storage_id
            existing_essay.assessment_input_text = assessment_input_text
            await session.flush()
            return existing_essay
        else:
            # Create new essay
            essay = TestProcessedEssay(
                els_essay_id=els_essay_id,
                cj_batch_id=cj_batch_id,
                text_storage_id=text_storage_id,
                assessment_input_text=assessment_input_text,
                processing_metadata={},
            )
            session.add(essay)
            await session.flush()
            return essay

    async def get_essays_for_cj_batch(
        self,
        session: AsyncSession,
        cj_batch_id: int,
    ) -> list[TestProcessedEssay]:
        """Get all essays for a CJ assessment batch."""
        stmt = select(TestProcessedEssay).where(TestProcessedEssay.cj_batch_id == cj_batch_id)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def get_comparison_pair_by_essays(
        self,
        session: AsyncSession,
        cj_batch_id: int,
        essay_a_els_id: str,
        essay_b_els_id: str,
    ) -> TestComparisonPair | None:
        """Get existing comparison pair between two essays in a batch."""
        stmt = select(TestComparisonPair).where(
            (TestComparisonPair.cj_batch_id == cj_batch_id)
            & (
                (
                    (TestComparisonPair.essay_a_els_id == essay_a_els_id)
                    & (TestComparisonPair.essay_b_els_id == essay_b_els_id)
                )
                | (
                    (TestComparisonPair.essay_a_els_id == essay_b_els_id)
                    & (TestComparisonPair.essay_b_els_id == essay_a_els_id)
                )
            ),
        )
        result = await session.execute(stmt)
        return result.scalars().first()

    async def store_comparison_results(
        self,
        session: AsyncSession,
        results: list[ComparisonResult],
        cj_batch_id: int,
    ) -> None:
        """Store multiple comparison results in the database."""
        for result in results:
            # Extract data from nested structure
            essay_a_id = result.task.essay_a.id
            essay_b_id = result.task.essay_b.id
            prompt_text = result.task.prompt

            # Extract LLM assessment data if available
            winner = None
            confidence = None
            justification = None
            if result.llm_assessment:
                winner = result.llm_assessment.winner
                confidence = result.llm_assessment.confidence
                justification = result.llm_assessment.justification

            # Extract error details if available
            error_code = None
            error_correlation_id = None
            error_timestamp = None
            error_service = None
            error_details = None
            if result.error_detail:
                error_code = result.error_detail.error_code
                error_correlation_id = str(result.error_detail.correlation_id)
                error_timestamp = result.error_detail.timestamp
                error_service = result.error_detail.service
                error_details = result.error_detail.details

            comparison_pair = TestComparisonPair(
                cj_batch_id=cj_batch_id,
                essay_a_els_id=essay_a_id,
                essay_b_els_id=essay_b_id,
                prompt_text=prompt_text,
                winner=winner,
                confidence=confidence,
                justification=justification,
                raw_llm_response=None,  # Can be added later if needed
                error_code=error_code,
                error_correlation_id=error_correlation_id,
                error_timestamp=error_timestamp,
                error_service=error_service,
                error_details=error_details,
                processing_metadata={},  # Can be expanded later if needed
            )
            session.add(comparison_pair)

        await session.flush()

    async def update_essay_scores_in_batch(
        self,
        session: AsyncSession,
        cj_batch_id: int,
        scores: dict[str, float],
    ) -> None:
        """Update Bradley-Terry scores for essays in a batch."""
        for els_essay_id, score in scores.items():
            stmt = (
                update(TestProcessedEssay)
                .where(
                    (TestProcessedEssay.els_essay_id == els_essay_id)
                    & (TestProcessedEssay.cj_batch_id == cj_batch_id),
                )
                .values(current_bt_score=score)
            )
            await session.execute(stmt)

        await session.flush()

    async def update_cj_batch_status(
        self,
        session: AsyncSession,
        cj_batch_id: int,
        status: CJBatchStatusEnum,
    ) -> None:
        """Update the status of a CJ assessment batch."""
        stmt = update(TestCJBatchUpload).where(TestCJBatchUpload.id == cj_batch_id).values(status=status)
        await session.execute(stmt)
        await session.flush()

    async def get_final_cj_rankings(
        self,
        session: AsyncSession,
        cj_batch_id: int,
    ) -> list[dict[str, Any]]:
        """Get final rankings for essays in a CJ batch."""
        # Get all essays with scores, ordered by score descending
        stmt = (
            select(TestProcessedEssay)
            .where(TestProcessedEssay.cj_batch_id == cj_batch_id)
            .order_by(TestProcessedEssay.current_bt_score.desc().nulls_last())
        )
        result = await session.execute(stmt)
        essays = result.scalars().all()

        # Build rankings with rank, els_essay_id, and score
        rankings = []
        for rank, essay in enumerate(essays, 1):
            rankings.append(
                {
                    "rank": rank,
                    "els_essay_id": essay.els_essay_id,
                    "score": essay.current_bt_score,
                    "comparison_count": essay.comparison_count,
                },
            )

        return rankings