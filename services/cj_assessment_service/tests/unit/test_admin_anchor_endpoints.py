"""Unit tests for CJ admin anchor summary endpoints."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any, AsyncContextManager, AsyncIterator, cast
from uuid import uuid4

import pytest
from dishka import Provider, Scope, make_async_container, provide
from huleedu_service_libs.error_handling.correlation import CorrelationContext
from huleedu_service_libs.error_handling.quart import register_error_handlers
from huleedu_service_libs.testing.jwt_helpers import build_jwt_headers
from pydantic import SecretStr
from quart import Quart
from quart.typing import TestClientProtocol as QuartTestClient
from quart_dishka import QuartDishka
from sqlalchemy.ext.asyncio import AsyncSession

from services.cj_assessment_service.api.admin import anchors_bp
from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.models_db import AnchorEssayReference, AssessmentInstruction
from services.cj_assessment_service.protocols import (
    AnchorRepositoryProtocol,
    AssessmentInstructionRepositoryProtocol,
    SessionProviderProtocol,
)
from services.cj_assessment_service.tests.unit.test_mocks.instruction_store import (
    AssessmentInstructionStore,
)


class AdminAnchorRepoMock(
    AssessmentInstructionRepositoryProtocol,
    AnchorRepositoryProtocol,
    SessionProviderProtocol,
):
    def __init__(self) -> None:
        self._instruction_store = AssessmentInstructionStore()
        self._anchors: list[AnchorEssayReference] = []

    def session(self) -> AsyncContextManager[AsyncSession]:
        @asynccontextmanager
        async def _session() -> AsyncIterator[AsyncSession]:
            yield cast(AsyncSession, None)

        return _session()

    async def get_assessment_instruction(
        self,
        session: AsyncSession,
        assignment_id: str | None,
        course_id: str | None,
    ) -> AssessmentInstruction | None:
        return self._instruction_store.get(assignment_id=assignment_id, course_id=course_id)

    async def get_assignment_context(
        self,
        session: AsyncSession,
        assignment_id: str,
    ) -> dict[str, Any] | None:
        record = self._instruction_store.get(assignment_id=assignment_id, course_id=None)
        if record is None:
            return None
        return {
            "assignment_id": assignment_id,
            "grade_scale": record.grade_scale,
            "context_origin": record.context_origin,
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
        return self._instruction_store.upsert(
            assignment_id=assignment_id,
            course_id=course_id,
            instructions_text=instructions_text,
            grade_scale=grade_scale,
            context_origin=context_origin,
            student_prompt_storage_id=student_prompt_storage_id,
            judge_rubric_storage_id=judge_rubric_storage_id,
            created_at=datetime.now(UTC),
        )

    async def list_assessment_instructions(
        self,
        session: AsyncSession,
        *,
        limit: int,
        offset: int,
        grade_scale: str | None = None,
    ) -> tuple[list[AssessmentInstruction], int]:
        records, total = self._instruction_store.list(
            limit=limit,
            offset=offset,
            grade_scale=grade_scale,
        )
        return list(records), total

    async def delete_assessment_instruction(
        self,
        session: AsyncSession,
        *,
        assignment_id: str | None,
        course_id: str | None,
    ) -> bool:
        return self._instruction_store.delete(assignment_id=assignment_id, course_id=course_id)

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
        for anchor in self._anchors:
            if (
                anchor.assignment_id == assignment_id
                and anchor.anchor_label == anchor_label
                and anchor.grade_scale == grade_scale
            ):
                anchor.grade = grade
                anchor.text_storage_id = text_storage_id
                return int(anchor.id)

        rec = AnchorEssayReference()
        rec.id = len(self._anchors) + 1
        rec.assignment_id = assignment_id
        rec.anchor_label = anchor_label
        rec.grade = grade
        rec.grade_scale = grade_scale
        rec.text_storage_id = text_storage_id
        rec.created_at = datetime.now(UTC)
        self._anchors.append(rec)
        return int(rec.id)

    async def get_anchor_essay_references(
        self,
        session: AsyncSession,
        assignment_id: str,
        grade_scale: str | None = None,
    ) -> list[AnchorEssayReference]:
        anchors = [a for a in self._anchors if a.assignment_id == assignment_id]
        if grade_scale is not None:
            anchors = [a for a in anchors if a.grade_scale == grade_scale]
        return anchors

    def seed_instruction(self, *, assignment_id: str, grade_scale: str) -> None:
        self._instruction_store.upsert(
            assignment_id=assignment_id,
            course_id=None,
            instructions_text="x" * 20,
            grade_scale=grade_scale,
            created_at=datetime.now(UTC),
        )

    def seed_anchor(
        self,
        *,
        assignment_id: str,
        anchor_label: str,
        grade: str,
        grade_scale: str,
        text_storage_id: str = "content-1",
    ) -> None:
        rec = AnchorEssayReference()
        rec.id = len(self._anchors) + 1
        rec.assignment_id = assignment_id
        rec.anchor_label = anchor_label
        rec.grade = grade
        rec.grade_scale = grade_scale
        rec.text_storage_id = text_storage_id
        rec.created_at = datetime.now(UTC)
        self._anchors.append(rec)


@pytest.fixture
def admin_repo() -> AdminAnchorRepoMock:
    return AdminAnchorRepoMock()


@pytest.fixture
def settings() -> Settings:
    s = Settings()
    s.ENABLE_ADMIN_ENDPOINTS = True
    s.JWT_SECRET_KEY = SecretStr("unit-test-secret-key-with-min-32-bytes")
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
    admin_repo: AdminAnchorRepoMock,
    settings: Settings,
    correlation_context: CorrelationContext,
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
        def provide_anchor_repository(self) -> AnchorRepositoryProtocol:
            return admin_repo

        @provide(scope=Scope.REQUEST)
        def provide_correlation_context(self) -> CorrelationContext:
            return correlation_context

    container = make_async_container(TestProvider())
    QuartDishka(app=app, container=container)
    app.register_blueprint(anchors_bp)

    @app.after_serving
    async def cleanup() -> None:
        await container.close()

    return app


@pytest.fixture
async def client(admin_app: Quart) -> AsyncIterator[QuartTestClient]:  # type: ignore[override]
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
async def test_anchor_summary_requires_existing_instructions(
    client: QuartTestClient,
    admin_headers: dict[str, str],
) -> None:
    resp = await client.get(
        "/admin/v1/anchors/assignment/missing-assignment",
        headers=admin_headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_anchor_summary_filters_by_instruction_grade_scale(
    client: QuartTestClient,
    admin_headers: dict[str, str],
    admin_repo: AdminAnchorRepoMock,
) -> None:
    assignment_id = "ENG5-ANCHOR-SUMMARY-TEST"
    admin_repo.seed_instruction(assignment_id=assignment_id, grade_scale="eng5_np_legacy_9_step")
    admin_repo.seed_anchor(
        assignment_id=assignment_id,
        anchor_label="A1",
        grade="A",
        grade_scale="eng5_np_legacy_9_step",
    )
    admin_repo.seed_anchor(
        assignment_id=assignment_id,
        anchor_label="B1",
        grade="B",
        grade_scale="eng5_np_national_9_step",
    )

    resp = await client.get(
        f"/admin/v1/anchors/assignment/{assignment_id}",
        headers=admin_headers,
    )
    assert resp.status_code == 200
    payload = await resp.get_json()
    assert payload["assignment_id"] == assignment_id
    assert payload["grade_scale"] == "eng5_np_legacy_9_step"
    assert payload["anchor_count"] == 1
    assert payload["anchor_count_total"] == 2
    assert payload["anchor_count_by_scale"]["eng5_np_legacy_9_step"] == 1
    assert payload["anchor_count_by_scale"]["eng5_np_national_9_step"] == 1
    assert payload["anchors"][0]["anchor_label"] == "A1"
