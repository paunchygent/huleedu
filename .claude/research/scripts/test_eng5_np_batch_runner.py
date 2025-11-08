from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.append(str(SCRIPT_DIR))

from common_core.domain_enums import CourseCode, Language

from eng5_np_batch_runner import (
    FileRecord,
    RunnerMode,
    RunnerPaths,
    RunnerSettings,
    build_essay_refs,
    build_prompt_reference,
    collect_inventory,
    compose_cj_assessment_request,
    ensure_schema_available,
    repo_root_from_this_file,
    snapshot_directory,
    sha256_of_file,
    write_cj_request_envelope,
    write_stub_artefact,
)


def test_sha256_round_trip(tmp_path: Path) -> None:
    target = tmp_path / "sample.txt"
    target.write_text("abc123", encoding="utf-8")

    checksum = sha256_of_file(target)

    assert checksum == "6ca13d52ca70c883e0f0bb101e425a89e8624de51db2d2392593af6a84118090"


def test_snapshot_directory_handles_missing(tmp_path: Path) -> None:
    snapshot = snapshot_directory(tmp_path / "missing", patterns=["*.docx"])

    assert snapshot.missing is True
    assert snapshot.count == 0


def test_write_stub_creates_schema_compliant_file(tmp_path: Path) -> None:
    schema_path = tmp_path / "schema.json"
    schema_path.write_text(json.dumps({"title": "test"}), encoding="utf-8")

    role_models_root = tmp_path / "ROLE_MODELS"
    role_models_root.mkdir(parents=True)
    instructions = role_models_root / "eng5_np_vt_2017_essay_instruction.md"
    instructions.write_text("instructions", encoding="utf-8")
    prompt = role_models_root / "llm_prompt_cj_assessment_eng5.md"
    prompt.write_text("prompt", encoding="utf-8")
    anchors_dir = role_models_root / "anchor_essays"
    anchors_dir.mkdir()
    anchor_doc = anchors_dir / "A1.docx"
    anchor_doc.write_text("anchor", encoding="utf-8")
    students_dir = role_models_root / "student_essays"
    students_dir.mkdir()

    paths = RunnerPaths(
        repo_root=tmp_path,
        role_models_root=role_models_root,
        instructions_path=instructions,
        prompt_path=prompt,
        anchors_csv=role_models_root / "ANCHOR_ESSAYS_BAYESIAN_INFERENCE_DATA.csv",
        anchors_xlsx=role_models_root / "ANCHOR_ESSAYS_BAYESIAN_INFERENCE_DATA.xlsx",
        anchor_docs_dir=anchors_dir,
        student_docs_dir=students_dir,
        schema_path=schema_path,
        artefact_output_dir=tmp_path / "output",
    )

    inventory = collect_inventory(paths)
    settings = RunnerSettings(
        assignment_id=uuid.UUID(int=1),
        course_id=uuid.UUID(int=2),
        grade_scale="eng5_np_legacy_9_step",
        mode=RunnerMode.DRY_RUN,
        use_kafka=False,
        output_dir=tmp_path / "output",
        runner_version="0.1.0",
        git_sha="deadbeef",
        batch_id="batch-1",
        user_id="user-1",
        org_id="org-1",
        course_code=CourseCode.ENG5,
        language=Language.ENGLISH,
        correlation_id=uuid.uuid4(),
        kafka_bootstrap="kafka:9092",
        kafka_client_id="test-client",
        llm_overrides=None,
        await_completion=False,
        completion_timeout=1.0,
    )

    output_file = write_stub_artefact(
        settings=settings,
        inventory=inventory,
        schema=ensure_schema_available(schema_path),
    )

    data = json.loads(output_file.read_text(encoding="utf-8"))

    assert data["metadata"]["runner_mode"] == RunnerMode.DRY_RUN.value
    assert data["inputs"]["instructions"]["exists"] is True


@pytest.mark.skipif(
    not (repo_root_from_this_file() / "test_uploads").exists(),
    reason="ENG5 role-model assets not available",
)
def test_collect_inventory_matches_real_dataset() -> None:
    paths = RunnerPaths.from_repo_root(repo_root_from_this_file())
    inventory = collect_inventory(paths)

    assert inventory.instructions.exists is True
    assert inventory.prompt.exists is True
    assert inventory.anchor_docs.count >= 1


def test_compose_cj_request_generates_envelope(tmp_path: Path) -> None:
    prompt = tmp_path / "prompt.md"
    prompt.write_text("prompt text", encoding="utf-8")
    student_dir = tmp_path / "students"
    student_dir.mkdir()
    essay_file = student_dir / "JA24.docx"
    essay_file.write_text("essay", encoding="utf-8")

    prompt_record = FileRecord.from_path(prompt)
    essay_records = [FileRecord.from_path(essay_file)]
    essay_refs = build_essay_refs(anchors=[], students=essay_records)

    settings = RunnerSettings(
        assignment_id=uuid.UUID(int=1),
        course_id=uuid.UUID(int=2),
        grade_scale="eng5_np_legacy_9_step",
        mode=RunnerMode.EXECUTE,
        use_kafka=False,
        output_dir=tmp_path / "out",
        runner_version="0.1.0",
        git_sha="deadbeef",
        batch_id="batch-42",
        user_id="user-42",
        org_id="org-42",
        course_code=CourseCode.ENG5,
        language=Language.ENGLISH,
        correlation_id=uuid.UUID(int=3),
        kafka_bootstrap="kafka:9092",
        kafka_client_id="test-client",
        llm_overrides=None,
        await_completion=False,
        completion_timeout=1.0,
    )

    prompt_ref = build_prompt_reference(prompt_record)
    envelope = compose_cj_assessment_request(
        settings=settings,
        essay_refs=essay_refs,
        prompt_reference=prompt_ref,
    )

    assert envelope.data.user_id == "user-42"
    assert envelope.data.language == Language.ENGLISH.value
    path = write_cj_request_envelope(envelope=envelope, output_dir=settings.output_dir)
    assert path.exists()
