"""Assessment instruction repository implementation for CJ Assessment Service."""

from __future__ import annotations

from typing import Any

from huleedu_service_libs.logging_utils import create_service_logger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from services.cj_assessment_service.models_db import AssessmentInstruction
from services.cj_assessment_service.protocols import AssessmentInstructionRepositoryProtocol

logger = create_service_logger("cj_assessment_service.repositories.assessment_instruction")


class PostgreSQLAssessmentInstructionRepository(AssessmentInstructionRepositoryProtocol):
    """PostgreSQL implementation for assessment instruction persistence."""

    async def get_assessment_instruction(
        self,
        session: AsyncSession,
        assignment_id: str | None,
        course_id: str | None,
    ) -> AssessmentInstruction | None:
        """Get assessment instruction by assignment or course ID."""
        if assignment_id:
            stmt = select(AssessmentInstruction).where(
                AssessmentInstruction.assignment_id == assignment_id
            )
            result = await session.execute(stmt)
            instruction = result.scalars().first()
            if instruction:
                return instruction

        if course_id:
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
            "context_origin": instruction.context_origin,
            "instruction_id": instruction.id,
            "student_prompt_storage_id": instruction.student_prompt_storage_id,
            "judge_rubric_storage_id": instruction.judge_rubric_storage_id,
        }

    async def upsert_assessment_instruction(
        self,
        session: AsyncSession,
        *,
        assignment_id: str | None,
        course_id: str | None,
        instructions_text: str,
        grade_scale: str,
        context_origin: str = "research_experiment",
        student_prompt_storage_id: str | None = None,
        judge_rubric_storage_id: str | None = None,
    ) -> AssessmentInstruction:
        """Create or update assignment-scoped assessment configuration."""
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
            if instruction.grade_scale != grade_scale:
                raise ValueError(
                    "grade_scale is immutable once assessment instructions exist for a scope"
                )
            if instruction.context_origin != context_origin:
                raise ValueError(
                    "context_origin is immutable once assessment instructions exist for a scope"
                )

            instruction.instructions_text = instructions_text
            if student_prompt_storage_id is not None:
                instruction.student_prompt_storage_id = student_prompt_storage_id
            if judge_rubric_storage_id is not None:
                instruction.judge_rubric_storage_id = judge_rubric_storage_id
        else:
            instruction = AssessmentInstruction(
                assignment_id=assignment_id,
                course_id=course_id,
                instructions_text=instructions_text,
                grade_scale=grade_scale,
                context_origin=context_origin,
                student_prompt_storage_id=student_prompt_storage_id,
                judge_rubric_storage_id=judge_rubric_storage_id,
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

    @staticmethod
    def _validate_instruction_scope(assignment_id: str | None, course_id: str | None) -> None:
        if bool(assignment_id) == bool(course_id):
            raise ValueError("Provide exactly one of assignment_id or course_id")
