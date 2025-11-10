"""Shared test helpers and mocks for anchor management API testing.

This module provides reusable mock implementations and fixtures for testing
the anchor management API endpoints across multiple test files.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncContextManager, AsyncIterator, Sequence
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from services.cj_assessment_service.models_db import AnchorEssayReference, AssessmentInstruction
from services.cj_assessment_service.protocols import CJRepositoryProtocol, ContentClientProtocol
from services.cj_assessment_service.tests.unit.instruction_store import AssessmentInstructionStore


class MockContentClient(ContentClientProtocol):
    """Mock implementation of ContentClientProtocol for testing."""

    def __init__(self, behavior: str = "success", storage_id: str = "content-test-123") -> None:
        """Initialize mock with configurable behavior.

        Args:
            behavior: "success" for normal operation, "failure" to raise exception
            storage_id: Storage ID to return on successful store operation
        """
        self.behavior = behavior
        self.storage_id = storage_id
        self.call_count = 0
        self.last_call_params: dict[str, Any] = {}

    async def store_content(self, content: str, content_type: str = "text/plain") -> dict[str, str]:
        """Mock content storage operation."""
        self.call_count += 1
        self.last_call_params = {
            "content": content,
            "content_type": content_type,
        }

        if self.behavior == "failure":
            raise RuntimeError("Content storage failed")

        return {"content_id": self.storage_id}

    async def fetch_content(self, storage_id: str, correlation_id: UUID) -> str:
        """Mock content retrieval operation."""
        return "Mock essay content"


class MockSessionManager:
    """Proper async context manager for mock database sessions."""

    def __init__(self, repository: "MockCJRepository") -> None:
        """Initialize with repository reference."""
        self.repository = repository

    async def __aenter__(self) -> AsyncSession:
        """Enter session context."""
        self.repository.session_context_calls += 1
        return MockAsyncSession(self.repository)  # type: ignore[return-value]

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit session context."""
        pass


class MockAsyncSession(AsyncSession):
    """Mock AsyncSession that implements required methods."""

    def __init__(self, repository: "MockCJRepository") -> None:
        """Initialize with repository reference."""
        # Don't call super().__init__() as AsyncSession requires real database setup
        self.repository = repository

    def add(self, instance: object, _warn: bool = True) -> None:
        """Mock session add operation."""
        if isinstance(instance, AnchorEssayReference):
            # Simulate database auto-increment ID
            instance.id = 42
            self.repository.created_anchor = instance

    async def commit(self) -> None:
        """Mock session commit operation."""
        if self.repository.behavior == "database_failure":
            raise RuntimeError("Database commit failed")

    async def flush(self, objects: Sequence[object] | None = None) -> None:
        """Mock session flush operation."""
        if self.repository.behavior == "database_failure":
            raise RuntimeError("Database flush failed")


