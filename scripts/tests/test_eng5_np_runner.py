from __future__ import annotations

import datetime as dt
import json
import uuid
from pathlib import Path

import jsonschema
import pytest
from common_core import LLMProviderType
from common_core.domain_enums import CourseCode, Language
from common_core.event_enums import ProcessingEvent, topic_name
from common_core.events.cj_assessment_events import AssessmentResultV1, EssayResultV1
from common_core.events.envelope import EventEnvelope
from common_core.events.llm_provider_events import (
    EssayComparisonWinner,
    LLMComparisonResultV1,
    TokenUsage,
)

from scripts.cj_experiments_runners.eng5_np.artefact_io import write_stub_artefact
from scripts.cj_experiments_runners.eng5_np.environment import repo_root_from_package
from scripts.cj_experiments_runners.eng5_np.hydrator import AssessmentRunHydrator
from scripts.cj_experiments_runners.eng5_np.inventory import (
    FileRecord,
    build_essay_refs,
    collect_inventory,
    snapshot_directory,
)
from scripts.cj_experiments_runners.eng5_np.paths import RunnerPaths
from scripts.cj_experiments_runners.eng5_np.requests import (
    compose_cj_assessment_request,
    write_cj_request_envelope,
)
from scripts.cj_experiments_runners.eng5_np.settings import RunnerMode, RunnerSettings
from scripts.cj_experiments_runners.eng5_np.utils import sha256_of_file


def _write_base_artefact(tmp_path: Path) -> Path:
    artefact = {
        "schema_version": "1.0.0",
        "metadata": {
            "assignment_id": str(uuid.uuid4()),
            "course_id": str(uuid.uuid4()),
            "grade_scale": "eng5_np_legacy_9_step",
            "runner_version": "0.1.0",
            "git_sha": "deadbeef",
            "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "runner_mode": "execute",
        },
        "inputs": {
            "instructions": {
                "source_path": "instructions.md",
                "checksum": "0" * 64,
                "content": "instructions",
            },
            "prompt_reference": {
                "source_path": "prompt.md",
                "checksum": "f" * 64,
                "content": "prompt",
            },
            "anchors": [
                {
                    "anchor_id": "ANCHOR_1",
                    "file_name": "anchor.docx",
                    "grade": "A",
                    "source_path": "anchor.docx",
                    "checksum": "1" * 64,
                }
            ],
            "students": [
                {
                    "essay_id": "STUDENT_1",
                    "file_name": "student.docx",
                    "source_path": "student.docx",
                    "checksum": "2" * 64,
                }
            ],
        },
        "llm_comparisons": [],
        "bt_summary": [],
        "grade_projections": [],
        "costs": {"total_usd": 0.0, "token_counts": []},
        "validation": {
            "artefact_checksum": "",
            "manifest": [],
            "cli_environment": {
                "python": "3.11",
                "pdm": "test",
                "os": "posix",
                "docker_compose": "n/a",
            },
            "runner_status": {
                "partial_data": False,
                "timeout_seconds": 0.0,
                "observed_events": {
                    "llm_comparisons": 0,
                    "assessment_results": 0,
                    "completions": 0,
                },
            },
        },
    }
    target = tmp_path / "assessment_run.execute.json"
    target.write_text(json.dumps(artefact, indent=2), encoding="utf-8")
    return target


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
        content_service_url="http://localhost:8001/v1/content",
        llm_overrides=None,
        await_completion=False,
        completion_timeout=1.0,
    )

    output_file = write_stub_artefact(
        settings=settings,
        inventory=inventory,
        schema={"schema_version": "1.0.0"},
    )

    data = json.loads(output_file.read_text(encoding="utf-8"))

    assert data["metadata"]["runner_mode"] == RunnerMode.DRY_RUN.value
    assert data["inputs"]["instructions"]["content"] == "instructions"
    assert data["inputs"]["prompt_reference"]["checksum"]
    assert len(data["inputs"]["anchors"]) >= 1
    assert len(data["inputs"]["students"]) >= 1
    assert data["validation"]["runner_status"]["partial_data"] is False


@pytest.mark.skipif(
    not (repo_root_from_package() / "test_uploads").exists(),
    reason="ENG5 role-model assets not available",
)
def test_collect_inventory_matches_real_dataset() -> None:
    paths = RunnerPaths.from_repo_root(repo_root_from_package())
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

    FileRecord.from_path(prompt)
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
        content_service_url="http://localhost:8001/v1/content",
        llm_overrides=None,
        await_completion=False,
        completion_timeout=1.0,
    )

    envelope = compose_cj_assessment_request(
        settings=settings,
        essay_refs=essay_refs,
        prompt_reference=None,
    )

    assert envelope.data.user_id == "user-42"
    assert envelope.data.language == Language.ENGLISH.value
    path = write_cj_request_envelope(envelope=envelope, output_dir=settings.output_dir)
    assert path.exists()


