"""Database access implementation for the CJ Assessment Service.

This module provides the concrete implementation of CJRepositoryProtocol,
adapted from the original prototype to work with ELS string essay IDs
and CJ assessment workflow requirements.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Optional

from common_core.models.error_models import ErrorDetail as CanonicalErrorDetail
from huleedu_service_libs.database import DatabaseMetrics, setup_database_monitoring
from huleedu_service_libs.logging_utils import create_service_logger
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.enums_db import CJBatchStatusEnum
from services.cj_assessment_service.models_api import ComparisonResult
from services.cj_assessment_service.models_db import (
    AssessmentInstruction,
    Base,
    CJBatchUpload,
    ComparisonPair,
    ProcessedEssay,
)
from services.cj_assessment_service.protocols import CJRepositoryProtocol


class PostgreSQLCJRepositoryImpl(CJRepositoryProtocol):
    """PostgreSQL implementation of CJRepositoryProtocol for CJ Assessment Service."""

    def __init__(
        self,
        settings: Settings,
        database_metrics: Optional[DatabaseMetrics] = None,
        engine: Optional[Any] = None,
    ) -> None:
        """Initialize the database handler with injected engine or connection settings."""
        self.settings = settings
        self.logger = create_service_logger("cj_assessment.repository.postgres")
        self.database_metrics = database_metrics

        # Use injected engine or create new one (for backward compatibility)
        if engine is not None:
            self.engine = engine
        else:
            # Create async engine with enhanced connection pooling (following BOS/ELS pattern)
            self.engine = create_async_engine(
                settings.DATABASE_URL,
                echo=False,
                future=True,
                pool_size=settings.DATABASE_POOL_SIZE,
                max_overflow=settings.DATABASE_MAX_OVERFLOW,
                pool_pre_ping=settings.DATABASE_POOL_PRE_PING,
                pool_recycle=settings.DATABASE_POOL_RECYCLE,
            )

        # Setup database monitoring if metrics are provided
        if self.database_metrics:
            setup_database_monitoring(
                self.engine, "cj_assessment", self.database_metrics.get_metrics()
            )
            self.logger.info("Database monitoring enabled for CJ Assessment Service")

        self.async_session_maker = async_sessionmaker(
            self.engine,
            expire_on_commit=False,
            class_=AsyncSession,
        )

    async def initialize_db_schema(self) -> None:
        """Create database tables if they don't exist."""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.logger.info("CJ Assessment Service database schema initialized")

    @staticmethod
    def _validate_instruction_scope(
        assignment_id: str | None,
        course_id: str | None,
    ) -> None:
        """Ensure exactly one of assignment_id or course_id is provided."""

        if bool(assignment_id) == bool(course_id):
            raise ValueError("Provide exactly one of assignment_id or course_id")

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
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
        event_correlation_id: str,
        language: str,
        course_code: str,
        initial_status: CJBatchStatusEnum,
        expected_essay_count: int,
        user_id: str | None = None,
        org_id: str | None = None,
    ) -> CJBatchUpload:
        """Create a new CJ assessment batch with its required state tracking."""
        from datetime import UTC, datetime

        from common_core.status_enums import CJBatchStateEnum

        from services.cj_assessment_service.models_db import CJBatchState

        # Create the batch
        cj_batch = CJBatchUpload(
            bos_batch_id=bos_batch_id,
            event_correlation_id=event_correlation_id,
            language=language,
            course_code=course_code,
            status=initial_status,
            expected_essay_count=expected_essay_count,
            processing_metadata={},
            user_id=user_id,
            org_id=org_id,
        )
        session.add(cj_batch)
        await session.flush()  # Get the batch ID

        # Create the required batch state for tracking
        # Every batch MUST have state tracking from creation
        batch_state = CJBatchState(
            batch_id=cj_batch.id,
            state=CJBatchStateEnum.INITIALIZING,
            total_comparisons=0,
            submitted_comparisons=0,
            completed_comparisons=0,
            failed_comparisons=0,
            partial_scoring_triggered=False,
            completion_threshold_pct=95,  # Default threshold
            current_iteration=0,
            last_activity_at=datetime.now(UTC),
        )
        session.add(batch_state)
        await session.flush()

        return cj_batch

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
        # Check if essay already exists
        existing_essay = await session.get(ProcessedEssay, els_essay_id)

        if existing_essay:
            # Update existing essay
            existing_essay.cj_batch_id = cj_batch_id
            existing_essay.text_storage_id = text_storage_id
            existing_essay.assessment_input_text = assessment_input_text
            existing_essay.processing_metadata = processing_metadata or {}
            await session.flush()
            return existing_essay
        else:
            # Create new essay
            essay = ProcessedEssay(
                els_essay_id=els_essay_id,
                cj_batch_id=cj_batch_id,
                text_storage_id=text_storage_id,
                assessment_input_text=assessment_input_text,
                processing_metadata=processing_metadata or {},
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
                update(ProcessedEssay)
                .where(
                    (ProcessedEssay.els_essay_id == els_essay_id)
                    & (ProcessedEssay.cj_batch_id == cj_batch_id),
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
                },
            )

        return rankings

    async def get_comparison_errors(self, cj_batch_id: str) -> list[CanonicalErrorDetail]:
        """Retrieve all error details for a CJ batch."""
        async with self.session() as session:
            result = await session.execute(
                select(ComparisonPair)
                .where(ComparisonPair.cj_batch_id == cj_batch_id)
                .where(ComparisonPair.error_code.is_not(None))
            )
            pairs = result.scalars().all()
            return [
                self._reconstruct_error_detail(pair)
                for pair in pairs
                if self._can_reconstruct_error(pair)
            ]

    def _can_reconstruct_error(self, pair: ComparisonPair) -> bool:
        """Check if a ComparisonPair has sufficient data to reconstruct an ErrorDetail."""
        return (
            pair.error_code is not None
            and pair.error_correlation_id is not None
            and pair.error_timestamp is not None
            and pair.error_service is not None
        )

    def _reconstruct_error_detail(self, pair: ComparisonPair) -> CanonicalErrorDetail:
        """Reconstruct ErrorDetail from database fields."""
        # This method should only be called after _can_reconstruct_error returns True
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
            stack_trace=None,  # Not stored in DB
            trace_id=None,  # Not stored in DB
            span_id=None,  # Not stored in DB
        )

    async def get_assessment_instruction(
        self,
        session: AsyncSession,
        assignment_id: str | None,
        course_id: str | None,
    ) -> AssessmentInstruction | None:
        """Get assessment instruction by assignment or course ID.

        Args:
            session: Database session
            assignment_id: Optional assignment ID (takes precedence)
            course_id: Optional course ID (fallback)

        Returns:
            AssessmentInstruction or None if not found
        """
        from services.cj_assessment_service.models_db import AssessmentInstruction

        if assignment_id:
            # Try assignment-specific first
            stmt = select(AssessmentInstruction).where(
                AssessmentInstruction.assignment_id == assignment_id
            )
            result = await session.execute(stmt)
            instruction = result.scalars().first()
            if instruction:
                return instruction

        if course_id:
            # Fall back to course-level
            stmt = select(AssessmentInstruction).where(
                AssessmentInstruction.course_id == course_id,
                AssessmentInstruction.assignment_id.is_(None),
            )
            result = await session.execute(stmt)
            return result.scalars().first()

        return None

    async def get_assignment_context(
        self,
        session: AsyncSession,
        assignment_id: str,
    ) -> dict[str, Any] | None:
        """Fetch assignment-level instructions and metadata for anchor workflows."""
        stmt = select(AssessmentInstruction).where(
            AssessmentInstruction.assignment_id == assignment_id
        )
        result = await session.execute(stmt)
        instruction = result.scalars().first()

        if instruction is None:
            return None

        return {
            "assignment_id": instruction.assignment_id,
            "course_id": instruction.course_id,
            "instructions_text": instruction.instructions_text,
            "grade_scale": instruction.grade_scale,
            "instruction_id": instruction.id,
        }

    async def upsert_assessment_instruction(
        self,
        session: AsyncSession,
        *,
        assignment_id: str | None,
        course_id: str | None,
        instructions_text: str,
        grade_scale: str,
        student_prompt_storage_id: str | None = None,
    ) -> AssessmentInstruction:
        """Create or update assignment-scoped assessment configuration.

        Storage-by-reference: `student_prompt_storage_id` is Content Service pointer,
        not prompt text. None on update preserves existing reference.
        """
        self._validate_instruction_scope(assignment_id, course_id)

        stmt = select(AssessmentInstruction)
        if assignment_id:
            stmt = stmt.where(AssessmentInstruction.assignment_id == assignment_id)
        else:
            stmt = stmt.where(
                AssessmentInstruction.course_id == course_id,
                AssessmentInstruction.assignment_id.is_(None),
            )

        result = await session.execute(stmt)
        instruction = result.scalars().first()

        if instruction:
            instruction.instructions_text = instructions_text
            instruction.grade_scale = grade_scale
            instruction.student_prompt_storage_id = student_prompt_storage_id
        else:
            instruction = AssessmentInstruction(
                assignment_id=assignment_id,
                course_id=course_id,
                instructions_text=instructions_text,
                grade_scale=grade_scale,
                student_prompt_storage_id=student_prompt_storage_id,
            )
            session.add(instruction)

        await session.flush()
        await session.refresh(instruction)
        return instruction

    async def list_assessment_instructions(
        self,
        session: AsyncSession,
        *,
        limit: int,
        offset: int,
        grade_scale: str | None = None,
    ) -> tuple[list[AssessmentInstruction], int]:
        """List assessment instructions with pagination and optional scale filter."""

        stmt = select(AssessmentInstruction).order_by(AssessmentInstruction.created_at.desc())
        count_stmt = select(func.count()).select_from(AssessmentInstruction)

        if grade_scale:
            stmt = stmt.where(AssessmentInstruction.grade_scale == grade_scale)
            count_stmt = count_stmt.where(AssessmentInstruction.grade_scale == grade_scale)

        stmt = stmt.offset(offset).limit(limit)

        result = await session.execute(stmt)
        items = list(result.scalars().all())

        total_result = await session.execute(count_stmt)
        total = int(total_result.scalar_one())

        return items, total

    async def delete_assessment_instruction(
        self,
        session: AsyncSession,
        *,
        assignment_id: str | None,
        course_id: str | None,
    ) -> bool:
        """Delete assessment instructions scoped by assignment or course."""

        self._validate_instruction_scope(assignment_id, course_id)

        stmt = select(AssessmentInstruction)
        if assignment_id:
            stmt = stmt.where(AssessmentInstruction.assignment_id == assignment_id)
        else:
            stmt = stmt.where(
                AssessmentInstruction.course_id == course_id,
                AssessmentInstruction.assignment_id.is_(None),
            )

        result = await session.execute(stmt)
        instruction = result.scalars().first()
        if instruction is None:
            return False

        await session.delete(instruction)
        await session.flush()
        return True

    async def get_cj_batch_upload(
        self,
        session: AsyncSession,
        cj_batch_id: int,
    ) -> CJBatchUpload | None:
        """Get CJ batch upload by ID."""
        return await session.get(CJBatchUpload, cj_batch_id)

    async def get_anchor_essay_references(
        self,
        session: AsyncSession,
        assignment_id: str,
        grade_scale: str | None = None,
    ) -> list[Any]:  # list[AnchorEssayReference]
        """Get anchor essay references for an assignment.

        Args:
            session: Database session
            assignment_id: Assignment ID
            grade_scale: Optional grade scale to filter anchors

        Returns:
            List of AnchorEssayReference objects
        """
        from services.cj_assessment_service.models_db import AnchorEssayReference

        stmt = select(AnchorEssayReference).where(
            AnchorEssayReference.assignment_id == assignment_id
        )

        if grade_scale:
            stmt = stmt.where(AnchorEssayReference.grade_scale == grade_scale)

        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def store_grade_projections(
        self,
        session: AsyncSession,
        projections: list[Any],  # list[GradeProjection]
    ) -> None:
        """Store grade projections in database.

        Args:
            session: Database session
            projections: List of GradeProjection objects
        """
        if not projections:
            return

        try:
            session.add_all(projections)
            await session.flush()
            self.logger.info(f"Stored {len(projections)} grade projections")
        except Exception as e:
            self.logger.error(f"Failed to store grade projections: {e}", extra={"error": str(e)})
            # Re-raise to let caller handle
            raise


