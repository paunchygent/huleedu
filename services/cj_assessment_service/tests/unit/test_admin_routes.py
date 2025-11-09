"""Unit tests for CJ admin routes."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any, AsyncContextManager, AsyncIterator, cast
from uuid import UUID, uuid4

import pytest
from _pytest.monkeypatch import MonkeyPatch
from dishka import Provider, Scope, make_async_container, provide
from huleedu_service_libs.error_handling.correlation import CorrelationContext
from huleedu_service_libs.error_handling.quart import register_error_handlers
from quart import Quart
from quart.typing import TestClientProtocol as QuartTestClient
from quart_dishka import QuartDishka
from sqlalchemy.ext.asyncio import AsyncSession

from services.cj_assessment_service.api import admin_routes
from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.models_db import AssessmentInstruction
from services.cj_assessment_service.protocols import CJRepositoryProtocol
from services.cj_assessment_service.tests.unit.instruction_store import AssessmentInstructionStore


class AdminRepositoryMock(CJRepositoryProtocol):
    """In-memory repository for admin route tests."""

    def __init__(self) -> None:
        self._instruction_store = AssessmentInstructionStore()

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
    ) -> AssessmentInstruction:
        return self._instruction_store.upsert(
            assignment_id=assignment_id,
            course_id=course_id,
            instructions_text=instructions_text,
            grade_scale=grade_scale,
        )

    async def list_assessment_instructions(
        self,
        session: AsyncSession,
        *,
        limit: int,
        offset: int,
        grade_scale: str | None = None,
    ) -> tuple[list[AssessmentInstruction], int]:
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
        return self._instruction_store.delete(
            assignment_id=assignment_id,
            course_id=course_id,
        )

    async def get_assessment_instruction(
        self,
        session: AsyncSession,
        assignment_id: str | None,
        course_id: str | None,
    ) -> AssessmentInstruction | None:
        return self._instruction_store.get(
            assignment_id=assignment_id,
            course_id=course_id,
        )

    def seed_instruction(
        self,
        *,
        assignment_id: str | None,
        course_id: str | None,
        instructions_text: str,
        grade_scale: str,
        created_at: datetime | None = None,
    ) -> AssessmentInstruction:
        """Helper for tests to preload instructions."""
        return self._instruction_store.upsert(
            assignment_id=assignment_id,
            course_id=course_id,
            instructions_text=instructions_text,
            grade_scale=grade_scale,
            created_at=created_at,
        )

    # Unused protocol methods (satisfy interface)
    async def get_assignment_context(
        self,
        session: AsyncSession,
        assignment_id: str,
    ) -> dict[str, Any] | None:
        return None

    async def get_cj_batch_upload(
        self,
        session: AsyncSession,
        cj_batch_id: int,
    ) -> Any | None:
        return None

    async def get_anchor_essay_references(
        self,
        session: AsyncSession,
        assignment_id: str,
        grade_scale: str | None = None,
    ) -> list[Any]:
        return []

    async def store_grade_projections(
        self,
        session: AsyncSession,
        projections: list[Any],
    ) -> None:
        return None

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
        return None

    async def get_essays_for_cj_batch(
        self,
        session: AsyncSession,
        cj_batch_id: int,
    ) -> list[Any]:
        return []

    async def get_comparison_pair_by_essays(
        self,
        session: AsyncSession,
        cj_batch_id: int,
        essay_a_els_id: str,
        essay_b_els_id: str,
    ) -> Any | None:
        return None

    async def store_comparison_results(
        self,
        session: AsyncSession,
        results: list[Any],
        cj_batch_id: int,
    ) -> None:
        return None

    async def update_essay_scores_in_batch(
        self,
        session: AsyncSession,
        cj_batch_id: int,
        scores: dict[str, float],
    ) -> None:
        return None

    async def update_cj_batch_status(
        self,
        session: AsyncSession,
        cj_batch_id: int,
        status: Any,
    ) -> None:
        return None

    async def get_final_cj_rankings(
        self,
        session: AsyncSession,
        cj_batch_id: int,
    ) -> list[dict[str, Any]]:
        return []

    async def initialize_db_schema(self) -> None:
        return None


@pytest.fixture
def admin_repo() -> AdminRepositoryMock:
    return AdminRepositoryMock()


@pytest.fixture
def settings() -> Settings:
    s = Settings()
    s.ENABLE_ADMIN_ENDPOINTS = True
    return s


@pytest.fixture
def correlation_context() -> CorrelationContext:
    return CorrelationContext(
        original=str(uuid4()),
        uuid=uuid4(),
        source="generated",
    )


@pytest.fixture
def admin_app(
    admin_repo: AdminRepositoryMock,
    settings: Settings,
    correlation_context: CorrelationContext,
) -> Quart:
    app = Quart(__name__)
    app.config["settings"] = settings
    register_error_handlers(app)

    class TestProvider(Provider):
        @provide(scope=Scope.REQUEST)
        def provide_repository(self) -> CJRepositoryProtocol:
            return admin_repo

        @provide(scope=Scope.REQUEST)
        def provide_correlation_context(self) -> CorrelationContext:
            return correlation_context

    container = make_async_container(TestProvider())
    QuartDishka(app=app, container=container)
    app.register_blueprint(admin_routes.bp)

    @app.after_serving
    async def cleanup() -> None:
        await container.close()

    return app


@pytest.fixture
async def client(admin_app: Quart) -> AsyncIterator[QuartTestClient]:  # type: ignore[override]
    async with admin_app.test_client() as test_client:
        yield test_client


def _patch_decode(monkeypatch: MonkeyPatch, roles: list[str] | None = None) -> None:
    from huleedu_service_libs import auth as auth_module
    from huleedu_service_libs.auth import jwt_utils
    from services.cj_assessment_service.api import admin_routes as admin_module

    def fake_decode(
        token: str,
        settings: Settings,
        correlation_id: UUID,
        service: str,
        operation: str,
    ) -> dict[str, Any]:
        return {"sub": "admin-user", "roles": roles or ["admin"]}

    monkeypatch.setattr(jwt_utils, "decode_and_validate_jwt", fake_decode)
    monkeypatch.setattr(auth_module, "decode_and_validate_jwt", fake_decode)
    monkeypatch.setattr(admin_module, "decode_and_validate_jwt", fake_decode)


@pytest.mark.asyncio
async def test_upsert_instruction_requires_admin(
    client: QuartTestClient, monkeypatch: MonkeyPatch
) -> None:
    _patch_decode(monkeypatch, roles=["analyst"])

    response = await client.post(
        "/admin/v1/assessment-instructions",
        headers={"Authorization": "Bearer fake"},
        json={
            "assignment_id": "a-1",
            "instructions_text": "Grade for clarity",
            "grade_scale": "swedish_8_anchor",
        },
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_upsert_and_get_instruction(
    client: QuartTestClient, monkeypatch: MonkeyPatch
) -> None:
    _patch_decode(monkeypatch)

    resp = await client.post(
        "/admin/v1/assessment-instructions",
        headers={"Authorization": "Bearer fake"},
        json={
            "assignment_id": "assignment-1",
            "instructions_text": "Grade for clarity and structure",
            "grade_scale": "swedish_8_anchor",
        },
    )
    assert resp.status_code == 200

    resp_get = await client.get(
        "/admin/v1/assessment-instructions/assignment/assignment-1",
        headers={"Authorization": "Bearer fake"},
    )
    assert resp_get.status_code == 200
    fetched = await resp_get.get_json()
    assert fetched["grade_scale"] == "swedish_8_anchor"


@pytest.mark.asyncio
async def test_list_and_delete_instructions(
    client: QuartTestClient, monkeypatch: MonkeyPatch, admin_repo: AdminRepositoryMock
) -> None:
    _patch_decode(monkeypatch)

    admin_repo.seed_instruction(
        assignment_id="assignment-a",
        course_id=None,
        instructions_text="Instruction A text",
        grade_scale="swedish_8_anchor",
        created_at=datetime.now(UTC),
    )
    admin_repo.seed_instruction(
        assignment_id="assignment-b",
        course_id=None,
        instructions_text="Instruction B text",
        grade_scale="eng5_np_legacy_9_step",
        created_at=datetime.now(UTC),
    )

    resp = await client.get(
        "/admin/v1/assessment-instructions?page=1&page_size=10&grade_scale=swedish_8_anchor",
        headers={"Authorization": "Bearer fake"},
    )
    assert resp.status_code == 200
    payload = await resp.get_json()
    assert payload["total"] == 1

    delete_resp = await client.delete(
        "/admin/v1/assessment-instructions/assignment/assignment-a",
        headers={"Authorization": "Bearer fake"},
    )
    assert delete_resp.status_code == 200