def test_build_essay_refs_prefers_uploaded_storage_ids(tmp_path: Path) -> None:
    anchor_file = tmp_path / "anchor.docx"
    student_file = tmp_path / "student.docx"
    anchor_file.write_text("anchor essay", encoding="utf-8")
    student_file.write_text("student essay", encoding="utf-8")

    anchor_record = FileRecord.from_path(anchor_file)
    student_record = FileRecord.from_path(student_file)
    storage_map = {
        anchor_record.checksum: "storage-anchor-123",
        student_record.checksum: "storage-student-456",
    }

    refs = build_essay_refs(
        anchors=[anchor_record],
        students=[student_record],
        storage_id_map=storage_map,
    )

    assert refs[0].text_storage_id == "storage-anchor-123"
    assert refs[1].text_storage_id == "storage-student-456"


def test_hydrator_appends_llm_comparison_and_manifest(tmp_path: Path) -> None:
    artefact_path = _write_base_artefact(tmp_path)
    hydrator = AssessmentRunHydrator(
        artefact_path=artefact_path,
        output_dir=tmp_path,
        grade_scale="eng5_np_legacy_9_step",
        batch_id="batch-llm",
    )

    llm_event = LLMComparisonResultV1(
        request_id="req-1",
        correlation_id=uuid.uuid4(),
        winner=EssayComparisonWinner.ESSAY_A,
        justification="Winner",
        confidence=3.5,
        error_detail=None,
        provider=LLMProviderType.OPENAI,
        model="gpt-4o-mini",
        response_time_ms=500,
        token_usage=TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150),
        cost_estimate=0.25,
        requested_at=dt.datetime.now(dt.timezone.utc),
        completed_at=dt.datetime.now(dt.timezone.utc),
        trace_id="trace",
        request_metadata={
            "batch_id": "batch-llm",
            "essay_a_id": "A1",
            "essay_b_id": "B1",
            "prompt_sha256": "a" * 64,
        },
    )
    envelope = EventEnvelope[LLMComparisonResultV1](
        event_type=topic_name(ProcessingEvent.LLM_COMPARISON_RESULT),
        event_timestamp=dt.datetime.now(dt.timezone.utc),
        source_service="test",
        correlation_id=llm_event.correlation_id,
        data=llm_event,
    )

    hydrator.apply_llm_comparison(envelope)

    data = json.loads(artefact_path.read_text(encoding="utf-8"))
    assert len(data["llm_comparisons"]) == 1
    comparison = data["llm_comparisons"][0]
    assert comparison["winner_id"] == "A1"
    assert comparison["request_id"] == "req-1"
    assert comparison["status"] == "succeeded"
    assert data["costs"]["total_usd"] == pytest.approx(0.25)
    assert data["validation"]["manifest"]
    assert data["validation"]["runner_status"]["observed_events"]["llm_comparisons"] == 1


def test_hydrator_applies_assessment_results(tmp_path: Path) -> None:
    artefact_path = _write_base_artefact(tmp_path)
    hydrator = AssessmentRunHydrator(
        artefact_path=artefact_path,
        output_dir=tmp_path,
        grade_scale="eng5_np_legacy_9_step",
        batch_id="batch-results",
    )

    essay = EssayResultV1(
        essay_id="student-1",
        normalized_score=0.9,
        letter_grade="A",
        confidence_score=0.8,
        confidence_label="HIGH",
        bt_score=1.2,
        rank=1,
        is_anchor=False,
        feedback_uri=None,
        metrics_uri=None,
        display_name=None,
    )

    assessment_event = AssessmentResultV1(
        batch_id="batch-results",
        cj_assessment_job_id="cj-1",
        assessment_method="cj_assessment",
        model_used="claude",
        model_provider="anthropic",
        model_version=None,
        essay_results=[essay],
        assessment_metadata={
            "comparison_count": 3,
            "grade_projection_summary": {
                "grade_probabilities": {"student-1": {"A": 0.8, "B": 0.2}},
            },
        },
    )
    envelope = EventEnvelope[AssessmentResultV1](
        event_type=topic_name(ProcessingEvent.ASSESSMENT_RESULT_PUBLISHED),
        event_timestamp=dt.datetime.now(dt.timezone.utc),
        source_service="test",
        correlation_id=uuid.uuid4(),
        data=assessment_event,
    )

    hydrator.apply_assessment_result(envelope)

    data = json.loads(artefact_path.read_text(encoding="utf-8"))
    assert data["bt_summary"][0]["comparison_count"] == 3
    assert data["grade_projections"][0]["probabilities"]["A"] == pytest.approx(0.8)
    assert data["validation"]["runner_status"]["observed_events"]["assessment_results"] == 1


