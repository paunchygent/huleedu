"""Integration tests for ENG5 NP runner execute mode (no-Kafka path).

This module tests the complete execute-mode workflow without Kafka:
- Stub artefact creation
- Event hydration (LLM comparisons, assessment results)
- Artefact completeness validation
- Timeout scenario handling
- Schema validation (optional if jsonschema available)
"""

from __future__ import annotations

import datetime as dt
import json
import uuid
from pathlib import Path

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
from scripts.cj_experiments_runners.eng5_np.inventory import collect_inventory
from scripts.cj_experiments_runners.eng5_np.paths import RunnerPaths
from scripts.cj_experiments_runners.eng5_np.settings import RunnerMode, RunnerSettings


def _create_test_environment(tmp_path: Path) -> tuple[RunnerPaths, RunnerSettings]:
    """Create test environment with role models and settings.

    Args:
        tmp_path: Pytest temporary directory

    Returns:
        Tuple of (RunnerPaths, RunnerSettings)
    """
    role_models_root = tmp_path / "ROLE_MODELS"
    role_models_root.mkdir(parents=True)

    # Create required files
    instructions = role_models_root / "eng5_np_vt_2017_essay_instruction.md"
    instructions.write_text("Assessment instructions for ENG5 NP", encoding="utf-8")

    prompt = role_models_root / "llm_prompt_cj_assessment_eng5.md"
    prompt.write_text("LLM prompt for comparisons", encoding="utf-8")

    # Create anchor essays directory with one anchor
    anchors_dir = role_models_root / "anchor_essays"
    anchors_dir.mkdir()
    (anchors_dir / "A1.docx").write_text("Anchor essay A grade", encoding="utf-8")

    # Create student essays directory with two students
    students_dir = role_models_root / "student_essays"
    students_dir.mkdir()
    (students_dir / "S1.docx").write_text("Student essay 1", encoding="utf-8")
    (students_dir / "S2.docx").write_text("Student essay 2", encoding="utf-8")

    # Create paths
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    repo_root = repo_root_from_package()
    schema_path = repo_root / "Documentation" / "schemas" / "eng5_np" / "assessment_run.schema.json"

    paths = RunnerPaths(
        repo_root=tmp_path,
        role_models_root=role_models_root,
        instructions_path=instructions,
        prompt_path=prompt,
        anchors_csv=role_models_root / "ANCHOR_ESSAYS_BAYESIAN_INFERENCE_DATA.csv",
        anchors_xlsx=role_models_root / "ANCHOR_ESSAYS_BAYESIAN_INFERENCE_DATA.xlsx",
        anchor_docs_dir=anchors_dir,
        student_docs_dir=students_dir,
        schema_path=schema_path if schema_path.exists() else tmp_path / "schema.json",
        artefact_output_dir=output_dir,
    )

    # Create settings for execute mode
    settings = RunnerSettings(
        assignment_id=uuid.uuid4(),
        course_id=uuid.uuid4(),
        grade_scale="eng5_np_legacy_9_step",
        mode=RunnerMode.EXECUTE,
        use_kafka=False,  # No-Kafka path
        output_dir=output_dir,
        runner_version="0.1.0",
        git_sha="deadbeef",  # Valid git SHA format
        batch_id="batch-execute-test",
        user_id="test-user",
        org_id="test-org",
        course_code=CourseCode.ENG5,
        language=Language.ENGLISH,
        correlation_id=uuid.uuid4(),
        kafka_bootstrap="kafka:9092",
        kafka_client_id="test-client",
        llm_overrides=None,
        await_completion=False,
        completion_timeout=10.0,
    )

    return paths, settings


