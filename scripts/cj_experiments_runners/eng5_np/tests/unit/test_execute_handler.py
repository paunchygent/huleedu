"""Unit tests for ExecuteHandler and EXECUTE flow."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from common_core.domain_enums import CourseCode, Language

from scripts.cj_experiments_runners.eng5_np.cj_client import AnchorRegistrationError
from scripts.cj_experiments_runners.eng5_np.handlers import ExecuteHandler
from scripts.cj_experiments_runners.eng5_np.inventory import (
    DirectorySnapshot,
    FileRecord,
    RunnerInventory,
)
from scripts.cj_experiments_runners.eng5_np.protocols import ModeHandlerProtocol
from scripts.cj_experiments_runners.eng5_np.settings import (
    RunnerMode,
    RunnerSettings,
)


def _make_settings(tmp_path: Path) -> RunnerSettings:
    """Create RunnerSettings for EXECUTE mode tests."""
    return RunnerSettings(
        assignment_id=uuid.UUID("00000000-0000-0000-0000-000000000031"),
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


class TestExecuteHandlerProtocol:
    """Contract tests for ExecuteHandler protocol compliance."""

    def test_execute_handler_implements_mode_handler_protocol(self) -> None:
        """ExecuteHandler instances satisfy ModeHandlerProtocol at runtime."""
        handler = ExecuteHandler()
        assert isinstance(handler, ModeHandlerProtocol)


class TestValidateExecuteRequirements:
    """Tests for _validate_execute_requirements guardrails."""

    def test_raises_when_no_anchors(self, tmp_path: Path) -> None:
        settings = _make_settings(tmp_path)
        handler = ExecuteHandler()

        anchors: list[FileRecord] = []
        students = [FileRecord(path=tmp_path / "students" / "s1.docx", exists=True)]

        with pytest.raises(RuntimeError) as exc:
            handler._validate_execute_requirements(
                settings=settings, anchors=anchors, students=students
            )
        assert "Anchor essays are required" in str(exc.value)

    def test_raises_when_no_students(self, tmp_path: Path) -> None:
        settings = _make_settings(tmp_path)
        handler = ExecuteHandler()

        anchors = [FileRecord(path=tmp_path / "anchors" / "a1.docx", exists=True)]
        students: list[FileRecord] = []

        with pytest.raises(RuntimeError) as exc:
            handler._validate_execute_requirements(
                settings=settings, anchors=anchors, students=students
            )
        assert "No essays available for upload" in str(exc.value)

    def test_raises_when_missing_cj_service_url(self, tmp_path: Path) -> None:
        settings = _make_settings(tmp_path)
        settings.cj_service_url = None
        handler = ExecuteHandler()

        anchors = [FileRecord(path=tmp_path / "anchors" / "a1.docx", exists=True)]
        students = [FileRecord(path=tmp_path / "students" / "s1.docx", exists=True)]

        with pytest.raises(RuntimeError) as exc:
            handler._validate_execute_requirements(
                settings=settings, anchors=anchors, students=students
            )
        assert "CJ service URL is required" in str(exc.value)


class TestRegisterAnchors:
    """Tests for internal _register_anchors helper."""

    def test_register_anchors_raises_on_anchor_registration_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        settings = _make_settings(tmp_path)
        handler = ExecuteHandler()

        async def failing_register_anchor_essays(*_args, **_kwargs):
            raise AnchorRegistrationError("boom")

        monkeypatch.setattr(
            "scripts.cj_experiments_runners.eng5_np.handlers.execute_handler.register_anchor_essays",
            failing_register_anchor_essays,
        )

        with pytest.raises(RuntimeError) as exc:
            handler._register_anchors(
                anchors=[FileRecord(path=tmp_path / "anchors" / "a1.docx", exists=True)],
                settings=settings,
            )
        assert "Anchor registration failed" in str(exc.value)

    def test_register_anchors_raises_on_empty_result(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        settings = _make_settings(tmp_path)
        handler = ExecuteHandler()

        async def register_anchor_essays_empty(*_args, **_kwargs):
            return []

        monkeypatch.setattr(
            "scripts.cj_experiments_runners.eng5_np.handlers.execute_handler.register_anchor_essays",
            register_anchor_essays_empty,
        )

        with pytest.raises(RuntimeError) as exc:
            handler._register_anchors(
                anchors=[FileRecord(path=tmp_path / "anchors" / "a1.docx", exists=True)],
                settings=settings,
            )
        assert "Anchor registration returned no results" in str(exc.value)

    def test_register_anchors_returns_results_on_success(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        settings = _make_settings(tmp_path)
        handler = ExecuteHandler()

        async def register_anchor_essays_ok(*_args, **_kwargs):
            return [{"anchor_id": "anchor_001"}]

        monkeypatch.setattr(
            "scripts.cj_experiments_runners.eng5_np.handlers.execute_handler.register_anchor_essays",
            register_anchor_essays_ok,
        )

        result = handler._register_anchors(
            anchors=[FileRecord(path=tmp_path / "anchors" / "a1.docx", exists=True)],
            settings=settings,
        )
        assert result == [{"anchor_id": "anchor_001"}]


class TestExecuteHandlerExecute:
    """Behavioral tests for ExecuteHandler.execute."""

    def test_execute_happy_path_calls_dependencies_and_returns_zero(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """EXECUTE mode orchestrates anchors, uploads, request composition and publish."""
        settings = _make_settings(tmp_path)
        settings.await_completion = True
        inventory = _make_inventory(tmp_path)

        schema_path = tmp_path / "schema.json"
        artefact_path = tmp_path / "assessment_run.execute.json"

        calls: dict[str, object] = {}

        def fake_ensure_execute_requirements(inv: RunnerInventory) -> None:
            calls["ensure_execute_requirements_inventory"] = inv

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

        def fake_register_anchors(
            self,
            anchors,
            settings: RunnerSettings,
        ):
            calls["registered_anchors"] = anchors
            calls["registered_settings_mode"] = settings.mode
            return [{"anchor_id": "anchor_001"}]

        def fake_upload_prompt(
            self, inventory: RunnerInventory, settings: RunnerSettings
        ) -> str | None:  # noqa: D401
            """Fake prompt upload."""
            calls["upload_prompt_inventory"] = inventory
            calls["upload_prompt_settings_mode"] = settings.mode
            return "prompt-storage-id"

        def fake_build_prompt_reference(_prompt, storage_id: str | None):
            calls["prompt_storage_id"] = storage_id
            return {"storage_id": storage_id}

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
            "scripts.cj_experiments_runners.eng5_np.handlers.execute_handler.ExecuteHandler._register_anchors",
            fake_register_anchors,
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

        class DummyPaths:
            """Minimal paths object exposing schema_path."""

            def __init__(self, schema: Path) -> None:
                self.schema_path = schema

        handler = ExecuteHandler()
        exit_code = handler.execute(
            settings=settings,
            inventory=inventory,
            paths=DummyPaths(schema_path),  # type: ignore[arg-type]
        )

        assert exit_code == 0

        # Preconditions and schema
        assert calls["ensure_execute_requirements_inventory"] is inventory
        assert calls["schema_path"] == schema_path
        assert calls["stub_settings_mode"] == RunnerMode.EXECUTE
        assert calls["stub_schema"] == {"$id": "test-schema"}

        # Uploads and refs
        upload_records = calls["upload_records"]
        assert len(upload_records) == 1
        assert calls["upload_url"] == settings.content_service_url
        assert calls["essay_refs_anchors"] == []
        assert len(calls["essay_refs_students"]) == 1

        # Prompt handling and request composition
        assert calls["prompt_storage_id"] == "prompt-storage-id"
        assert calls["compose_settings_mode"] == RunnerMode.EXECUTE
        assert calls["compose_essay_refs"] == ["ref-1"]
        assert calls["compose_prompt_ref"] == {"storage_id": "prompt-storage-id"}

        # Publish & validation logging
        assert calls["published_envelope"]["type"] == "ELS_CJAssessmentRequestV1"
        assert calls["published_settings_mode"] == RunnerMode.EXECUTE
        assert calls["logged_artefact_path"] == artefact_path
        assert calls["loaded_artefact_path"] == artefact_path
