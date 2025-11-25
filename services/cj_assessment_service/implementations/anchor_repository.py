"""Anchor repository implementation for CJ Assessment Service."""

from __future__ import annotations

from huleedu_service_libs.logging_utils import create_service_logger
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from services.cj_assessment_service.models_db import AnchorEssayReference
from services.cj_assessment_service.protocols import AnchorRepositoryProtocol

logger = create_service_logger("cj_assessment_service.repositories.anchor")


class PostgreSQLAnchorRepository(AnchorRepositoryProtocol):
    """PostgreSQL implementation for anchor essay references."""

    async def upsert_anchor_reference(
        self,
        session: AsyncSession,
        *,
        assignment_id: str,
        anchor_label: str,
        grade: str,
        grade_scale: str,
        text_storage_id: str,
    ) -> int:
        """Create/update an anchor for an assignment/anchor-label/scale triple."""
        stmt = insert(AnchorEssayReference).values(
            assignment_id=assignment_id,
            anchor_label=anchor_label,
            grade=grade,
            grade_scale=grade_scale,
            text_storage_id=text_storage_id,
        )

        stmt = stmt.on_conflict_do_update(  # type: ignore[assignment]
            index_elements=["assignment_id", "anchor_label", "grade_scale"],
            set_={"text_storage_id": text_storage_id, "grade": grade},
        ).returning(AnchorEssayReference.id)

        result = await session.execute(stmt)
        anchor_id = result.scalar_one()
        return int(anchor_id)

    async def get_anchor_essay_references(
        self,
        session: AsyncSession,
        assignment_id: str,
        grade_scale: str | None = None,
    ) -> list[AnchorEssayReference]:
        """Get anchor essay references for an assignment."""
        stmt = select(AnchorEssayReference).where(
            AnchorEssayReference.assignment_id == assignment_id
        )

        if grade_scale:
            stmt = stmt.where(AnchorEssayReference.grade_scale == grade_scale)

        result = await session.execute(stmt)
        return list(result.scalars().all())
