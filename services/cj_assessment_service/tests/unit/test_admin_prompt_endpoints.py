"""Unit tests for student prompt admin endpoints."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, AsyncContextManager, AsyncIterator, cast
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from common_core.status_enums import CJBatchStateEnum
from dishka import Provider, Scope, make_async_container, provide
from huleedu_service_libs.error_handling.correlation import CorrelationContext
from huleedu_service_libs.error_handling.quart import register_error_handlers
from huleedu_service_libs.testing.jwt_helpers import build_jwt_headers
from pydantic import SecretStr
from quart import Quart
from quart.typing import TestClientProtocol as QuartTestClient
from quart_dishka import QuartDishka
from sqlalchemy.ext.asyncio import AsyncSession

from services.cj_assessment_service.api.admin import student_prompts_bp
from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.models_db import CJBatchState, ComparisonPair
from services.cj_assessment_service.protocols import (
    AssessmentInstructionRepositoryProtocol,
    ContentClientProtocol,
    SessionProviderProtocol,
)
from services.cj_assessment_service.tests.unit.test_mocks import AssessmentInstructionStore


class AdminRepositoryMock(AssessmentInstructionRepositoryProtocol, SessionProviderProtocol):
    """In-memory repository mock for admin tests."""

    def __init__(self) -> None:
        self._instruction_store = AssessmentInstructionStore()
        self.records: list[dict[str, Any]] = []

    def session(self) -> AsyncContextManager[AsyncSession]:
        @asynccontextmanager
        async def _session() -> AsyncIterator[AsyncSession]:
            session = AsyncMock(spec=AsyncSession)
            session.commit = AsyncMock()
            session.rollback = AsyncMock()
            session.flush = AsyncMock()
            yield cast(AsyncSession, session)

        return _session()

    async def upsert_assessment_instruction(
        self,
        session: AsyncSession,
        *,
        assignment_id: str | None,
        course_id: str | None,
        instructions_text: str,
        grade_scale: str,
        context_origin: str = "canonical_national",
        student_prompt_storage_id: str | None = None,
        judge_rubric_storage_id: str | None = None,
    ) -> Any:
        record = self._instruction_store.upsert(
            assignment_id=assignment_id,
            course_id=course_id,
            instructions_text=instructions_text,
            grade_scale=grade_scale,
            context_origin=context_origin,
            student_prompt_storage_id=student_prompt_storage_id,
            judge_rubric_storage_id=judge_rubric_storage_id,
        )
        self.records.append(
            {
                "assignment_id": assignment_id,
                "student_prompt_storage_id": student_prompt_storage_id,
                "judge_rubric_storage_id": judge_rubric_storage_id,
            }
        )
        return record

    async def get_assessment_instruction(
        self,
        session: AsyncSession,
        assignment_id: str | None,
        course_id: str | None,
    ) -> Any | None:
        return self._instruction_store.get(assignment_id=assignment_id, course_id=course_id)

    # Stub implementations for required protocol methods not used in these tests
    async def get_assignment_context(self, session: AsyncSession, assignment_id: str) -> Any:
        raise NotImplementedError("Not needed for admin prompt tests")

    async def list_assessment_instructions(
        self,
        session: AsyncSession,
        *,
        limit: int,
        offset: int,
        grade_scale: str | None = None,
    ) -> tuple[list[Any], int]:
        raise NotImplementedError("Not needed for admin prompt tests")

    async def delete_assessment_instruction(
        self, session: AsyncSession, *, assignment_id: str | None, course_id: str | None
    ) -> bool:
        raise NotImplementedError("Not needed for admin prompt tests")

    async def get_cj_batch_upload(self, session: AsyncSession, cj_batch_id: int) -> Any:
        raise NotImplementedError("Not needed for admin prompt tests")

    async def get_anchor_essay_references(
        self, session: AsyncSession, assignment_id: str, grade_scale: str | None = None
    ) -> list[Any]:
        raise NotImplementedError("Not needed for admin prompt tests")

    async def get_batch_state(
        self, session: AsyncSession, cj_batch_id: int, *, for_update: bool = False
    ) -> CJBatchState | None:
        return None

    async def get_comparison_pair_by_correlation_id(
        self, session: AsyncSession, request_correlation_id: UUID
    ) -> ComparisonPair | None:
        return None

    async def store_grade_projections(self, session: AsyncSession, projections: list[Any]) -> None:
        raise NotImplementedError("Not needed for admin prompt tests")

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
        raise NotImplementedError("Not needed for admin prompt tests")

    async def create_or_update_cj_processed_essay(
        self,
        session: AsyncSession,
        cj_batch_id: int,
        els_essay_id: str,
        text_storage_id: str,
        assessment_input_text: str,
        processing_metadata: dict | None = None,
    ) -> Any:
        raise NotImplementedError("Not needed for admin prompt tests")

    async def get_essays_for_cj_batch(self, session: AsyncSession, cj_batch_id: int) -> list[Any]:
        raise NotImplementedError("Not needed for admin prompt tests")

    async def get_comparison_pair_by_essays(
        self, session: AsyncSession, cj_batch_id: int, essay_a_id: str, essay_b_id: str
    ) -> Any | None:
        raise NotImplementedError("Not needed for admin prompt tests")

    async def store_comparison_results(
        self, session: AsyncSession, results: list[Any], cj_batch_id: int
    ) -> None:
        raise NotImplementedError("Not needed for admin prompt tests")

    async def update_essay_scores_in_batch(
        self, session: AsyncSession, cj_batch_id: int, scores: dict[str, float]
    ) -> None:
        raise NotImplementedError("Not needed for admin prompt tests")

    async def update_cj_batch_status(
        self, session: AsyncSession, cj_batch_id: int, status: str
    ) -> None:
        raise NotImplementedError("Not needed for admin prompt tests")

    async def get_final_cj_rankings(self, session: AsyncSession, cj_batch_id: int) -> list[Any]:
        raise NotImplementedError("Not needed for admin prompt tests")

    async def initialize_db_schema(self) -> None:
        raise NotImplementedError("Not needed for admin prompt tests")

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
        """Stub implementation for test mocks."""
        return 1  # Return a mock anchor ID

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

    async def get_batch_state_for_update(
        self,
        session: AsyncSession,
        batch_id: int,
        for_update: bool = False,
    ) -> Any | None:
        """Get batch state with optional row locking."""
        return None

    async def update_batch_state(
        self,
        session: AsyncSession,
        batch_id: int,
        state: CJBatchStateEnum,
    ) -> None:
        """Update batch state."""
        pass


class ContentClientMock(ContentClientProtocol):
    """Content client mock capturing correlation usage."""

    def __init__(self) -> None:
        self.store_calls: list[tuple[str, str]] = []
        self.fetch_calls: list[tuple[str, UUID]] = []
        self._next_store_response: dict[str, str] | None = None
        self._fetch_text: str = ""
        self._raise_store: Exception | None = None
        self._raise_fetch: Exception | None = None

    async def store_content(self, content: str, content_type: str = "text/plain") -> dict[str, str]:
        self.store_calls.append((content, content_type))
        if self._raise_store:
            raise self._raise_store
        if self._next_store_response is not None:
            response = self._next_store_response
            self._next_store_response = None
            return response
        return {"content_id": "storage-id-123"}

    async def fetch_content(self, storage_id: str, correlation_id: UUID) -> str:
        self.fetch_calls.append((storage_id, correlation_id))
        if self._raise_fetch:
            raise self._raise_fetch
        return self._fetch_text

    def set_store_response(self, response: dict[str, str]) -> None:
        self._next_store_response = response

    def set_fetch_text(self, text: str) -> None:
        self._fetch_text = text


@pytest.fixture
def admin_repo() -> AdminRepositoryMock:
    repo = AdminRepositoryMock()
    repo.records.clear()
    repo._instruction_store.upsert(
        assignment_id="assignment-1",
        course_id=None,
        instructions_text="Judge clarity",
        grade_scale="swedish_8_anchor",
        student_prompt_storage_id="seed-storage",
    )
    return repo


@pytest.fixture
def content_client() -> ContentClientMock:
    mock_client = ContentClientMock()
    mock_client.set_fetch_text("Prompt text example ÅÄÖ …")
    return mock_client


@pytest.fixture
def correlation_context() -> CorrelationContext:
    return CorrelationContext(original=str(uuid4()), uuid=uuid4(), source="generated")


@pytest.fixture
def settings() -> Settings:
    cfg = Settings()
    cfg.ENABLE_ADMIN_ENDPOINTS = True
    cfg.JWT_SECRET_KEY = SecretStr("unit-test-secret-key-with-min-32-bytes")
    return cfg


@pytest.fixture
def admin_app(
    admin_repo: AdminRepositoryMock,
    content_client: ContentClientMock,
    correlation_context: CorrelationContext,
    settings: Settings,
) -> Quart:
    app = Quart(__name__)
    app.config["settings"] = settings
    register_error_handlers(app)

    class TestProvider(Provider):
        @provide(scope=Scope.REQUEST)
        def provide_session_provider(self) -> SessionProviderProtocol:
            return admin_repo

        @provide(scope=Scope.REQUEST)
        def provide_instruction_repository(self) -> AssessmentInstructionRepositoryProtocol:
            return admin_repo

        @provide(scope=Scope.REQUEST)
        def provide_content_client(self) -> ContentClientProtocol:
            return content_client

        @provide(scope=Scope.REQUEST)
        def provide_correlation(self) -> CorrelationContext:
            return correlation_context

    container = make_async_container(TestProvider())
    QuartDishka(app=app, container=container)
    app.register_blueprint(student_prompts_bp)

    @app.after_serving
    async def cleanup() -> None:  # pragma: no cover - defensive cleanup
        await container.close()

    return app


@pytest.fixture
async def client(admin_app: Quart) -> AsyncIterator[QuartTestClient]:
    async with admin_app.test_client() as test_client:
        yield test_client


@pytest.fixture
def admin_headers(settings: Settings) -> dict[str, str]:
    return build_jwt_headers(
        settings,
        subject="test-admin-user",
        roles=["admin"],
        extra_claims={"email": "test-admin-user@admin.test"},
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "prompt_text",
    [
        "Student prompt sample text",
        "Unicode prompt åäö with extended length" * 50,
    ],
    ids=["simple_prompt", "long_unicode_prompt"],
)
async def test_prompt_upload_success(
    client: QuartTestClient,
    admin_repo: AdminRepositoryMock,
    content_client: ContentClientMock,
    admin_headers: dict[str, str],
    prompt_text: str,
) -> None:
    response = await client.post(
        "/admin/v1/student-prompts",
        headers=admin_headers,
        json={"assignment_id": "assignment-1", "prompt_text": prompt_text},
    )

    assert response.status_code == 200
    payload = await response.get_json()
    assert payload["student_prompt_storage_id"] == "storage-id-123"
    assert payload["assignment_id"] == "assignment-1"
    assert payload["prompt_text"] == prompt_text

    assert content_client.store_calls == [(prompt_text, "text/plain")]
    instruction = admin_repo._instruction_store.get(assignment_id="assignment-1", course_id=None)
    assert instruction is not None
    assert instruction.student_prompt_storage_id == "storage-id-123"


@pytest.mark.asyncio
async def test_prompt_upload_instruction_missing(
    client: QuartTestClient,
    admin_repo: AdminRepositoryMock,
    admin_headers: dict[str, str],
) -> None:
    admin_repo._instruction_store.delete(assignment_id="assignment-1", course_id=None)

    response = await client.post(
        "/admin/v1/student-prompts",
        headers=admin_headers,
        json={"assignment_id": "assignment-1", "prompt_text": "valid prompt text"},
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_prompt_upload_missing_storage_id(
    client: QuartTestClient,
    content_client: ContentClientMock,
    admin_headers: dict[str, str],
) -> None:
    content_client.set_store_response({})

    response = await client.post(
        "/admin/v1/student-prompts",
        headers=admin_headers,
        json={"assignment_id": "assignment-1", "prompt_text": "valid prompt body"},
    )

    assert response.status_code == 500


@pytest.mark.asyncio
async def test_prompt_upload_validation_error(
    client: QuartTestClient,
    admin_headers: dict[str, str],
) -> None:
    response = await client.post(
        "/admin/v1/student-prompts",
        headers=admin_headers,
        json={"assignment_id": "assignment-1", "prompt_text": "short"},
    )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_prompt_get_success(
    client: QuartTestClient,
    content_client: ContentClientMock,
    admin_headers: dict[str, str],
) -> None:
    content_client.set_fetch_text("Fetched prompt text")

    response = await client.get(
        "/admin/v1/student-prompts/assignment/assignment-1",
        headers=admin_headers,
    )

    assert response.status_code == 200
    payload = await response.get_json()
    assert payload["prompt_text"] == "Fetched prompt text"
    assert payload["student_prompt_storage_id"] == "seed-storage"

    assert content_client.fetch_calls
    _, corr_id = content_client.fetch_calls[0]
    assert isinstance(corr_id, UUID)


@pytest.mark.asyncio
async def test_prompt_get_instruction_missing(
    client: QuartTestClient,
    admin_repo: AdminRepositoryMock,
    admin_headers: dict[str, str],
) -> None:
    admin_repo._instruction_store.delete(assignment_id="assignment-1", course_id=None)

    response = await client.get(
        "/admin/v1/student-prompts/assignment/assignment-1",
        headers=admin_headers,
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_prompt_get_missing_storage_id(
    client: QuartTestClient,
    admin_repo: AdminRepositoryMock,
    admin_headers: dict[str, str],
) -> None:
    # The in-memory instruction store follows the same semantics as the real repository:
    # passing `student_prompt_storage_id=None` to upsert does NOT clear an existing value.
    # To simulate "instruction exists but no prompt uploaded yet", we replace the record.
    admin_repo._instruction_store.delete(assignment_id="assignment-1", course_id=None)
    admin_repo._instruction_store.upsert(
        assignment_id="assignment-1",
        course_id=None,
        instructions_text="Judge",
        grade_scale="swedish_8_anchor",
        student_prompt_storage_id=None,
    )

    response = await client.get(
        "/admin/v1/student-prompts/assignment/assignment-1",
        headers=admin_headers,
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_prompt_get_content_service_failure(
    client: QuartTestClient,
    content_client: ContentClientMock,
    admin_headers: dict[str, str],
) -> None:
    content_client._raise_fetch = RuntimeError("fetch_failed")

    response = await client.get(
        "/admin/v1/student-prompts/assignment/assignment-1",
        headers=admin_headers,
    )

    assert response.status_code == 500
