"""
Integration test: End-to-end student prompt flow
(admin upload -> CLI retrieval -> batch auto-hydration).

- Uses real PostgreSQL via testcontainers (postgres_repository fixture)
- Mocks external services (Content Service) at protocol level
- Exercises HTTP (admin endpoints), Typer CLI (prompts get), and batch preparation
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from dishka import Provider, Scope, make_async_container, provide
from huleedu_service_libs.error_handling.correlation import CorrelationContext
from huleedu_service_libs.error_handling.quart import register_error_handlers
from quart import Quart
from quart_dishka import QuartDishka
from typer.testing import CliRunner

from services.cj_assessment_service import cli_admin
from services.cj_assessment_service.api.admin import common as admin_common
from services.cj_assessment_service.api.admin import student_prompts_bp
from services.cj_assessment_service.cj_core_logic.batch_preparation import create_cj_batch
from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.models_api import CJAssessmentRequestData, EssayToProcess
from services.cj_assessment_service.protocols import (
    AssessmentInstructionRepositoryProtocol,
    CJBatchRepositoryProtocol,
    ContentClientProtocol,
    SessionProviderProtocol,
)
from services.cj_assessment_service.tests.fixtures.database_fixtures import PostgresDataAccess


def _patch_decode(monkeypatch: pytest.MonkeyPatch) -> None:
    """Bypass admin JWT validation in tests."""
    from huleedu_service_libs import auth as auth_module

    def fake_decode(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {"sub": "admin-user", "roles": ["admin"]}

    # Patch both the shared auth helper and the global auth module
    monkeypatch.setattr(admin_common, "decode_and_validate_jwt", fake_decode)
    monkeypatch.setattr(auth_module, "decode_and_validate_jwt", fake_decode)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_student_prompt_workflow_end_to_end(
    postgres_data_access: PostgresDataAccess,
    postgres_session_provider: SessionProviderProtocol,
    postgres_batch_repository: CJBatchRepositoryProtocol,
    postgres_instruction_repository: AssessmentInstructionRepositoryProtocol,
    mock_content_client: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # --- Build admin app (Quart + Dishka) using real repository and mocked content client ---
    app = Quart(__name__)
    settings = Settings()
    settings.ENABLE_ADMIN_ENDPOINTS = True
    app.config["settings"] = settings
    register_error_handlers(app)

    class TestProvider(Provider):
        @provide(scope=Scope.REQUEST)
        def provide_session_provider(self) -> SessionProviderProtocol:  # type: ignore[override]
            return postgres_session_provider

        @provide(scope=Scope.REQUEST)
        def provide_instruction_repository(
            self,
        ) -> AssessmentInstructionRepositoryProtocol:  # type: ignore[override]
            return postgres_instruction_repository

        @provide(scope=Scope.REQUEST)
        def provide_content_client(self) -> ContentClientProtocol:  # type: ignore[override]
            return mock_content_client

        @provide(scope=Scope.REQUEST)
        def provide_correlation(self) -> CorrelationContext:  # type: ignore[override]
            return CorrelationContext(original=str(uuid4()), uuid=uuid4(), source="generated")

    container = make_async_container(TestProvider())
    QuartDishka(
        app=app, container=container
    )  # DI must be initialized before blueprint registration
    app.register_blueprint(student_prompts_bp)

    _patch_decode(monkeypatch)

    # --- Seed AssessmentInstruction without a prompt ---
    assignment_id = "assignment-itg-1"
    async with postgres_session_provider.session() as session:
        await postgres_data_access.upsert_assessment_instruction(
            session=session,
            assignment_id=assignment_id,
            course_id=None,
            instructions_text="Judge clarity concisely",
            grade_scale="swedish_8_anchor",
            student_prompt_storage_id=None,
        )
        # Commit so the admin HTTP surface can see this instruction via a new session
        await session.commit()

    # Prepare Content Service mocks for upload + retrieval
    uploaded_storage_id = "uploaded-storage-001"
    mock_content_client.store_content = AsyncMock(return_value={"content_id": uploaded_storage_id})
    mock_content_client.fetch_content = AsyncMock(return_value="Fetched prompt text for assignment")

    # --- Admin upload via HTTP ---
    async with app.test_client() as client:
        upload_resp = await client.post(
            "/admin/v1/student-prompts",
            headers={"Authorization": "Bearer token"},
            json={"assignment_id": assignment_id, "prompt_text": "Prompt body to store"},
        )
        assert upload_resp.status_code == 200
        upload_payload = await upload_resp.get_json()
        assert upload_payload["assignment_id"] == assignment_id
        assert upload_payload["student_prompt_storage_id"] == uploaded_storage_id

        # Verify instruction now carries the storage-by-reference
        async with postgres_session_provider.session() as session:
            instruction = await postgres_data_access.get_assessment_instruction(
                session=session,
                assignment_id=assignment_id,
                course_id=None,
            )
            assert instruction is not None
            assert instruction.student_prompt_storage_id == uploaded_storage_id

        # --- CLI retrieval (Typer) using the same storage ID ---
        # Fetch via HTTP to get realistic payload, then feed it to CLI by patching _admin_request
        get_resp = await client.get(
            f"/admin/v1/student-prompts/assignment/{assignment_id}",
            headers={"Authorization": "Bearer token"},
        )
        assert get_resp.status_code == 200
        cli_payload = await get_resp.get_json()
        assert cli_payload["student_prompt_storage_id"] == uploaded_storage_id

        runner = CliRunner()

        def fake_admin_request(method: str, path: str, json_body: Any | None = None) -> Any:
            # The CLI will call GET /student-prompts/assignment/<assignment_id>
            assert method.upper() == "GET"
            assert path.endswith(f"/student-prompts/assignment/{assignment_id}")
            return cli_payload

        monkeypatch.setattr(cli_admin, "_admin_request", fake_admin_request)

        result = runner.invoke(cli_admin.app, ["prompts", "get", assignment_id])
        assert result.exit_code == 0
        # CLI output should reflect the storage ID and the fetched prompt text
        assert "Student Prompt Details" in result.stdout
        assert f"Storage ID: {uploaded_storage_id}" in result.stdout
        assert "Fetched prompt text for assignment" in result.stdout

    # --- Batch auto-hydration: omit student_prompt_storage_id and expect copy from instruction ---
    request_data_hydrate = CJAssessmentRequestData(
        bos_batch_id="bos-batch-hydrate-1",
        language="en",
        course_code="ENG5",
        essays_to_process=[
            EssayToProcess(els_essay_id="essay-1", text_storage_id="storage-1"),
            EssayToProcess(els_essay_id="essay-2", text_storage_id="storage-2"),
        ],
        assignment_id=assignment_id,
        # IMPORTANT: student_prompt_storage_id omitted to trigger hydration
    )

    cj_batch_id_hydrated = await create_cj_batch(
        request_data=request_data_hydrate,
        correlation_id=uuid4(),
        session_provider=postgres_session_provider,
        batch_repository=postgres_batch_repository,
        instruction_repository=postgres_instruction_repository,
        content_client=mock_content_client,
        log_extra={"test": "student_prompt_integration"},
    )

    async with postgres_session_provider.session() as session:
        hydrated_batch = await postgres_data_access.get_cj_batch_upload(
            session=session,
            cj_batch_id=cj_batch_id_hydrated,
        )
        assert hydrated_batch is not None
        assert hydrated_batch.assignment_id == assignment_id
        assert hydrated_batch.processing_metadata is not None
        assert (
            hydrated_batch.processing_metadata.get("student_prompt_storage_id")
            == uploaded_storage_id
        )

    # --- Explicit storage ID should bypass hydration and remain intact ---
    explicit_storage_id = "explicit-storage-999"
    request_data_explicit = CJAssessmentRequestData(
        bos_batch_id="bos-batch-explicit-1",
        language="en",
        course_code="ENG5",
        essays_to_process=[
            EssayToProcess(els_essay_id="essay-3", text_storage_id="storage-3"),
            EssayToProcess(els_essay_id="essay-4", text_storage_id="storage-4"),
        ],
        assignment_id=assignment_id,  # present, but explicit prompt provided should win
        student_prompt_storage_id=explicit_storage_id,
        student_prompt_text="Explicit prompt provided by client",
    )

    cj_batch_id_explicit = await create_cj_batch(
        request_data=request_data_explicit,
        correlation_id=uuid4(),
        session_provider=postgres_session_provider,
        batch_repository=postgres_batch_repository,
        instruction_repository=postgres_instruction_repository,
        content_client=mock_content_client,
        log_extra={"test": "student_prompt_integration"},
    )

    async with postgres_session_provider.session() as session:
        explicit_batch = await postgres_data_access.get_cj_batch_upload(
            session=session,
            cj_batch_id=cj_batch_id_explicit,
        )
        assert explicit_batch is not None
        assert explicit_batch.assignment_id == assignment_id
        assert explicit_batch.processing_metadata is not None
        assert (
            explicit_batch.processing_metadata.get("student_prompt_storage_id")
            == explicit_storage_id
        )
        assert (
            explicit_batch.processing_metadata.get("student_prompt_text")
            == "Explicit prompt provided by client"
        )

    # Verify Content Service upload was called exactly once during admin upload
    assert mock_content_client.store_content.await_count == 1
