"""Shared helpers for AnchorAlignHandler tests."""

from __future__ import annotations

import uuid
from pathlib import Path

from common_core.domain_enums import CourseCode, Language

from scripts.cj_experiments_runners.eng5_np.inventory import (
    DirectorySnapshot,
    FileRecord,
    RunnerInventory,
)
from scripts.cj_experiments_runners.eng5_np.settings import (
    RunnerMode,
    RunnerSettings,
)


def make_anchor_align_settings(tmp_path: Path) -> RunnerSettings:
    """Create RunnerSettings for ANCHOR_ALIGN_TEST mode tests."""
    return RunnerSettings(
        assignment_id=uuid.UUID("00000000-0000-0000-0000-000000000021"),
        cj_assignment_id=None,
        course_id=uuid.UUID("00000000-0000-0000-0000-000000000022"),
        grade_scale="eng5_np_legacy_9_step",
        mode=RunnerMode.ANCHOR_ALIGN_TEST,
        use_kafka=True,
        output_dir=tmp_path,
        runner_version="test-1.0.0",
        git_sha="test-sha",
        batch_uuid=uuid.UUID("00000000-0000-0000-0000-000000000023"),
        batch_id="TEST-BATCH-ANCHOR-ALIGN",
        user_id="test-user",
        org_id=None,
        course_code=CourseCode.ENG5,
        language=Language.ENGLISH,
        correlation_id=uuid.UUID("00000000-0000-0000-0000-000000000024"),
        kafka_bootstrap="localhost:9092",
        kafka_client_id="test-client",
        content_service_url="http://localhost:8000",
    )


def make_inventory_with_anchors(tmp_path: Path, anchor_count: int = 2) -> RunnerInventory:
    """Create RunnerInventory with a configurable number of anchor files."""
    instructions = FileRecord(path=tmp_path / "instructions.md", exists=True)
    prompt = FileRecord(path=tmp_path / "prompt.md", exists=True)
    anchors_csv = FileRecord(path=tmp_path / "anchors.csv", exists=True)
    anchors_xlsx = FileRecord(path=tmp_path / "anchors.xlsx", exists=True)

    anchor_files: list[FileRecord] = []
    for idx in range(anchor_count):
        anchor_files.append(
            FileRecord(
                path=tmp_path / "anchors" / f"anchor_{idx + 1:03d}.docx",
                exists=True,
                checksum=f"checksum-{idx + 1}",
            )
        )

    anchor_docs = DirectorySnapshot(root=tmp_path / "anchors", files=anchor_files)
    student_docs = DirectorySnapshot(root=tmp_path / "students", files=[])

    return RunnerInventory(
        instructions=instructions,
        prompt=prompt,
        anchors_csv=anchors_csv,
        anchors_xlsx=anchors_xlsx,
        anchor_docs=anchor_docs,
        student_docs=student_docs,
    )