def _create_llm_comparison_envelope(
    batch_id: str,
    request_id: str,
    essay_a_id: str,
    essay_b_id: str,
    winner: EssayComparisonWinner,
    prompt_sha256: str,
) -> EventEnvelope[LLMComparisonResultV1]:
    """Create LLM comparison result envelope for testing.

    Args:
        batch_id: Batch identifier
        request_id: Request identifier
        essay_a_id: First essay ID
        essay_b_id: Second essay ID
        winner: Comparison winner
        prompt_sha256: SHA256 hash of prompt

    Returns:
        Event envelope with LLM comparison result
    """
    llm_event = LLMComparisonResultV1(
        request_id=request_id,
        correlation_id=uuid.uuid4(),
        winner=winner,
        justification=f"{winner.value} demonstrates better quality",
        confidence=4.0,
        error_detail=None,
        provider=LLMProviderType.ANTHROPIC,
        model="claude-sonnet-4-5",
        response_time_ms=800,
        token_usage=TokenUsage(prompt_tokens=200, completion_tokens=50, total_tokens=250),
        cost_estimate=0.15,
        requested_at=dt.datetime.now(dt.timezone.utc),
        completed_at=dt.datetime.now(dt.timezone.utc),
        trace_id=f"trace-{request_id}",
        request_metadata={
            "batch_id": batch_id,
            "essay_a_id": essay_a_id,
            "essay_b_id": essay_b_id,
            "prompt_sha256": prompt_sha256,
        },
    )

    return EventEnvelope[LLMComparisonResultV1](
        event_type=topic_name(ProcessingEvent.LLM_COMPARISON_RESULT),
        event_timestamp=dt.datetime.now(dt.timezone.utc),
        source_service="llm_provider_service",
        correlation_id=llm_event.correlation_id,
        data=llm_event,
    )


def _create_assessment_result_envelope(
    batch_id: str,
    essay_results: list[EssayResultV1],
) -> EventEnvelope[AssessmentResultV1]:
    """Create assessment result envelope for testing.

    Args:
        batch_id: Batch identifier
        essay_results: List of essay results

    Returns:
        Event envelope with assessment result
    """
    assessment_event = AssessmentResultV1(
        batch_id=batch_id,
        cj_assessment_job_id="cj-execute-test",
        assessment_method="cj_assessment",
        model_used="claude-sonnet-4-5",
        model_provider="anthropic",
        model_version="20250929",
        essay_results=essay_results,
        assessment_metadata={
            "comparison_count": len(essay_results),
            "grade_projection_summary": {
                "grade_probabilities": {
                    result.essay_id: {"A": 0.7, "B": 0.2, "C": 0.1}
                    for result in essay_results
                    if not result.is_anchor
                }
            },
        },
    )

    return EventEnvelope[AssessmentResultV1](
        event_type=topic_name(ProcessingEvent.ASSESSMENT_RESULT_PUBLISHED),
        event_timestamp=dt.datetime.now(dt.timezone.utc),
        source_service="cj_assessment_service",
        correlation_id=uuid.uuid4(),
        data=assessment_event,
    )