# Standalone functions for use in context_builder to avoid circular imports
async def get_assessment_instruction(
    session: AsyncSession,
    assignment_id: str | None,
    course_id: str | None,
) -> Any | None:  # AssessmentInstruction | None
    """Get assessment instruction by assignment or course ID.

    Standalone function to avoid circular imports in context_builder.

    Args:
        session: Database session
        assignment_id: Optional assignment ID (takes precedence)
        course_id: Optional course ID (fallback)

    Returns:
        AssessmentInstruction or None if not found
    """
    from services.cj_assessment_service.models_db import AssessmentInstruction

    if assignment_id:
        # Try assignment-specific first
        stmt = select(AssessmentInstruction).where(
            AssessmentInstruction.assignment_id == assignment_id
        )
        result = await session.execute(stmt)
        instruction = result.scalars().first()
        if instruction:
            return instruction

    if course_id:
        # Fall back to course-level
        stmt = select(AssessmentInstruction).where(
            AssessmentInstruction.course_id == course_id,
            AssessmentInstruction.assignment_id.is_(None),
        )
        result = await session.execute(stmt)
        return result.scalars().first()

    return None


async def get_anchor_essay_references(
    session: AsyncSession,
    assignment_id: str,
    grade_scale: str | None = None,
) -> list[Any]:  # list[AnchorEssayReference]
    """Get anchor essay references for an assignment.

    Standalone function to avoid circular imports in context_builder.

    Args:
        session: Database session
        assignment_id: Assignment ID
        grade_scale: Optional grade scale filter

    Returns:
        List of AnchorEssayReference objects
    """
    from services.cj_assessment_service.models_db import AnchorEssayReference

    stmt = select(AnchorEssayReference).where(AnchorEssayReference.assignment_id == assignment_id)

    if grade_scale:
        stmt = stmt.where(AnchorEssayReference.grade_scale == grade_scale)

    result = await session.execute(stmt)
    return list(result.scalars().all())
