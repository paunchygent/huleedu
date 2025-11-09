"""Test helper for managing in-memory assessment instructions."""

from __future__ import annotations

from datetime import UTC, datetime

from services.cj_assessment_service.models_db import AssessmentInstruction


class AssessmentInstructionStore:
    """Utility that mimics repository CRUD operations for instructions."""

    def __init__(self) -> None:
        self._records: dict[str, AssessmentInstruction] = {}
        self._sequence = 1

    def _scope_key(self, assignment_id: str | None, course_id: str | None) -> str:
        if bool(assignment_id) == bool(course_id):
            raise ValueError("Provide exactly one of assignment_id or course_id")
        if assignment_id:
            return f"assignment:{assignment_id}"
        assert course_id is not None  # for type checkers
        return f"course:{course_id}"

    def _build_instruction(
        self,
        *,
        assignment_id: str | None,
        course_id: str | None,
        instructions_text: str,
        grade_scale: str,
        created_at: datetime | None = None,
    ) -> AssessmentInstruction:
        record = AssessmentInstruction()
        record.id = self._sequence
        self._sequence += 1
        record.assignment_id = assignment_id
        record.course_id = course_id
        record.instructions_text = instructions_text
        record.grade_scale = grade_scale
        record.created_at = created_at or datetime.now(UTC)
        return record

    def upsert(
        self,
        *,
        assignment_id: str | None,
        course_id: str | None,
        instructions_text: str,
        grade_scale: str,
        created_at: datetime | None = None,
    ) -> AssessmentInstruction:
        """Create or update an instruction record."""
        key = self._scope_key(assignment_id, course_id)
        existing = self._records.get(key)
        if existing is None:
            record = self._build_instruction(
                assignment_id=assignment_id,
                course_id=course_id,
                instructions_text=instructions_text,
                grade_scale=grade_scale,
                created_at=created_at,
            )
            self._records[key] = record
            return record

        existing.instructions_text = instructions_text
        existing.grade_scale = grade_scale
        return existing

    def get(
        self,
        *,
        assignment_id: str | None,
        course_id: str | None,
    ) -> AssessmentInstruction | None:
        """Fetch a specific instruction by assignment or course scope."""
        key = self._scope_key(assignment_id, course_id)
        return self._records.get(key)

    def list(
        self,
        *,
        limit: int,
        offset: int,
        grade_scale: str | None = None,
    ) -> tuple[list[AssessmentInstruction], int]:
        """Return paginated instructions, filtered by grade scale when provided."""
        items = list(self._records.values())
        if grade_scale:
            items = [record for record in items if record.grade_scale == grade_scale]

        items.sort(key=lambda record: record.created_at, reverse=True)
        total = len(items)
        window = items[offset : offset + limit]
        return window, total

    def delete(self, *, assignment_id: str | None, course_id: str | None) -> bool:
        """Delete a record scoped to assignment or course."""
        key = self._scope_key(assignment_id, course_id)
        return self._records.pop(key, None) is not None