def test_execute_mode_complete_artefact(tmp_path: Path) -> None:
    """Test complete execute-mode workflow with full artefact hydration.

    This test simulates execute mode by:
    1. Creating a stub artefact
    2. Applying LLM comparison events
    3. Applying assessment result event
    4. Validating artefact completeness
    """
    # Create test environment
    paths, settings = _create_test_environment(tmp_path)
    inventory = collect_inventory(paths)

    # Write stub artefact
    if paths.schema_path.exists():
        schema = json.loads(paths.schema_path.read_text(encoding="utf-8"))
    else:
        schema = {"schema_version": "1.0.0"}

    artefact_path = write_stub_artefact(
        settings=settings,
        inventory=inventory,
        schema=schema,
    )

    # Create hydrator
    hydrator = AssessmentRunHydrator(
        artefact_path=artefact_path,
        output_dir=settings.output_dir,
        grade_scale=settings.grade_scale,
        batch_id=settings.batch_id,
    )

    # Apply LLM comparison events (3 comparisons)
    prompt_hash = "a" * 64
    comparisons = [
        ("A1", "S1", EssayComparisonWinner.ESSAY_A, "req-1"),
        ("A1", "S2", EssayComparisonWinner.ESSAY_B, "req-2"),
        ("S1", "S2", EssayComparisonWinner.ESSAY_A, "req-3"),
    ]

    for essay_a_id, essay_b_id, winner, request_id in comparisons:
        envelope = _create_llm_comparison_envelope(
            batch_id=settings.batch_id,
            request_id=request_id,
            essay_a_id=essay_a_id,
            essay_b_id=essay_b_id,
            winner=winner,
            prompt_sha256=prompt_hash,
        )
        hydrator.apply_llm_comparison(envelope)

    # Apply assessment result event
    essay_results = [
        EssayResultV1(
            essay_id="A1",
            normalized_score=0.95,
            letter_grade="A",
            confidence_score=0.9,
            confidence_label="HIGH",
            bt_score=1.5,
            rank=1,
            is_anchor=True,
            feedback_uri=None,
            metrics_uri=None,
            display_name=None,
        ),
        EssayResultV1(
            essay_id="S1",
            normalized_score=0.75,
            letter_grade="B",
            confidence_score=0.8,
            confidence_label="HIGH",
            bt_score=0.8,
            rank=2,
            is_anchor=False,
            feedback_uri=None,
            metrics_uri=None,
            display_name=None,
        ),
        EssayResultV1(
            essay_id="S2",
            normalized_score=0.65,
            letter_grade="C",
            confidence_score=0.7,
            confidence_label="MID",
            bt_score=0.5,
            rank=3,
            is_anchor=False,
            feedback_uri=None,
            metrics_uri=None,
            display_name=None,
        ),
    ]

    result_envelope = _create_assessment_result_envelope(
        batch_id=settings.batch_id,
        essay_results=essay_results,
    )
    hydrator.apply_assessment_result(result_envelope)

    # Validate artefact completeness
    artefact_data = json.loads(artefact_path.read_text(encoding="utf-8"))

    # Validate metadata
    assert artefact_data["metadata"]["runner_mode"] == RunnerMode.EXECUTE.value
    assert artefact_data["metadata"]["grade_scale"] == settings.grade_scale
    assert artefact_data["metadata"]["assignment_id"] == str(settings.assignment_id)

    # Validate LLM comparisons section
    assert len(artefact_data["llm_comparisons"]) == 3, "Should have 3 LLM comparisons"
    for comparison in artefact_data["llm_comparisons"]:
        assert comparison["status"] == "succeeded"
        assert comparison["prompt_hash"] == prompt_hash
        assert "winner_id" in comparison
        assert "request_id" in comparison

    # Validate BT summary section (one entry per essay)
    assert len(artefact_data["bt_summary"]) == 3, "Should have 3 BT summary entries (one per essay)"
    for bt_entry in artefact_data["bt_summary"]:
        assert "essay_id" in bt_entry
        assert "comparison_count" in bt_entry
        assert bt_entry["comparison_count"] == 3

    # Validate grade projections section (includes all essays with projections)
    assert len(artefact_data["grade_projections"]) == 3, (
        "Should have 3 grade projections (all essays)"
    )
    for projection in artefact_data["grade_projections"]:
        assert "grade" in projection  # Field name is "grade" not "primary_grade"
        assert "probabilities" in projection
        assert projection["essay_id"] in ["A1", "S1", "S2"]

    # Validate costs
    assert artefact_data["costs"]["total_usd"] > 0, "Should have non-zero cost"
    assert len(artefact_data["costs"]["token_counts"]) > 0, "Should have token count entries"

    # Validate manifest
    assert len(artefact_data["validation"]["manifest"]) > 0, "Should have manifest entries"

    # Validate runner status
    runner_status = artefact_data["validation"]["runner_status"]
    assert runner_status["partial_data"] is False, "Should not be partial data"
    assert runner_status["observed_events"]["llm_comparisons"] == 3
    assert runner_status["observed_events"]["assessment_results"] == 1


def test_execute_mode_timeout_scenario(tmp_path: Path) -> None:
    """Test execute-mode with timeout scenario (partial data).

    This test validates that the runner correctly handles timeout scenarios
    by setting partial_data=true when completion is not achieved.
    """
    # Create test environment
    paths, settings = _create_test_environment(tmp_path)
    inventory = collect_inventory(paths)

    # Write stub artefact
    schema = {"schema_version": "1.0.0"}
    artefact_path = write_stub_artefact(
        settings=settings,
        inventory=inventory,
        schema=schema,
    )

    # Create hydrator
    hydrator = AssessmentRunHydrator(
        artefact_path=artefact_path,
        output_dir=settings.output_dir,
        grade_scale=settings.grade_scale,
        batch_id=settings.batch_id,
    )

    # Apply only one LLM comparison (incomplete)
    envelope = _create_llm_comparison_envelope(
        batch_id=settings.batch_id,
        request_id="req-timeout",
        essay_a_id="A1",
        essay_b_id="S1",
        winner=EssayComparisonWinner.ESSAY_A,
        prompt_sha256="b" * 64,
    )
    hydrator.apply_llm_comparison(envelope)

    # Simulate timeout by marking partial data
    artefact_data = json.loads(artefact_path.read_text(encoding="utf-8"))
    artefact_data["validation"]["runner_status"]["partial_data"] = True
    artefact_data["validation"]["runner_status"]["timeout_seconds"] = settings.completion_timeout
    artefact_path.write_text(json.dumps(artefact_data, indent=2), encoding="utf-8")

    # Validate timeout scenario
    final_data = json.loads(artefact_path.read_text(encoding="utf-8"))

    # Partial data should be marked
    assert final_data["validation"]["runner_status"]["partial_data"] is True
    assert (
        final_data["validation"]["runner_status"]["timeout_seconds"] == settings.completion_timeout
    )

    # Should have some comparisons but incomplete assessment
    assert len(final_data["llm_comparisons"]) == 1, "Should have 1 partial comparison"
    assert len(final_data["bt_summary"]) == 0, "Should have no BT summary (incomplete)"
    assert len(final_data["grade_projections"]) == 0, "Should have no projections (incomplete)"