def test_hydrator_deduplicates_comparison_events(tmp_path: Path) -> None:
    artefact_path = _write_base_artefact(tmp_path)
    hydrator = AssessmentRunHydrator(
        artefact_path=artefact_path,
        output_dir=tmp_path,
        grade_scale="eng5_np_legacy_9_step",
        batch_id="batch-dup",
    )

    llm_event = LLMComparisonResultV1(
        request_id="req-dup",
        correlation_id=uuid.uuid4(),
        winner=EssayComparisonWinner.ESSAY_B,
        justification="B wins",
        confidence=3.1,
        error_detail=None,
        provider=LLMProviderType.OPENAI,
        model="gpt-4o-mini",
        response_time_ms=400,
        token_usage=TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
        cost_estimate=0.05,
        requested_at=dt.datetime.now(dt.timezone.utc),
        completed_at=dt.datetime.now(dt.timezone.utc),
        trace_id="trace",
        request_metadata={
            "batch_id": "batch-dup",
            "essay_a_id": "A1",
            "essay_b_id": "B1",
            "prompt_sha256": "b" * 64,
        },
    )
    envelope = EventEnvelope[LLMComparisonResultV1](
        event_type=topic_name(ProcessingEvent.LLM_COMPARISON_RESULT),
        event_timestamp=dt.datetime.now(dt.timezone.utc),
        source_service="test",
        correlation_id=llm_event.correlation_id,
        data=llm_event,
    )

    hydrator.apply_llm_comparison(envelope)
    hydrator.apply_llm_comparison(envelope)

    data = json.loads(artefact_path.read_text(encoding="utf-8"))
    assert len(data["llm_comparisons"]) == 1


def test_hydrator_raises_when_prompt_hash_missing(tmp_path: Path) -> None:
    artefact_path = _write_base_artefact(tmp_path)
    hydrator = AssessmentRunHydrator(
        artefact_path=artefact_path,
        output_dir=tmp_path,
        grade_scale="eng5_np_legacy_9_step",
        batch_id="batch-missing",
    )

    llm_event = LLMComparisonResultV1(
        request_id="req-missing",
        correlation_id=uuid.uuid4(),
        winner=EssayComparisonWinner.ESSAY_A,
        justification="A wins",
        confidence=4.2,
        error_detail=None,
        provider=LLMProviderType.OPENAI,
        model="gpt-4o-mini",
        response_time_ms=500,
        token_usage=TokenUsage(prompt_tokens=20, completion_tokens=10, total_tokens=30),
        cost_estimate=0.1,
        requested_at=dt.datetime.now(dt.timezone.utc),
        completed_at=dt.datetime.now(dt.timezone.utc),
        trace_id="trace",
        request_metadata={
            "batch_id": "batch-missing",
            "essay_a_id": "A1",
            "essay_b_id": "B1",
        },
    )
    envelope = EventEnvelope[LLMComparisonResultV1](
        event_type=topic_name(ProcessingEvent.LLM_COMPARISON_RESULT),
        event_timestamp=dt.datetime.now(dt.timezone.utc),
        source_service="test",
        correlation_id=llm_event.correlation_id,
        data=llm_event,
    )

    with pytest.raises(ValueError):
        hydrator.apply_llm_comparison(envelope)


def test_stub_validates_against_schema(tmp_path: Path) -> None:
    repo_root = repo_root_from_package()
    schema_path = repo_root / "Documentation" / "schemas" / "eng5_np" / "assessment_run.schema.json"
    if not schema_path.exists():
        pytest.skip("Schema file missing")

    role_models_root = tmp_path / "ROLE_MODELS"
    role_models_root.mkdir(parents=True)
    instructions = role_models_root / "instructions.md"
    instructions.write_text("instructions", encoding="utf-8")
    prompt = role_models_root / "prompt.md"
    prompt.write_text("prompt", encoding="utf-8")
    anchors_dir = role_models_root / "anchor_essays"
    anchors_dir.mkdir()
    (anchors_dir / "A1.docx").write_text("anchor", encoding="utf-8")
    students_dir = role_models_root / "student_essays"
    students_dir.mkdir()
    (students_dir / "S1.docx").write_text("student", encoding="utf-8")

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
        assignment_id=uuid.uuid4(),
        course_id=uuid.uuid4(),
        grade_scale="eng5_np_legacy_9_step",
        mode=RunnerMode.DRY_RUN,
        use_kafka=False,
        output_dir=tmp_path / "output",
        runner_version="0.1.0",
        git_sha="deadbeef",
        batch_id="batch-schema",
        user_id="user",
        org_id="org",
        course_code=CourseCode.ENG5,
        language=Language.ENGLISH,
        correlation_id=uuid.uuid4(),
        kafka_bootstrap="kafka:9092",
        kafka_client_id="test-client",
        content_service_url="http://localhost:8001/v1/content",
        llm_overrides=None,
        await_completion=False,
        completion_timeout=1.0,
    )

    artefact_path = write_stub_artefact(
        settings=settings,
        inventory=inventory,
        schema=json.loads(schema_path.read_text(encoding="utf-8")),
    )

    instance = json.loads(artefact_path.read_text(encoding="utf-8"))
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    jsonschema.validate(instance=instance, schema=schema)
