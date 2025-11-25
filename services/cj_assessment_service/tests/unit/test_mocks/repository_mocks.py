"""Per-aggregate repository mocks for CJ Assessment Service unit tests.

Provides mock implementations of repository protocols for testing business logic
against each domain aggregate without requiring actual database connections.

Available Mocks:
- MockBatchRepository: CJ batch operations
- MockEssayRepository: Processed essay operations
- MockComparisonRepository: Comparison pair operations
- MockAnchorRepository: Anchor essay reference operations
- MockInstructionRepository: Assessment instruction operations
- MockGradeProjectionRepository: Grade projection operations
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from common_core.status_enums import CJBatchStateEnum
from sqlalchemy.ext.asyncio import AsyncSession

from services.cj_assessment_service.models_db import AssessmentInstruction
from services.cj_assessment_service.protocols import (
    AnchorRepositoryProtocol,
    AssessmentInstructionRepositoryProtocol,
    CJBatchRepositoryProtocol,
    CJComparisonRepositoryProtocol,
    CJEssayRepositoryProtocol,
    GradeProjectionRepositoryProtocol,
)
from services.cj_assessment_service.tests.unit.test_mocks.instruction_store import (
    AssessmentInstructionStore,
)


class MockBatchRepository(CJBatchRepositoryProtocol):
    """Mock batch repository for testing batch aggregate operations."""

    def __init__(self) -> None:
        """Initialize mock batch storage."""
        self.batches: dict[int, dict] = {}
        self.next_batch_id = 1
        self.should_fail_create_batch = False

    async def create_new_cj_batch(
        self,
        session: AsyncSession,
        bos_batch_id: str,
        event_correlation_id: str,
        language: str,
        course_code: str,
        initial_status: Any,
        expected_essay_count: int,
        user_id: str | None = None,
        org_id: str | None = None,
    ) -> Any:
        """Create a new CJ batch record."""
        if self.should_fail_create_batch:
            raise Exception("DB create batch failed")
        batch_id = self.next_batch_id
        self.next_batch_id += 1
        self.batches[batch_id] = {
            "bos_batch_id": bos_batch_id,
            "event_correlation_id": event_correlation_id,
            "language": language,
            "course_code": course_code,
            "initial_status": initial_status,
            "expected_essay_count": expected_essay_count,
            "user_id": user_id,
            "org_id": org_id,
        }

        class Batch:
            def __init__(self, batch_id_val: int, batch_data: dict) -> None:
                self.id = batch_id_val
                self.user_id = batch_data.get("user_id")
                self.org_id = batch_data.get("org_id")
                self.processing_metadata: dict[str, Any] = {}
                self.assignment_id = None

        return Batch(batch_id, self.batches[batch_id])

    async def get_cj_batch_upload(
        self,
        session: AsyncSession,
        cj_batch_id: int,
    ) -> Any | None:
        """Get CJ batch upload by ID."""
        if cj_batch_id in self.batches:

            class MockBatchUpload:
                def __init__(self, batch_id: int):
                    self.id = batch_id
                    self.assignment_id = "test-assignment-123"

            return MockBatchUpload(cj_batch_id)
        return None

    async def get_batch_state(
        self,
        session: AsyncSession,
        batch_id: int,
    ) -> Any | None:
        """Fetch batch state for a given batch."""
        return None

    async def get_batch_state_for_update(
        self,
        session: AsyncSession,
        batch_id: int,
        for_update: bool = False,
    ) -> Any | None:
        """Get batch state with optional row locking."""
        return None

    async def update_cj_batch_status(
        self,
        session: AsyncSession,
        cj_batch_id: int,
        status: Any,
    ) -> None:
        """Update the status of a CJ batch."""
        pass

    async def get_stuck_batches(
        self,
        session: AsyncSession,
        states: list[CJBatchStateEnum],
        stuck_threshold: datetime,
    ) -> list[Any]:
        """Get batches stuck in specified states beyond threshold."""
        return []

    async def get_batches_ready_for_completion(
        self,
        session: AsyncSession,
    ) -> list[Any]:
        """Get batches ready for final completion."""
        return []

    async def update_batch_state(
        self,
        session: AsyncSession,
        batch_id: int,
        state: CJBatchStateEnum,
    ) -> None:
        """Update batch state."""
        pass


class MockEssayRepository(CJEssayRepositoryProtocol):
    """Mock essay repository for testing processed essay aggregate operations."""

    def __init__(self) -> None:
        """Initialize mock essay storage."""
        self.essays: dict[int, list] = {}

    async def create_or_update_cj_processed_essay(
        self,
        session: AsyncSession,
        cj_batch_id: int,
        els_essay_id: str,
        text_storage_id: str,
        assessment_input_text: str,
        processing_metadata: dict | None = None,
    ) -> Any:
        """Create or update a processed essay record."""
        essay_data = {
            "els_essay_id": els_essay_id,
            "text_storage_id": text_storage_id,
            "assessment_input_text": assessment_input_text,
            "processing_metadata": processing_metadata or {},
        }
        self.essays.setdefault(cj_batch_id, []).append(essay_data)

        class MockProcessedEssay:
            def __init__(self) -> None:
                self.current_bt_score = 0.0
                self.els_essay_id = els_essay_id
                self.text_storage_id = text_storage_id
                self.assessment_input_text = assessment_input_text

        return MockProcessedEssay()

    async def get_essays_for_cj_batch(
        self,
        session: AsyncSession,
        cj_batch_id: int,
    ) -> list[Any]:
        """Get all essays for a CJ batch."""
        return self.essays.get(cj_batch_id, [])

    async def update_essay_scores_in_batch(
        self,
        session: AsyncSession,
        cj_batch_id: int,
        scores: dict[str, float],
    ) -> None:
        """Update essay scores within a batch."""
        pass

    async def get_final_cj_rankings(
        self,
        session: AsyncSession,
        cj_batch_id: int,
    ) -> list[dict[str, Any]]:
        """Get the final ranked list of essays for a CJ batch."""
        return []


class MockComparisonRepository(CJComparisonRepositoryProtocol):
    """Mock comparison repository for testing comparison pair operations."""

    def __init__(self) -> None:
        """Initialize mock comparison pair storage."""
        self.comparison_pairs: dict[int, list] = {}

    async def get_comparison_pair_by_essays(
        self,
        session: AsyncSession,
        cj_batch_id: int,
        essay_a_els_id: str,
        essay_b_els_id: str,
    ) -> Any | None:
        """Check if comparison pair already exists."""
        return None

    async def get_comparison_pair_by_correlation_id(
        self,
        session: AsyncSession,
        correlation_id: Any,
    ) -> Any | None:
        """Retrieve comparison pair by correlation ID."""
        for pairs in self.comparison_pairs.values():
            for pair in pairs:
                if getattr(pair, "request_correlation_id", None) == correlation_id:
                    return pair
        return None

    async def store_comparison_results(
        self,
        session: AsyncSession,
        results: list[Any],
        cj_batch_id: int,
    ) -> None:
        """Store comparison results to database."""
        pass

    async def get_comparison_pairs_for_batch(
        self,
        session: AsyncSession,
        batch_id: int,
    ) -> list[tuple[str, str]]:
        """Get comparison pairs for batch (pair generation)."""
        pairs = self.comparison_pairs.get(batch_id, [])
        return [(p.essay_a_els_id, p.essay_b_els_id) for p in pairs]

    async def get_valid_comparisons_for_batch(
        self,
        session: AsyncSession,
        batch_id: int,
    ) -> list[Any]:
        """Get valid comparisons for batch (scoring)."""
        pairs = self.comparison_pairs.get(batch_id, [])
        return [p for p in pairs if p.winner and p.winner != "error"]


class MockAnchorRepository(AnchorRepositoryProtocol):
    """Mock anchor repository for testing anchor essay reference operations."""

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
        """Create or update anchor reference."""
        return 1

    async def get_anchor_essay_references(
        self,
        session: AsyncSession,
        assignment_id: str,
        grade_scale: str | None = None,
    ) -> list[Any]:
        """Get anchor essay references for an assignment."""
        return []


class MockInstructionRepository(AssessmentInstructionRepositoryProtocol):
    """Mock instruction repository for testing assessment instruction operations."""

    def __init__(self) -> None:
        """Initialize mock instruction storage."""
        self._instruction_store = AssessmentInstructionStore()

    async def get_assessment_instruction(
        self,
        session: AsyncSession,
        assignment_id: str | None,
        course_id: str | None,
    ) -> AssessmentInstruction | None:
        """Get assessment instruction by assignment or course ID."""
        return self._instruction_store.get(assignment_id=assignment_id, course_id=course_id)

    async def get_assignment_context(
        self,
        session: AsyncSession,
        assignment_id: str,
    ) -> dict[str, Any] | None:
        """Return simplified assignment context for tests."""
        return {
            "assignment_id": assignment_id,
            "instructions_text": "Mock instructions",
            "grade_scale": "swedish_8_anchor",
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
        judge_rubric_storage_id: str | None = None,
    ) -> AssessmentInstruction:
        """Create or update assessment instruction."""
        return self._instruction_store.upsert(
            assignment_id=assignment_id,
            course_id=course_id,
            instructions_text=instructions_text,
            grade_scale=grade_scale,
            student_prompt_storage_id=student_prompt_storage_id,
            judge_rubric_storage_id=judge_rubric_storage_id,
        )

    async def list_assessment_instructions(
        self,
        session: AsyncSession,
        *,
        limit: int,
        offset: int,
        grade_scale: str | None = None,
    ) -> tuple[list[AssessmentInstruction], int]:
        """List assessment instructions with pagination support."""
        return self._instruction_store.list(
            limit=limit,
            offset=offset,
            grade_scale=grade_scale,
        )

    async def delete_assessment_instruction(
        self,
        session: AsyncSession,
        *,
        assignment_id: str | None,
        course_id: str | None,
    ) -> bool:
        """Delete assessment instruction."""
        return self._instruction_store.delete(
            assignment_id=assignment_id,
            course_id=course_id,
        )


class MockGradeProjectionRepository(GradeProjectionRepositoryProtocol):
    """Mock grade projection repository for testing grade projection operations."""

    async def store_grade_projections(
        self,
        session: AsyncSession,
        projections: list[Any],
    ) -> None:
        """Store grade projections in database."""
        pass