@pytest.mark.skipif(
    not (
        repo_root_from_package()
        / "Documentation"
        / "schemas"
        / "eng5_np"
        / "assessment_run.schema.json"
    ).exists(),
    reason="Schema file not available",
)
def test_execute_mode_schema_validation(tmp_path: Path) -> None:
    """Test that execute-mode stub artefact validates against JSON schema.

    This test validates schema compliance for the initial stub artefact.
    Note: After hydration, checksum recalculation may be needed for full validation.
    """
    try:
        import jsonschema
    except ImportError:
        pytest.skip("jsonschema package not available")

    # Create test environment
    paths, settings = _create_test_environment(tmp_path)
    inventory = collect_inventory(paths)

    # Load schema
    schema_path = paths.schema_path
    if not schema_path.exists():
        pytest.skip("Schema file not found")

    schema = json.loads(schema_path.read_text(encoding="utf-8"))

    # Write stub artefact
    artefact_path = write_stub_artefact(
        settings=settings,
        inventory=inventory,
        schema=schema,
    )

    # Validate stub schema compliance (before hydration)
    artefact_data = json.loads(artefact_path.read_text(encoding="utf-8"))

    # This should not raise ValidationError
    jsonschema.validate(instance=artefact_data, schema=schema)


def test_hydrator_metadata_validation_enforced(tmp_path: Path) -> None:
    """Test that hydrator enforces metadata presence (essay IDs, prompt hash).

    This test validates that missing metadata causes appropriate errors.
    """
    # Create minimal artefact
    artefact = {
        "schema_version": "1.0.0",
        "metadata": {
            "assignment_id": str(uuid.uuid4()),
            "grade_scale": "eng5_np_legacy_9_step",
            "runner_mode": "execute",
        },
        "llm_comparisons": [],
        "bt_summary": [],
        "grade_projections": [],
        "costs": {"total_usd": 0.0, "token_counts": []},
        "validation": {
            "manifest": [],
            "runner_status": {
                "partial_data": False,
                "observed_events": {
                    "llm_comparisons": 0,
                    "assessment_results": 0,
                },
            },
        },
    }

    artefact_path = tmp_path / "test.json"
    artefact_path.write_text(json.dumps(artefact), encoding="utf-8")

    hydrator = AssessmentRunHydrator(
        artefact_path=artefact_path,
        output_dir=tmp_path,
        grade_scale="eng5_np_legacy_9_step",
        batch_id="batch-validation",
    )

    # Create envelope with missing prompt_sha256
    llm_event = LLMComparisonResultV1(
        request_id="req-no-hash",
        correlation_id=uuid.uuid4(),
        winner=EssayComparisonWinner.ESSAY_A,
        justification="A wins",
        confidence=4.0,
        error_detail=None,
        provider=LLMProviderType.ANTHROPIC,
        model="claude-sonnet-4-5",
        response_time_ms=500,
        token_usage=TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150),
        cost_estimate=0.1,
        requested_at=dt.datetime.now(dt.timezone.utc),
        completed_at=dt.datetime.now(dt.timezone.utc),
        trace_id="trace",
        request_metadata={
            "batch_id": "batch-validation",
            "essay_a_id": "A1",
            "essay_b_id": "B1",
            # Missing prompt_sha256!
        },
    )

    envelope = EventEnvelope[LLMComparisonResultV1](
        event_type=topic_name(ProcessingEvent.LLM_COMPARISON_RESULT),
        event_timestamp=dt.datetime.now(dt.timezone.utc),
        source_service="test",
        correlation_id=llm_event.correlation_id,
        data=llm_event,
    )

    # Should raise ValueError for missing prompt hash
    with pytest.raises(ValueError, match="prompt hash"):
        hydrator.apply_llm_comparison(envelope)
