"""Unit tests for judge rubric admin endpoints."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, AsyncContextManager, AsyncIterator, cast
from uuid import UUID, uuid4

import pytest
from common_core.status_enums import CJBatchStateEnum
from dishka import Provider, Scope, make_async_container, provide
from huleedu_service_libs.error_handling.correlation import (
    CorrelationContext,
    extract_correlation_context_from_request,
)
from huleedu_service_libs.error_handling.quart import register_error_handlers
from huleedu_service_libs.testing.jwt_helpers import build_jwt_headers
from pydantic import SecretStr
from quart import Quart
from quart.typing import TestClientProtocol as QuartTestClient
from quart_dishka import QuartDishka
from sqlalchemy.ext.asyncio import AsyncSession

from services.cj_assessment_service.api.admin import judge_rubrics_bp
from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.models_db import CJBatchState, ComparisonPair
from services.cj_assessment_service.protocols import (
    AssessmentInstructionRepositoryProtocol,
    ContentClientProtocol,
    SessionProviderProtocol,
)
from services.cj_assessment_service.tests.unit.test_mocks import AssessmentInstructionStore


class AdminRepositoryMock(AssessmentInstructionRepositoryProtocol, SessionProviderProtocol):
    """In-memory repository mock for admin rubric tests."""

    def __init__(self) -> None:
        self._instruction_store = AssessmentInstructionStore()
        self.records: list[dict[str, Any]] = []

    def session(self) -> AsyncContextManager[AsyncSession]:
        @asynccontextmanager
        async def _session() -> AsyncIterator[AsyncSession]:
            yield cast(AsyncSession, None)

        return _session()

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
    ) -> Any:
        record = self._instruction_store.upsert(
            assignment_id=assignment_id,
            course_id=course_id,
            instructions_text=instructions_text,
            grade_scale=grade_scale,
            student_prompt_storage_id=student_prompt_storage_id,
            judge_rubric_storage_id=judge_rubric_storage_id,
        )
        self.records.append(
            {
                "assignment_id": assignment_id,
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
        raise NotImplementedError("Not needed for admin rubric tests")

    async def list_assessment_instructions(
        self,
        session: AsyncSession,
        *,
        limit: int,
        offset: int,
        grade_scale: str | None = None,
    ) -> tuple[list[Any], int]:
        raise NotImplementedError("Not needed for admin rubric tests")

    async def delete_assessment_instruction(
        self, session: AsyncSession, *, assignment_id: str | None, course_id: str | None
    ) -> bool:
        raise NotImplementedError("Not needed for admin rubric tests")

    async def get_cj_batch_upload(self, session: AsyncSession, cj_batch_id: int) -> Any:
        raise NotImplementedError("Not needed for admin rubric tests")

    async def get_batch_state(
        self, session: AsyncSession, cj_batch_id: int, *, for_update: bool = False
    ) -> CJBatchState | None:
        return None

    async def get_comparison_pair_by_correlation_id(
        self, session: AsyncSession, request_correlation_id: UUID
    ) -> ComparisonPair | None:
        return None

    async def get_anchor_essay_references(
        self, session: AsyncSession, assignment_id: str, grade_scale: str | None = None
    ) -> list[Any]:
        raise NotImplementedError("Not needed for admin rubric tests")

    async def store_grade_projections(self, session: AsyncSession, projections: list[Any]) -> None:
        raise NotImplementedError("Not needed for admin rubric tests")

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
        raise NotImplementedError("Not needed for admin rubric tests")

    async def create_or_update_cj_processed_essay(
        self,
        session: AsyncSession,
        cj_batch_id: int,
        els_essay_id: str,
        text_storage_id: str,
        assessment_input_text: str,
        processing_metadata: dict[str, Any] | None = None,
    ) -> Any:
        raise NotImplementedError("Not needed for admin rubric tests")

    async def get_essays_for_cj_batch(self, session: AsyncSession, cj_batch_id: int) -> list[Any]:
        raise NotImplementedError("Not needed for admin rubric tests")

    async def update_essay_scores_in_batch(
        self, session: AsyncSession, cj_batch_id: int, scores: dict[str, float]
    ) -> None:
        raise NotImplementedError("Not needed for admin rubric tests")

    async def get_final_cj_rankings(
        self, session: AsyncSession, cj_batch_id: int
    ) -> list[dict[str, Any]]:
        raise NotImplementedError("Not needed for admin rubric tests")

    async def get_comparison_pair_by_essays(
        self,
        session: AsyncSession,
        cj_batch_id: int,
        essay_a_els_id: str,
        essay_b_els_id: str,
    ) -> Any | None:
        raise NotImplementedError("Not needed for admin rubric tests")

    async def store_comparison_results(
        self, session: AsyncSession, results: list[Any], cj_batch_id: int
    ) -> None:
        return None

    async def update_cj_batch_status(
        self, session: AsyncSession, cj_batch_id: int, status: str
    ) -> None:
        return None

    async def initialize_db_schema(self) -> None:
        return None

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
    ) -> list[CJBatchState]:
        """Get batches stuck in specified states beyond threshold."""
        return []

    async def get_batches_ready_for_completion(
        self,
        session: AsyncSession,
    ) -> list[CJBatchState]:
        """Get batches ready for final completion."""
        return []

    async def get_batch_state_for_update(
        self,
        session: AsyncSession,
        batch_id: int,
        for_update: bool = False,
    ) -> CJBatchState | None:
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
    """Mock content client for rubric upload/retrieval tests."""

    def __init__(self) -> None:
        self._storage: dict[str, str] = {}

    async def store_content(self, content: str, content_type: str = "text/plain") -> dict[str, str]:
        storage_id = str(uuid4())
        self._storage[storage_id] = content
        return {"content_id": storage_id}

    async def fetch_content(self, storage_id: str, correlation_id: UUID) -> str:
        if storage_id not in self._storage:
            raise ValueError(f"Content not found: {storage_id}")
        return self._storage[storage_id]


class TestProvider(Provider):
    """DI provider for judge rubric tests."""

    __test__ = False

    def __init__(self, repo: AdminRepositoryMock, content_client: ContentClientMock) -> None:
        super().__init__(scope=Scope.APP)
        self._repo = repo
        self._content_client = content_client

    @provide(scope=Scope.REQUEST)
    def provide_session_provider(self) -> SessionProviderProtocol:
        return self._repo

    @provide(scope=Scope.REQUEST)
    def provide_instruction_repository(self) -> AssessmentInstructionRepositoryProtocol:
        return self._repo

    @provide(scope=Scope.REQUEST)
    def get_content_client(self) -> ContentClientProtocol:
        return self._content_client

    @provide(scope=Scope.REQUEST)
    def get_correlation_context(self) -> CorrelationContext:
        from quart import request as quart_request

        return extract_correlation_context_from_request(quart_request)


TEST_JWT_SECRET = "test-secret-key"


@pytest.fixture
async def admin_rubric_app() -> AsyncIterator[
    tuple[QuartTestClient, AdminRepositoryMock, ContentClientMock, Settings]
]:
    """Create Quart app with judge rubric admin routes for testing."""

    settings = Settings()
    settings.ENABLE_ADMIN_ENDPOINTS = True
    settings.JWT_SECRET_KEY = SecretStr(TEST_JWT_SECRET)

    repo = AdminRepositoryMock()
    content_client = ContentClientMock()
    provider = TestProvider(repo, content_client)

    app = Quart(__name__)
    app.config["settings"] = settings
    register_error_handlers(app)

    class SettingsProvider(Provider):
        __test__ = False

        def __init__(self) -> None:
            super().__init__(scope=Scope.REQUEST)

        @provide(scope=Scope.REQUEST)
        def get_settings(self) -> Settings:
            return settings

    container = make_async_container(SettingsProvider(), provider)
    QuartDishka(app=app, container=container)
    app.register_blueprint(judge_rubrics_bp)

    try:
        async with app.test_client() as test_client:
            yield test_client, repo, content_client, settings
    finally:
        await container.close()


@pytest.mark.asyncio
class TestJudgeRubricUpload:
    """Test judge rubric upload endpoint."""

    async def test_upload_rubric_success(
        self,
        admin_rubric_app: tuple[
            QuartTestClient,
            AdminRepositoryMock,
            ContentClientMock,
            Settings,
        ],
    ) -> None:
        """Test successful judge rubric upload."""
        test_client, repo, _content_client, settings = admin_rubric_app

        # First create an assessment instruction
        await repo.upsert_assessment_instruction(
            session=cast(AsyncSession, None),
            assignment_id="ENG5-TEST",
            course_id=None,
            instructions_text="Test instructions for rubric upload",
            grade_scale="swedish_8_anchor",
        )

        # Upload judge rubric
        payload = {
            "assignment_id": "ENG5-TEST",
            "rubric_text": "You are an impartial Comparative Judgement assessor...",
        }

        response = await test_client.post(
            "/admin/v1/judge-rubrics",
            json=payload,
            headers=build_jwt_headers(
                settings,
                subject="test-admin-user",
                roles=["admin"],
                extra_claims={"email": "test-admin-user@admin.test"},
            ),
        )

        assert response.status_code == 200
        data = await response.get_json()

        assert data["assignment_id"] == "ENG5-TEST"
        assert "judge_rubric_storage_id" in data
        assert data["rubric_text"] == payload["rubric_text"]
        assert data["grade_scale"] == "swedish_8_anchor"

    async def test_upload_rubric_no_instruction(
        self,
        admin_rubric_app: tuple[
            QuartTestClient,
            AdminRepositoryMock,
            ContentClientMock,
            Settings,
        ],
    ) -> None:
        """Test rubric upload fails when no assessment instruction exists."""
        test_client, _, _, settings = admin_rubric_app

        payload = {
            "assignment_id": "NONEXISTENT",
            "rubric_text": "Test rubric text",
        }

        response = await test_client.post(
            "/admin/v1/judge-rubrics",
            json=payload,
            headers=build_jwt_headers(
                settings,
                subject="test-admin-user",
                roles=["admin"],
                extra_claims={"email": "test-admin-user@admin.test"},
            ),
        )

        assert response.status_code == 404

    async def test_upload_rubric_empty_text(
        self,
        admin_rubric_app: tuple[
            QuartTestClient,
            AdminRepositoryMock,
            ContentClientMock,
            Settings,
        ],
    ) -> None:
        """Test rubric upload validation rejects empty rubric text."""
        test_client, _, _, settings = admin_rubric_app

        payload = {
            "assignment_id": "ENG5-TEST",
            "rubric_text": "",  # Empty rubric
        }

        response = await test_client.post(
            "/admin/v1/judge-rubrics",
            json=payload,
            headers=build_jwt_headers(
                settings,
                subject="test-admin-user",
                roles=["admin"],
                extra_claims={"email": "test-admin-user@admin.test"},
            ),
        )

        assert response.status_code == 400

    async def test_upload_rubric_preserves_existing_fields(
        self,
        admin_rubric_app: tuple[
            QuartTestClient,
            AdminRepositoryMock,
            ContentClientMock,
            Settings,
        ],
    ) -> None:
        """Test that rubric upload preserves existing instruction fields."""
        test_client, repo, _content_client, settings = admin_rubric_app

        # Create instruction with student prompt
        existing_storage_id = "existing-student-prompt-id"
        await repo.upsert_assessment_instruction(
            session=cast(AsyncSession, None),
            assignment_id="ENG5-PRESERVE",
            course_id=None,
            instructions_text="Original instructions",
            grade_scale="swedish_8_anchor",
            student_prompt_storage_id=existing_storage_id,
        )

        # Upload judge rubric
        payload = {
            "assignment_id": "ENG5-PRESERVE",
            "rubric_text": "New judge rubric",
        }

        response = await test_client.post(
            "/admin/v1/judge-rubrics",
            json=payload,
            headers=build_jwt_headers(
                settings,
                subject="test-admin-user",
                roles=["admin"],
                extra_claims={"email": "test-admin-user@admin.test"},
            ),
        )

        assert response.status_code == 200
        data = await response.get_json()

        # Verify fields preserved
        assert data["instructions_text"] == "Original instructions"
        assert data["grade_scale"] == "swedish_8_anchor"


@pytest.mark.asyncio
class TestJudgeRubricGet:
    """Test judge rubric retrieval endpoint."""

    async def test_get_rubric_success(
        self,
        admin_rubric_app: tuple[
            QuartTestClient,
            AdminRepositoryMock,
            ContentClientMock,
            Settings,
        ],
    ) -> None:
        """Test successful judge rubric retrieval."""
        test_client, repo, content_client, settings = admin_rubric_app

        # Create instruction with rubric
        rubric_text = "You are an impartial assessor..."
        storage_response = await content_client.store_content(rubric_text, "text/plain")
        storage_id = storage_response["content_id"]

        await repo.upsert_assessment_instruction(
            session=cast(AsyncSession, None),
            assignment_id="ENG5-GET-TEST",
            course_id=None,
            instructions_text="Test instructions",
            grade_scale="eng5_np_national_9_step",
            judge_rubric_storage_id=storage_id,
        )

        # Retrieve rubric
        response = await test_client.get(
            "/admin/v1/judge-rubrics/assignment/ENG5-GET-TEST",
            headers=build_jwt_headers(
                settings,
                subject="test-admin-user",
                roles=["admin"],
                extra_claims={"email": "test-admin-user@admin.test"},
            ),
        )

        assert response.status_code == 200
        data = await response.get_json()

        assert data["assignment_id"] == "ENG5-GET-TEST"
        assert data["judge_rubric_storage_id"] == storage_id
        assert data["rubric_text"] == rubric_text
        assert data["grade_scale"] == "eng5_np_national_9_step"

    async def test_get_rubric_no_instruction(
        self,
        admin_rubric_app: tuple[
            QuartTestClient,
            AdminRepositoryMock,
            ContentClientMock,
            Settings,
        ],
    ) -> None:
        """Test rubric retrieval fails when no instruction exists."""
        test_client, _, _, settings = admin_rubric_app

        response = await test_client.get(
            "/admin/v1/judge-rubrics/assignment/NONEXISTENT",
            headers=build_jwt_headers(
                settings,
                subject="test-admin-user",
                roles=["admin"],
                extra_claims={"email": "test-admin-user@admin.test"},
            ),
        )

        assert response.status_code == 404

    async def test_get_rubric_no_rubric_configured(
        self,
        admin_rubric_app: tuple[
            QuartTestClient,
            AdminRepositoryMock,
            ContentClientMock,
            Settings,
        ],
    ) -> None:
        """Test rubric retrieval fails when instruction exists but no rubric configured."""
        test_client, repo, _content_client, settings = admin_rubric_app

        # Create instruction WITHOUT rubric
        await repo.upsert_assessment_instruction(
            session=cast(AsyncSession, None),
            assignment_id="ENG5-NO-RUBRIC",
            course_id=None,
            instructions_text="Test instructions",
            grade_scale="swedish_8_anchor",
            judge_rubric_storage_id=None,  # No rubric
        )

        response = await test_client.get(
            "/admin/v1/judge-rubrics/assignment/ENG5-NO-RUBRIC",
            headers=build_jwt_headers(
                settings,
                subject="test-admin-user",
                roles=["admin"],
                extra_claims={"email": "test-admin-user@admin.test"},
            ),
        )

        assert response.status_code == 404
