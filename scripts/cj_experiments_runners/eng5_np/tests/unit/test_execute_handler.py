"""Unit tests for ExecuteHandler and EXECUTE flow."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from common_core.domain_enums import CourseCode, Language

from scripts.cj_experiments_runners.eng5_np.eng5_db_extract import Eng5DbExtractionResult
from scripts.cj_experiments_runners.eng5_np.handlers import ExecuteHandler
from scripts.cj_experiments_runners.eng5_np.inventory import (
    DirectorySnapshot,
    FileRecord,
    RunnerInventory,
)
from scripts.cj_experiments_runners.eng5_np.paths import RunnerPaths
from scripts.cj_experiments_runners.eng5_np.protocols import ModeHandlerProtocol
from scripts.cj_experiments_runners.eng5_np.settings import (
    RunnerMode,
    RunnerSettings,
)


def _make_settings(tmp_path: Path) -> RunnerSettings:
    """Create RunnerSettings for EXECUTE mode tests."""
    return RunnerSettings(
        assignment_id=uuid.UUID("00000000-0000-0000-0000-000000000031"),
        cj_assignment_id=uuid.UUID("00000000-0000-0000-0000-000000000031"),
        course_id=uuid.UUID("00000000-0000-0000-0000-000000000032"),
        grade_scale="eng5_np_legacy_9_step",
        mode=RunnerMode.EXECUTE,
        use_kafka=True,
        output_dir=tmp_path,
        runner_version="test-1.0.0",
        git_sha="test-sha",
        batch_uuid=uuid.UUID("00000000-0000-0000-0000-000000000033"),
        batch_id="TEST-BATCH-EXECUTE",
        user_id="test-user",
        org_id=None,
        course_code=CourseCode.ENG5,
        language=Language.ENGLISH,
        correlation_id=uuid.UUID("00000000-0000-0000-0000-000000000034"),
        kafka_bootstrap="localhost:9092",
        kafka_client_id="test-client",
        content_service_url="http://localhost:8000",
        cj_service_url="http://localhost:9095",
        cj_anchor_count=12,
    )


def _make_inventory(tmp_path: Path) -> RunnerInventory:
    """Create RunnerInventory with anchors and students."""
    instructions = FileRecord(path=tmp_path / "instructions.md", exists=True)
    prompt = FileRecord(path=tmp_path / "prompt.md", exists=True)
    anchors_csv = FileRecord(path=tmp_path / "anchors.csv", exists=True)
    anchors_xlsx = FileRecord(path=tmp_path / "anchors.xlsx", exists=True)

    anchor_files = [
        FileRecord(
            path=tmp_path / "anchors" / "anchor_001.docx",
            exists=True,
            checksum="anchor-checksum-1",
        )
    ]
    student_files = [
        FileRecord(
            path=tmp_path / "students" / "student_001.docx",
            exists=True,
            checksum="student-checksum-1",
        )
    ]

    anchor_docs = DirectorySnapshot(root=tmp_path / "anchors", files=anchor_files)
    student_docs = DirectorySnapshot(root=tmp_path / "students", files=student_files)

    return RunnerInventory(
        instructions=instructions,
        prompt=prompt,
        anchors_csv=anchors_csv,
        anchors_xlsx=anchors_xlsx,
        anchor_docs=anchor_docs,
        student_docs=student_docs,
    )


def _make_paths(tmp_path: Path) -> RunnerPaths:
    return RunnerPaths(
        repo_root=tmp_path,
        role_models_root=tmp_path,
        instructions_path=tmp_path / "instructions.md",
        prompt_path=tmp_path / "prompt.md",
        anchors_csv=tmp_path / "anchors.csv",
        anchors_xlsx=tmp_path / "anchors.xlsx",
        anchor_docs_dir=tmp_path / "anchors",
        student_docs_dir=tmp_path / "students",
        schema_path=tmp_path / "schema.json",
        artefact_output_dir=tmp_path,
    )


class TestExecuteHandlerProtocol:
    """Contract tests for ExecuteHandler protocol compliance."""

    def test_execute_handler_implements_mode_handler_protocol(self) -> None:
        """ExecuteHandler instances satisfy ModeHandlerProtocol at runtime."""
        handler = ExecuteHandler()
        assert isinstance(handler, ModeHandlerProtocol)


class TestExecuteHandlerExecute:
    """Behavioral tests for ExecuteHandler.execute."""

    def test_execute_happy_path_calls_dependencies_and_returns_zero(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """EXECUTE mode orchestrates uploads, request composition and publish."""
        settings = _make_settings(tmp_path)
        settings.await_completion = True
        inventory = _make_inventory(tmp_path)

        schema_path = tmp_path / "schema.json"
        artefact_path = tmp_path / "assessment_run.execute.json"

        calls: dict[str, object] = {}

        def fake_ensure_execute_requirements(inv: RunnerInventory, *, require_prompt: bool) -> None:
            calls["ensure_execute_requirements_inventory"] = inv
            calls["ensure_execute_requirements_require_prompt"] = require_prompt

        def fake_ensure_schema_available(path: Path) -> dict:
            calls["schema_path"] = path
            return {"$id": "test-schema"}

        def fake_write_stub_artefact(
            *,
            settings: RunnerSettings,
            inventory: RunnerInventory,
            schema: dict,
        ) -> Path:
            calls["stub_settings_mode"] = settings.mode
            calls["stub_schema"] = schema
            return artefact_path

        async def fake_upload_essays_parallel(records, content_service_url: str):
            calls["upload_records"] = records
            calls["upload_url"] = content_service_url
            # Map checksums to storage IDs
            return {r.checksum: f"storage-{idx}" for idx, r in enumerate(records)}

        def fake_build_essay_refs(
            *,
            anchors,
            students,
            max_comparisons,
            storage_id_map,
            student_id_factory=None,
        ):
            calls["essay_refs_anchors"] = anchors
            calls["essay_refs_students"] = students
            calls["essay_refs_storage_map"] = storage_id_map
            return ["ref-1"]

        def fake_upload_prompt(
            self, inventory: RunnerInventory, settings: RunnerSettings
        ) -> str | None:  # noqa: D401
            raise AssertionError(
                "ExecuteHandler must not upload prompts when cj_assignment_id is set "
                "(assignment-owned prompt/rubric)."
            )

        def fake_build_prompt_reference(_prompt, storage_id: str | None):
            raise AssertionError("build_prompt_reference should not be invoked for assignment runs")

        def fake_compose_cj_assessment_request(
            *,
            settings: RunnerSettings,
            essay_refs,
            prompt_reference,
        ):
            calls["compose_settings_mode"] = settings.mode
            calls["compose_essay_refs"] = essay_refs
            calls["compose_prompt_ref"] = prompt_reference
            return {"type": "ELS_CJAssessmentRequestV1"}

        def fake_write_cj_request_envelope(
            *,
            envelope,
            output_dir: Path,
        ) -> Path:
            calls["request_envelope"] = envelope
            calls["request_output_dir"] = output_dir
            return tmp_path / "request.json"

        async def fake_run_publish_and_capture(
            *,
            envelope,
            settings: RunnerSettings,
            hydrator,
        ):
            calls["published_envelope"] = envelope
            calls["published_settings_mode"] = settings.mode
            calls["published_hydrator"] = hydrator

        def fake_load_artefact_data(path: Path) -> dict:
            calls["loaded_artefact_path"] = path
            return {"validation": {"ok": True}}

        def fake_print_run_summary(path: Path) -> dict:
            calls["print_run_summary_path"] = path
            return {"summary": True}

        def fake_print_batching_metrics_hints(*, llm_batching_mode_hint: str | None) -> None:
            calls["batching_hint"] = llm_batching_mode_hint

        def fake_log_validation_state(
            *,
            logger,
            artefact_path: Path,
            artefact_data: dict,
        ) -> None:
            calls["logged_artefact_path"] = artefact_path
            calls["logged_artefact_data"] = artefact_data

        class DummyHydrator:
            def __init__(self, *args, **kwargs) -> None:  # pragma: no cover - trivial
                pass

            def runner_status(self) -> dict:
                return {"status": "ok"}

        # Patch dependencies used inside ExecuteHandler.execute
        monkeypatch.setattr(
            "scripts.cj_experiments_runners.eng5_np.handlers.execute_handler.ensure_execute_requirements",
            fake_ensure_execute_requirements,
        )
        monkeypatch.setattr(
            "scripts.cj_experiments_runners.eng5_np.handlers.execute_handler.ensure_schema_available",
            fake_ensure_schema_available,
        )
        monkeypatch.setattr(
            "scripts.cj_experiments_runners.eng5_np.handlers.execute_handler.write_stub_artefact",
            fake_write_stub_artefact,
        )
        monkeypatch.setattr(
            "scripts.cj_experiments_runners.eng5_np.handlers.execute_handler.upload_essays_parallel",
            fake_upload_essays_parallel,
        )
        monkeypatch.setattr(
            "scripts.cj_experiments_runners.eng5_np.handlers.execute_handler.build_essay_refs",
            fake_build_essay_refs,
        )
        monkeypatch.setattr(
            "scripts.cj_experiments_runners.eng5_np.handlers.execute_handler.ExecuteHandler._upload_prompt",
            fake_upload_prompt,
        )
        monkeypatch.setattr(
            "scripts.cj_experiments_runners.eng5_np.handlers.execute_handler.build_prompt_reference",
            fake_build_prompt_reference,
        )
        monkeypatch.setattr(
            "scripts.cj_experiments_runners.eng5_np.handlers.execute_handler.compose_cj_assessment_request",
            fake_compose_cj_assessment_request,
        )
        monkeypatch.setattr(
            "scripts.cj_experiments_runners.eng5_np.handlers.execute_handler.write_cj_request_envelope",
            fake_write_cj_request_envelope,
        )
        monkeypatch.setattr(
            "scripts.cj_experiments_runners.eng5_np.handlers.execute_handler.run_publish_and_capture",
            fake_run_publish_and_capture,
        )
        monkeypatch.setattr(
            "scripts.cj_experiments_runners.eng5_np.handlers.execute_handler.print_run_summary",
            fake_print_run_summary,
        )
        monkeypatch.setattr(
            "scripts.cj_experiments_runners.eng5_np.handlers.execute_handler.print_batching_metrics_hints",
            fake_print_batching_metrics_hints,
        )
        monkeypatch.setattr(
            "scripts.cj_experiments_runners.eng5_np.handlers.execute_handler.load_artefact_data",
            fake_load_artefact_data,
        )
        monkeypatch.setattr(
            "scripts.cj_experiments_runners.eng5_np.handlers.execute_handler.log_validation_state",
            fake_log_validation_state,
        )
        monkeypatch.setattr(
            "scripts.cj_experiments_runners.eng5_np.handlers.execute_handler.AssessmentRunHydrator",
            DummyHydrator,
        )

        handler = ExecuteHandler()
        exit_code = handler.execute(
            settings=settings,
            inventory=inventory,
            paths=_make_paths(tmp_path),
        )

        assert exit_code == 0

        # Preconditions and schema
        assert calls["ensure_execute_requirements_inventory"] is inventory
        assert calls["ensure_execute_requirements_require_prompt"] is False
        assert calls["schema_path"] == schema_path
        assert calls["stub_settings_mode"] == RunnerMode.EXECUTE

        # Execute is student-only: anchors list passed to build_essay_refs is empty.
        assert calls["essay_refs_anchors"] == []
        assert calls["compose_prompt_ref"] is None

    def test_execute_runs_db_extraction_when_auto_flag_set(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        settings = _make_settings(tmp_path)
        settings.await_completion = True
        settings.auto_extract_eng5_db = True
        inventory = _make_inventory(tmp_path)

        artefact_path = tmp_path / "assessment_run.execute.json"
        calls: dict[str, object] = {}

        def fake_ensure_schema_available(_path: Path) -> dict:
            return {"$id": "test-schema"}

        def fake_write_stub_artefact(
            *, settings: RunnerSettings, inventory: RunnerInventory, schema: dict
        ) -> Path:  # noqa: E501
            return artefact_path

        async def fake_upload_essays_parallel(records, content_service_url: str):
            return {r.checksum: "storage-1" for r in records}

        def fake_build_essay_refs(
            *, anchors, students, max_comparisons, storage_id_map, student_id_factory=None
        ):  # noqa: E501
            return ["ref-1"]

        def fake_upload_prompt(
            self, inventory: RunnerInventory, settings: RunnerSettings
        ) -> str | None:  # noqa: D401,E501
            raise AssertionError("ExecuteHandler must not upload prompts for assignment runs")

        def fake_build_prompt_reference(_prompt, storage_id: str | None):
            raise AssertionError("build_prompt_reference should not be invoked for assignment runs")

        def fake_compose_cj_assessment_request(
            *, settings: RunnerSettings, essay_refs, prompt_reference
        ):  # noqa: E501
            return {"type": "ELS_CJAssessmentRequestV1"}

        def fake_write_cj_request_envelope(*, envelope, output_dir: Path) -> Path:
            return tmp_path / "request.json"

        async def fake_run_publish_and_capture(*, envelope, settings: RunnerSettings, hydrator):
            return None

        def fake_run_eng5_db_extraction(
            *, batch_identifier: str, output_dir: Path, output_format: str = "text"
        ):  # noqa: E501
            calls["extraction_batch_identifier"] = batch_identifier
            return Eng5DbExtractionResult(
                batch_identifier=batch_identifier,
                output_path=output_dir / "out.txt",
                output_format=output_format,
                exit_code=0,
                error=None,
            )

        class DummyHydrator:
            def __init__(self, *args, **kwargs) -> None:  # pragma: no cover - trivial
                pass

            def runner_status(self) -> dict:
                return {"observed_events": {"completions": 1}}

            def update_post_run(self, *, key: str, payload: dict) -> None:
                calls["post_run_key"] = key
                calls["post_run_payload"] = payload

        monkeypatch.setattr(
            "scripts.cj_experiments_runners.eng5_np.handlers.execute_handler.ensure_execute_requirements",
            lambda *_args, **_kwargs: None,
        )
        monkeypatch.setattr(
            "scripts.cj_experiments_runners.eng5_np.handlers.execute_handler.ensure_schema_available",
            fake_ensure_schema_available,
        )
        monkeypatch.setattr(
            "scripts.cj_experiments_runners.eng5_np.handlers.execute_handler.write_stub_artefact",
            fake_write_stub_artefact,
        )
        monkeypatch.setattr(
            "scripts.cj_experiments_runners.eng5_np.handlers.execute_handler.upload_essays_parallel",
            fake_upload_essays_parallel,
        )
        monkeypatch.setattr(
            "scripts.cj_experiments_runners.eng5_np.handlers.execute_handler.build_essay_refs",
            fake_build_essay_refs,
        )
        monkeypatch.setattr(
            "scripts.cj_experiments_runners.eng5_np.handlers.execute_handler.ExecuteHandler._upload_prompt",
            fake_upload_prompt,
        )
        monkeypatch.setattr(
            "scripts.cj_experiments_runners.eng5_np.handlers.execute_handler.build_prompt_reference",
            fake_build_prompt_reference,
        )
        monkeypatch.setattr(
            "scripts.cj_experiments_runners.eng5_np.handlers.execute_handler.compose_cj_assessment_request",
            fake_compose_cj_assessment_request,
        )
        monkeypatch.setattr(
            "scripts.cj_experiments_runners.eng5_np.handlers.execute_handler.write_cj_request_envelope",
            fake_write_cj_request_envelope,
        )
        monkeypatch.setattr(
            "scripts.cj_experiments_runners.eng5_np.handlers.execute_handler.run_publish_and_capture",
            fake_run_publish_and_capture,
        )
        monkeypatch.setattr(
            "scripts.cj_experiments_runners.eng5_np.handlers.execute_handler.AssessmentRunHydrator",
            DummyHydrator,
        )
        monkeypatch.setattr(
            "scripts.cj_experiments_runners.eng5_np.handlers.execute_handler.run_eng5_db_extraction",
            fake_run_eng5_db_extraction,
        )
        monkeypatch.setattr(
            "scripts.cj_experiments_runners.eng5_np.handlers.execute_handler.load_artefact_data",
            lambda _path: {"validation": {"ok": True}},
        )

        handler = ExecuteHandler()
        exit_code = handler.execute(
            settings=settings, inventory=inventory, paths=_make_paths(tmp_path)
        )
        assert exit_code == 0
        assert calls["post_run_key"] == "eng5_db_extract"
        assert calls["extraction_batch_identifier"] == str(settings.batch_uuid)

    def test_execute_returns_two_when_db_extraction_fails(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        settings = _make_settings(tmp_path)
        settings.await_completion = True
        settings.auto_extract_eng5_db = True
        inventory = _make_inventory(tmp_path)

        async def fake_upload_essays_parallel(*, records, content_service_url: str):  # noqa: ARG001
            return {r.checksum: "storage-1" for r in records}

        async def fake_run_publish_and_capture(*_args, **_kwargs):
            return None

        def fake_run_eng5_db_extraction(
            *,
            batch_identifier: str,
            output_dir: Path,
            output_format: str = "text",
        ) -> Eng5DbExtractionResult:
            return Eng5DbExtractionResult(
                batch_identifier=batch_identifier,
                output_path=output_dir / "out.txt",
                output_format=output_format,
                exit_code=1,
                error="boom",
            )

        class DummyHydrator:
            def __init__(self, *args, **kwargs) -> None:  # pragma: no cover - trivial
                pass

            def runner_status(self) -> dict:
                return {"observed_events": {"completions": 1}}

            def update_post_run(self, *, key: str, payload: dict) -> None:
                return None

        monkeypatch.setattr(
            "scripts.cj_experiments_runners.eng5_np.handlers.execute_handler.ensure_execute_requirements",
            lambda *_args, **_kwargs: None,
        )
        monkeypatch.setattr(
            "scripts.cj_experiments_runners.eng5_np.handlers.execute_handler.ensure_schema_available",
            lambda _path: {"$id": "test-schema"},
        )
        monkeypatch.setattr(
            "scripts.cj_experiments_runners.eng5_np.handlers.execute_handler.write_stub_artefact",
            lambda **_kwargs: tmp_path / "assessment_run.execute.json",
        )
        monkeypatch.setattr(
            "scripts.cj_experiments_runners.eng5_np.handlers.execute_handler.upload_essays_parallel",
            fake_upload_essays_parallel,
        )
        monkeypatch.setattr(
            "scripts.cj_experiments_runners.eng5_np.handlers.execute_handler.build_essay_refs",
            lambda **_kwargs: ["ref-1"],
        )
        monkeypatch.setattr(
            "scripts.cj_experiments_runners.eng5_np.handlers.execute_handler.ExecuteHandler._upload_prompt",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                AssertionError("ExecuteHandler must not upload prompts for assignment runs")
            ),
        )
        monkeypatch.setattr(
            "scripts.cj_experiments_runners.eng5_np.handlers.execute_handler.build_prompt_reference",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                AssertionError("build_prompt_reference should not be invoked for assignment runs")
            ),
        )
        monkeypatch.setattr(
            "scripts.cj_experiments_runners.eng5_np.handlers.execute_handler.compose_cj_assessment_request",
            lambda **_kwargs: {"type": "ELS_CJAssessmentRequestV1"},
        )
        monkeypatch.setattr(
            "scripts.cj_experiments_runners.eng5_np.handlers.execute_handler.write_cj_request_envelope",
            lambda **_kwargs: tmp_path / "request.json",
        )
        monkeypatch.setattr(
            "scripts.cj_experiments_runners.eng5_np.handlers.execute_handler.run_publish_and_capture",
            fake_run_publish_and_capture,
        )
        monkeypatch.setattr(
            "scripts.cj_experiments_runners.eng5_np.handlers.execute_handler.AssessmentRunHydrator",
            DummyHydrator,
        )
        monkeypatch.setattr(
            "scripts.cj_experiments_runners.eng5_np.handlers.execute_handler.run_eng5_db_extraction",
            fake_run_eng5_db_extraction,
        )
        monkeypatch.setattr(
            "scripts.cj_experiments_runners.eng5_np.handlers.execute_handler.load_artefact_data",
            lambda _path: {"validation": {"ok": True}},
        )

        handler = ExecuteHandler()
        exit_code = handler.execute(
            settings=settings, inventory=inventory, paths=_make_paths(tmp_path)
        )
        assert exit_code == 2
