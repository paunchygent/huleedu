"""Unit tests for DryRunHandler behavior and protocol compliance."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from common_core.domain_enums import CourseCode, Language

from scripts.cj_experiments_runners.eng5_np.handlers import DryRunHandler
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
    """Create minimal RunnerSettings for DRY_RUN mode tests."""
    return RunnerSettings(
        assignment_id=uuid.UUID("00000000-0000-0000-0000-000000000011"),
        course_id=uuid.UUID("00000000-0000-0000-0000-000000000012"),
        grade_scale="eng5_np_legacy_9_step",
        mode=RunnerMode.DRY_RUN,
        use_kafka=False,
        output_dir=tmp_path,
        runner_version="test-1.0.0",
        git_sha="test-sha",
        batch_uuid=uuid.UUID("00000000-0000-0000-0000-000000000013"),
        batch_id="TEST-BATCH-DRY",
        user_id="test-user",
        org_id=None,
        course_code=CourseCode.ENG5,
        language=Language.ENGLISH,
        correlation_id=uuid.UUID("00000000-0000-0000-0000-000000000014"),
        kafka_bootstrap="localhost:9092",
        kafka_client_id="test-client",
        content_service_url="http://localhost:8000",
    )


def _make_inventory(tmp_path: Path) -> RunnerInventory:
    """Create a small RunnerInventory for DRY_RUN tests."""
    instructions = FileRecord(path=tmp_path / "instructions.md", exists=True)
    prompt = FileRecord(path=tmp_path / "prompt.md", exists=True)
    anchors_csv = FileRecord(path=tmp_path / "anchors.csv", exists=True)
    anchors_xlsx = FileRecord(path=tmp_path / "anchors.xlsx", exists=True)

    anchor_file = FileRecord(path=tmp_path / "anchors" / "a1.docx", exists=True)
    student_file = FileRecord(path=tmp_path / "students" / "s1.docx", exists=True)

    anchor_docs = DirectorySnapshot(root=tmp_path / "anchors", files=[anchor_file])
    student_docs = DirectorySnapshot(root=tmp_path / "students", files=[student_file])

    return RunnerInventory(
        instructions=instructions,
        prompt=prompt,
        anchors_csv=anchors_csv,
        anchors_xlsx=anchors_xlsx,
        anchor_docs=anchor_docs,
        student_docs=student_docs,
    )


class TestDryRunHandlerProtocol:
    """Contract tests for DryRunHandler protocol compliance."""

    def test_dry_run_handler_implements_mode_handler_protocol(self) -> None:
        """DryRunHandler instances satisfy ModeHandlerProtocol at runtime."""
        handler = DryRunHandler()
        assert isinstance(handler, ModeHandlerProtocol)


class TestDryRunHandlerExecute:
    """Behavioral tests for DryRunHandler.execute."""

    def test_execute_writes_stub_and_logs_validation(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """DRY_RUN mode writes stub artefact and logs validation state."""
        settings = _make_settings(tmp_path)
        inventory = _make_inventory(tmp_path)

        schema_path = tmp_path / "schema.json"

        captured: dict[str, object] = {}

        def fake_ensure_schema_available(path: Path) -> dict:
            captured["schema_path"] = path
            return {"$id": "test-schema"}

        def fake_write_stub_artefact(
            *,
            settings: RunnerSettings,
            inventory: RunnerInventory,
            schema: dict,
        ) -> Path:
            captured["settings"] = settings
            captured["inventory"] = inventory
            captured["schema"] = schema
            artefact = tmp_path / "assessment_run.dry-run.json"
            artefact.write_text("{}", encoding="utf-8")
            return artefact

        def fake_load_artefact_data(path: Path) -> dict:
            captured["loaded_path"] = path
            return {"validation": {"ok": True}}

        def fake_log_validation_state(
            *,
            logger,
            artefact_path: Path,
            artefact_data: dict,
        ) -> None:
            captured["logger"] = logger
            captured["artefact_path"] = artefact_path
            captured["artefact_data"] = artefact_data

        # Patch dependencies in the handler module namespace
        monkeypatch.setattr(
            "scripts.cj_experiments_runners.eng5_np.handlers.dry_run_handler.ensure_schema_available",
            fake_ensure_schema_available,
        )
        monkeypatch.setattr(
            "scripts.cj_experiments_runners.eng5_np.handlers.dry_run_handler.write_stub_artefact",
            fake_write_stub_artefact,
        )
        monkeypatch.setattr(
            "scripts.cj_experiments_runners.eng5_np.handlers.dry_run_handler.load_artefact_data",
            fake_load_artefact_data,
        )
        monkeypatch.setattr(
            "scripts.cj_experiments_runners.eng5_np.handlers.dry_run_handler.log_validation_state",
            fake_log_validation_state,
        )

        handler = DryRunHandler()

        class DummyPaths:
            """Minimal paths object exposing schema_path for the handler."""

            def __init__(self, schema: Path) -> None:
                self.schema_path = schema

        exit_code = handler.execute(
            settings=settings,
            inventory=inventory,
            paths=DummyPaths(schema_path),  # type: ignore[arg-type]
        )

        assert exit_code == 0
        assert captured["schema_path"] == schema_path
        assert captured["settings"] is settings
        assert captured["inventory"] is inventory
        assert captured["schema"] == {"$id": "test-schema"}

        artefact_path = captured["artefact_path"]
        assert isinstance(artefact_path, Path)
        assert artefact_path.name.startswith("assessment_run.dry-run")
