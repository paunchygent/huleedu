"""Database access implementation for the CJ Assessment Service.

This module provides the concrete implementation of CJDatabaseProtocol,
adapted from the original prototype to work with ELS string essay IDs
and CJ assessment workflow requirements.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from config import Settings
from enums_db import CJBatchStatusEnum
from models_api import ComparisonResult
from models_db import Base, CJBatchUpload, ComparisonPair, ProcessedEssay
from protocols import CJDatabaseProtocol
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


class CJDatabaseImpl(CJDatabaseProtocol):
    """Implementation of CJDatabaseProtocol for CJ Assessment Service."""

    def __init__(self, settings: Settings) -> None:
        """Initialize the database handler with connection settings."""
        self.settings = settings
        self.engine = create_async_engine(
            settings.DATABASE_URL_CJ,
            echo=False,
            future=True,
        )
        self.async_session_maker = async_sessionmaker(
            self.engine,
            expire_on_commit=False,
            class_=AsyncSession,
        )

    async def initialize_db_schema(self) -> None:
        """Create database tables if they don't exist."""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    @asynccontextmanager
    async def session(self):
        """Context manager for database sessions."""
        session = self.async_session_maker()
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

    async def create_new_cj_batch(
        self,
        session: AsyncSession,
        bos_batch_id: str,
        event_correlation_id: str | None,
        language: str,
        course_code: str,
        essay_instructions: str,
        initial_status: CJBatchStatusEnum,
        expected_essay_count: int,
    ) -> CJBatchUpload:
        """Create a new CJ assessment batch."""
        cj_batch = CJBatchUpload(
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
    ) -> ProcessedEssay:
        """Create or update a processed essay in CJ batch."""
        # Check if essay already exists
        existing_essay = await session.get(ProcessedEssay, els_essay_id)

        if existing_essay:
            # Update existing essay
            existing_essay.cj_batch_id = cj_batch_id
            existing_essay.text_storage_id = text_storage_id
            existing_essay.assessment_input_text = assessment_input_text
            await session.flush()
            return existing_essay
        else:
            # Create new essay
            essay = ProcessedEssay(
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
    ) -> list[ProcessedEssay]:
        """Get all essays for a CJ assessment batch."""
        stmt = select(ProcessedEssay).where(ProcessedEssay.cj_batch_id == cj_batch_id)
        result = await session.execute(stmt)
        return list(result.scalars().all())

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
            )
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
            prompt_hash = result.prompt_hash or ""

            # Extract LLM assessment data if available
            winner = None
            confidence = None
            justification = None
            if result.llm_assessment:
                winner = result.llm_assessment.winner
                confidence = result.llm_assessment.confidence
                justification = result.llm_assessment.justification

            comparison_pair = ComparisonPair(
                cj_batch_id=cj_batch_id,
                essay_a_els_id=essay_a_id,
                essay_b_els_id=essay_b_id,
                prompt_text=prompt_text,
                prompt_hash=prompt_hash,
                winner=winner,
                confidence=confidence,
                justification=justification,
                raw_llm_response=None,  # Can be added later if needed
                error_message=result.error_message,
                from_cache=result.from_cache,
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
                update(ProcessedEssay)
                .where(
                    (ProcessedEssay.els_essay_id == els_essay_id)
                    & (ProcessedEssay.cj_batch_id == cj_batch_id)
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
        stmt = update(CJBatchUpload).where(CJBatchUpload.id == cj_batch_id).values(status=status)
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
            select(ProcessedEssay)
            .where(ProcessedEssay.cj_batch_id == cj_batch_id)
            .order_by(ProcessedEssay.current_bt_score.desc().nulls_last())
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
                }
            )

        return rankings
