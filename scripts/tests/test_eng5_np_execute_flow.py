"""ENG5 execute flow tests (R4/R5).

These are unit-style tests focused on hardening semantics:
- R4: execute is student-only and does not require local anchor docs.
- R5: optional post-run DB extraction runs after completion and returns non-zero on failure.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from common_core.domain_enums import CourseCode, Language

from scripts.cj_experiments_runners.eng5_np.handlers import ExecuteHandler
from scripts.cj_experiments_runners.eng5_np.inventory import (
    DirectorySnapshot,
    FileRecord,
    RunnerInventory,
)
from scripts.cj_experiments_runners.eng5_np.settings import RunnerMode, RunnerSettings


def _make_settings(tmp_path: Path) -> RunnerSettings:
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
        cj_anchor_count=1,
    )


def _make_inventory(tmp_path: Path, *, with_local_anchors: bool) -> RunnerInventory:
    instructions = FileRecord(path=tmp_path / "instructions.md", exists=True)
    prompt = FileRecord(path=tmp_path / "prompt.md", exists=True)
    anchors_csv = FileRecord(path=tmp_path / "anchors.csv", exists=True)
    anchors_xlsx = FileRecord(path=tmp_path / "anchors.xlsx", exists=True)

    anchor_files = (
        [
            FileRecord(
                path=tmp_path / "anchors" / "anchor_001.docx",
                exists=True,
                checksum="anchor-checksum-1",
            )
        ]
        if with_local_anchors
        else []
    )
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


class DummyPaths:
    def __init__(self, schema_path: Path) -> None:
        self.schema_path = schema_path


class TestEng5ExecuteFlow:
    def test_execute_allows_empty_local_anchors_when_cj_preflight_present(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        settings = _make_settings(tmp_path)
        settings.await_completion = False
        settings.auto_extract_eng5_db = False
        inventory = _make_inventory(tmp_path, with_local_anchors=False)

        async def fake_upload_essays_parallel(records, content_service_url: str):
            return {r.checksum: "storage-1" for r in records}

        async def fake_publish_envelope_to_kafka(*_args, **_kwargs):
            return None

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
            "scripts.cj_experiments_runners.eng5_np.handlers.execute_handler.ExecuteHandler._upload_prompt",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                AssertionError("ExecuteHandler must not upload prompts for assignment runs")
            ),
        )
        monkeypatch.setattr(
            "scripts.cj_experiments_runners.eng5_np.handlers.execute_handler.publish_envelope_to_kafka",
            fake_publish_envelope_to_kafka,
        )
        monkeypatch.setattr(
            "scripts.cj_experiments_runners.eng5_np.handlers.execute_handler.load_artefact_data",
            lambda _path: {"validation": {"ok": True}},
        )
        monkeypatch.setattr(
            "scripts.cj_experiments_runners.eng5_np.handlers.execute_handler.log_validation_state",
            lambda **_kwargs: None,
        )

        handler = ExecuteHandler()
        exit_code = handler.execute(
            settings=settings,
            inventory=inventory,
            paths=DummyPaths(tmp_path / "schema.json"),  # type: ignore[arg-type]
        )
        assert exit_code == 0

    def test_execute_returns_two_when_auto_extract_fails_after_completion(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        settings = _make_settings(tmp_path)
        settings.await_completion = True
        settings.auto_extract_eng5_db = True
        inventory = _make_inventory(tmp_path, with_local_anchors=False)

        async def fake_upload_essays_parallel(records, content_service_url: str):
            return {r.checksum: "storage-1" for r in records}

        async def fake_run_publish_and_capture(*_args, **_kwargs):
            return None

        def fake_run_eng5_db_extraction(
            *, batch_identifier: str, output_dir: Path, output_format: str = "text"
        ):  # noqa: E501
            return type(
                "Result",
                (),
                {
                    "batch_identifier": batch_identifier,
                    "output_path": output_dir / "out.txt",
                    "output_format": output_format,
                    "exit_code": 1,
                    "error": "boom",
                },
            )()

        class DummyHydrator:
            def __init__(self, *args, **kwargs) -> None:  # pragma: no cover - trivial
                pass

            def runner_status(self) -> dict:
                return {"observed_events": {"completions": 1}}

            def update_post_run(self, *, key: str, payload: dict) -> None:
                return None

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
            "scripts.cj_experiments_runners.eng5_np.handlers.execute_handler.ExecuteHandler._upload_prompt",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                AssertionError("ExecuteHandler must not upload prompts for assignment runs")
            ),
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
        monkeypatch.setattr(
            "scripts.cj_experiments_runners.eng5_np.handlers.execute_handler.log_validation_state",
            lambda **_kwargs: None,
        )

        handler = ExecuteHandler()
        exit_code = handler.execute(
            settings=settings,
            inventory=inventory,
            paths=DummyPaths(tmp_path / "schema.json"),  # type: ignore[arg-type]
        )
        assert exit_code == 2
