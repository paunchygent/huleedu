"""Unit tests for PlanHandler behavior and protocol compliance."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from common_core.domain_enums import CourseCode, Language

from scripts.cj_experiments_runners.eng5_np.handlers import PlanHandler
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
    """Create minimal RunnerSettings for PLAN mode tests."""
    return RunnerSettings(
        assignment_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        cj_assignment_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        course_id=uuid.UUID("00000000-0000-0000-0000-000000000002"),
        grade_scale="eng5_np_legacy_9_step",
        mode=RunnerMode.PLAN,
        use_kafka=False,
        output_dir=tmp_path,
        runner_version="test-1.0.0",
        git_sha="test-sha",
        batch_uuid=uuid.UUID("00000000-0000-0000-0000-000000000003"),
        batch_id="TEST-BATCH-PLAN",
        user_id="test-user",
        org_id=None,
        course_code=CourseCode.ENG5,
        language=Language.ENGLISH,
        correlation_id=uuid.UUID("00000000-0000-0000-0000-000000000004"),
        kafka_bootstrap="localhost:9092",
        kafka_client_id="test-client",
        content_service_url="http://localhost:8000",
    )


def _make_inventory(tmp_path: Path) -> RunnerInventory:
    """Create a small, in-memory RunnerInventory for testing."""
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


class TestPlanHandlerProtocol:
    """Contract tests for PlanHandler protocol compliance."""

    def test_plan_handler_implements_mode_handler_protocol(self) -> None:
        """PlanHandler instances satisfy ModeHandlerProtocol at runtime."""
        handler = PlanHandler()
        assert isinstance(handler, ModeHandlerProtocol)


class TestPlanHandlerExecute:
    """Behavioral tests for PlanHandler.execute."""

    def test_execute_logs_inventory_and_returns_zero(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """PLAN mode prints inventory and logs validation state."""
        settings = _make_settings(tmp_path)
        inventory = _make_inventory(tmp_path)

        captured_inventory: list[RunnerInventory] = []
        logged: dict[str, object] = {}

        def fake_print_inventory(inv: RunnerInventory) -> None:
            captured_inventory.append(inv)

        def fake_log_validation_state(
            *,
            logger,
            artefact_path: Path,
            artefact_data: dict,
        ) -> None:
            logged["logger"] = logger
            logged["artefact_path"] = artefact_path
            logged["artefact_data"] = artefact_data

        # Patch dependencies in the handler module namespace
        monkeypatch.setattr(
            "scripts.cj_experiments_runners.eng5_np.handlers.plan_handler.print_inventory",
            fake_print_inventory,
        )
        monkeypatch.setattr(
            "scripts.cj_experiments_runners.eng5_np.handlers.plan_handler.log_validation_state",
            fake_log_validation_state,
        )

        handler = PlanHandler()
        exit_code = handler.execute(settings=settings, inventory=inventory, paths=None)  # type: ignore[arg-type]

        assert exit_code == 0
        assert captured_inventory == [inventory]

        # Validate validation state logging
        assert isinstance(logged.get("artefact_path"), Path)
        artefact_path = logged["artefact_path"]
        assert str(artefact_path).endswith("assessment_run.plan.json")
        artefact_data = logged["artefact_data"]
        assert artefact_data["validation"]["runner_status"]["inventory"]["anchors"] == 1
        assert artefact_data["validation"]["runner_status"]["inventory"]["students"] == 1