class MockCJRepository(CJRepositoryProtocol):
    """Mock implementation of CJRepositoryProtocol for testing."""

    def __init__(self, behavior: str = "success") -> None:
        """Initialize mock with configurable behavior."""
        self.behavior = behavior
        self.created_anchor: AnchorEssayReference | None = None
        self.session_context_calls = 0
        self.assignment_contexts: dict[str, dict[str, Any]] = {}
        self.register_assignment_context("default-assignment")
        self._instruction_store = AssessmentInstructionStore()

    def register_assignment_context(
        self,
        assignment_id: str,
        *,
        grade_scale: str = "swedish_8_anchor",
        instructions_text: str = "Default instructions",
        course_id: str | None = None,
    ) -> None:
        """Add or update assignment metadata returned to the API under test."""
        self.assignment_contexts[assignment_id] = {
            "assignment_id": assignment_id,
            "course_id": course_id,
            "instructions_text": instructions_text,
            "grade_scale": grade_scale,
        }

    def session(self) -> AsyncContextManager[AsyncSession]:
        """Return mock session context manager."""
        return MockSessionManager(self)

    async def get_assessment_instruction(
        self,
        session: AsyncSession,
        assignment_id: str | None,
        course_id: str | None,
    ) -> AssessmentInstruction | None:
        """Return stored instruction when present."""
        return self._instruction_store.get(assignment_id=assignment_id, course_id=course_id)

    async def get_assignment_context(
        self,
        session: AsyncSession,
        assignment_id: str,
    ) -> dict[str, Any] | None:
        """Return stored assignment context for tests."""
        return self.assignment_contexts.get(assignment_id)

    async def get_cj_batch_upload(
        self,
        session: AsyncSession,
        cj_batch_id: int,
    ) -> Any | None:
        """Mock implementation - not used in anchor management tests."""
        return None

    async def get_anchor_essay_references(
        self,
        session: AsyncSession,
        assignment_id: str,
        grade_scale: str | None = None,
    ) -> list[Any]:
        """Mock implementation - not used in anchor management tests."""
        return []

    async def store_grade_projections(
        self,
        session: AsyncSession,
        projections: list[Any],
    ) -> None:
        """Mock implementation - not used in anchor management tests."""
        pass

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
        """Mock implementation - not used in anchor management tests."""
        return None

    async def create_or_update_cj_processed_essay(
        self,
        session: AsyncSession,
        cj_batch_id: int,
        els_essay_id: str,
        text_storage_id: str,
        assessment_input_text: str,
        processing_metadata: dict | None = None,
    ) -> Any:
        """Mock implementation - not used in anchor management tests."""
        return None

    async def get_essays_for_cj_batch(
        self,
        session: AsyncSession,
        cj_batch_id: int,
    ) -> list[Any]:
        """Mock implementation - not used in anchor management tests."""
        return []

    async def get_comparison_pair_by_essays(
        self,
        session: AsyncSession,
        cj_batch_id: int,
        essay_a_els_id: str,
        essay_b_els_id: str,
    ) -> Any | None:
        """Mock implementation - not used in anchor management tests."""
        return None

    async def store_comparison_results(
        self,
        session: AsyncSession,
        results: list[Any],
        cj_batch_id: int,
    ) -> None:
        """Mock implementation - not used in anchor management tests."""
        pass

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
        return self._instruction_store.upsert(
            assignment_id=assignment_id,
            course_id=course_id,
            instructions_text=instructions_text,
            grade_scale=grade_scale,
            student_prompt_storage_id=student_prompt_storage_id,
        )

    async def list_assessment_instructions(
        self,
        session: AsyncSession,
        *,
        limit: int,
        offset: int,
        grade_scale: str | None = None,
    ) -> tuple[list[AssessmentInstruction], int]:
        return self._instruction_store.list(limit=limit, offset=offset, grade_scale=grade_scale)

    async def delete_assessment_instruction(
        self,
        session: AsyncSession,
        *,
        assignment_id: str | None,
        course_id: str | None,
    ) -> bool:
        return self._instruction_store.delete(
            assignment_id=assignment_id,
            course_id=course_id,
        )

    async def update_essay_scores_in_batch(
        self,
        session: AsyncSession,
        cj_batch_id: int,
        scores: dict[str, float],
    ) -> None:
        """Mock implementation - not used in anchor management tests."""
        pass

    async def update_cj_batch_status(
        self,
        session: AsyncSession,
        cj_batch_id: int,
        status: Any,
    ) -> None:
        """Mock implementation - not used in anchor management tests."""
        pass

    async def get_final_cj_rankings(
        self,
        session: AsyncSession,
        cj_batch_id: int,
    ) -> list[dict[str, Any]]:
        """Mock implementation - not used in anchor management tests."""
        return []

    async def initialize_db_schema(self) -> None:
        """Mock implementation - not used in anchor management tests."""
        pass


class MissingStorageIdClient(ContentClientProtocol):
    """Mock client that doesn't return storage_id for error testing."""

    def __init__(self) -> None:
        """Initialize mock."""
        self.call_count = 0
        self.last_call_params: dict[str, Any] = {}

    async def store_content(self, content: str, content_type: str = "text/plain") -> dict[str, str]:
        """Mock store that returns empty dict."""
        self.call_count += 1
        self.last_call_params = {"content": content, "content_type": content_type}
        return {}  # Missing content_id

    async def fetch_content(self, storage_id: str, correlation_id: UUID) -> str:
        """Mock fetch operation."""
        return "Mock content"


class FailingMockRepository:
    """Mock repository that raises unexpected exception."""

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        """Raise unexpected exception during session creation."""
        raise ValueError("Unexpected database error")
        yield  # This will never be reached but satisfies the type checker
