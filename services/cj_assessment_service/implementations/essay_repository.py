"""Essay aggregate repository implementation for CJ Assessment Service."""

from __future__ import annotations

from typing import Any

from huleedu_service_libs.logging_utils import create_service_logger
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from services.cj_assessment_service.models_db import ProcessedEssay
from services.cj_assessment_service.protocols import CJEssayRepositoryProtocol

logger = create_service_logger("cj_assessment_service.repositories.essay")


class PostgreSQLCJEssayRepository(CJEssayRepositoryProtocol):
    """PostgreSQL implementation for processed essay persistence."""

    async def create_or_update_cj_processed_essay(
        self,
        session: AsyncSession,
        cj_batch_id: int,
        els_essay_id: str,
        text_storage_id: str,
        assessment_input_text: str,
        processing_metadata: dict | None = None,
    ) -> ProcessedEssay:
        """Create or update a processed essay in CJ batch."""
        metadata = processing_metadata or {}
        anchor_flag: bool | None = None
        if "is_anchor" in metadata:
            anchor_flag = bool(metadata["is_anchor"])

        existing_essay = await session.get(ProcessedEssay, els_essay_id)
        if existing_essay:
            existing_essay.cj_batch_id = cj_batch_id
            existing_essay.text_storage_id = text_storage_id
            existing_essay.assessment_input_text = assessment_input_text
            if metadata:
                existing = existing_essay.processing_metadata or {}
                existing_essay.processing_metadata = {**existing, **metadata}
            if anchor_flag is not None:
                existing_essay.is_anchor = anchor_flag
            await session.flush()
            return existing_essay

        essay_kwargs: dict[str, Any] = {
            "els_essay_id": els_essay_id,
            "cj_batch_id": cj_batch_id,
            "text_storage_id": text_storage_id,
            "assessment_input_text": assessment_input_text,
        }
        if metadata:
            essay_kwargs["processing_metadata"] = metadata
        if anchor_flag is not None:
            essay_kwargs["is_anchor"] = anchor_flag

        essay = ProcessedEssay(**essay_kwargs)
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
                    & (ProcessedEssay.cj_batch_id == cj_batch_id),
                )
                .values(current_bt_score=score)
            )
            await session.execute(stmt)

        await session.flush()

    async def get_final_cj_rankings(
        self,
        session: AsyncSession,
        cj_batch_id: int,
    ) -> list[dict[str, Any]]:
        """Get final rankings for essays in a CJ batch."""
        stmt = (
            select(ProcessedEssay)
            .where(ProcessedEssay.cj_batch_id == cj_batch_id)
            .order_by(ProcessedEssay.current_bt_score.desc().nulls_last())
        )
        result = await session.execute(stmt)
        essays = result.scalars().all()

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
