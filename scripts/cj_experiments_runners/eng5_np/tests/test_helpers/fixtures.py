"""Shared fixtures for ENG5 NP runner tests.

These fixtures provide standardized test data without using conftest.py.
Import explicitly in test files as per project conventions.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from common_core.domain_enums import CourseCode, Language

from scripts.cj_experiments_runners.eng5_np.settings import RunnerMode, RunnerSettings


@pytest.fixture
def base_runner_settings() -> RunnerSettings:
    """Create minimal valid RunnerSettings for testing.

    Returns settings suitable for PLAN mode with all required fields.
    Test-specific modes can override the mode field after fixture creation.
    """
    return RunnerSettings(
        assignment_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        course_id=uuid.UUID("00000000-0000-0000-0000-000000000002"),
        grade_scale="eng5_np_legacy_9_step",
        mode=RunnerMode.PLAN,
        use_kafka=False,
        output_dir=Path("/tmp/test_output"),
        runner_version="test-1.0.0",
        git_sha="abc123def456",
        batch_uuid=uuid.UUID("00000000-0000-0000-0000-000000000003"),
        batch_id="TEST-BATCH-001",
        user_id="test_user",
        org_id=None,
        course_code=CourseCode.ENG5,
        language=Language.ENGLISH,
        correlation_id=uuid.UUID("00000000-0000-0000-0000-000000000004"),
        kafka_bootstrap="localhost:9092",
        kafka_client_id="test-client",
        content_service_url="http://localhost:8000",
    )


@pytest.fixture
def sample_anchor_grade_map() -> dict[str, str]:
    """Standard anchor-to-grade mapping for tests.

    Covers full ENG5 NP grade range with representative anchors.
    """
    return {
        "anchor_001": "A",
        "anchor_002": "A",
        "anchor_003": "B",
        "anchor_004": "B",
        "anchor_005": "C+",
        "anchor_006": "C-",
        "anchor_007": "D+",
        "anchor_008": "D-",
        "anchor_009": "E+",
        "anchor_010": "E-",
        "anchor_011": "F+",
        "anchor_012": "F+",
    }


@pytest.fixture
def sample_bt_summary() -> list[dict]:
    """Sample Bradley-Terry summary output.

    Represents typical BT scoring results with descending theta values.
    """
    return [
        {"essay_id": "student::anchor_001", "theta": 3.5, "rank": 1},
        {"essay_id": "student::anchor_002", "theta": 2.8, "rank": 2},
        {"essay_id": "student::anchor_003", "theta": 2.1, "rank": 3},
        {"essay_id": "student::anchor_004", "theta": 1.5, "rank": 4},
        {"essay_id": "student::anchor_005", "theta": 0.5, "rank": 5},
        {"essay_id": "student::anchor_006", "theta": -0.5, "rank": 6},
        {"essay_id": "student::anchor_007", "theta": -1.2, "rank": 7},
        {"essay_id": "student::anchor_008", "theta": -2.0, "rank": 8},
        {"essay_id": "student::anchor_009", "theta": -2.8, "rank": 9},
        {"essay_id": "student::anchor_010", "theta": -3.5, "rank": 10},
        {"essay_id": "student::anchor_011", "theta": -4.2, "rank": 11},
        {"essay_id": "student::anchor_012", "theta": -5.0, "rank": 12},
    ]


@pytest.fixture
def sample_comparisons() -> list[dict]:
    """Sample LLM comparison records.

    Includes typical comparison outcomes with confidence and justification.
    """
    return [
        {
            "winner_id": "student::anchor_001",
            "loser_id": "student::anchor_003",
            "confidence": 4.0,
            "justification": "Essay A demonstrates superior vocabulary and structure.",
        },
        {
            "winner_id": "student::anchor_003",
            "loser_id": "student::anchor_005",
            "confidence": 3.5,
            "justification": "Better argumentation and clearer thesis.",
        },
        {
            "winner_id": "student::anchor_005",
            "loser_id": "student::anchor_007",
            "confidence": 3.0,
            "justification": "More comprehensive coverage of prompt points.",
        },
        {
            "winner_id": "student::anchor_007",
            "loser_id": "student::anchor_009",
            "confidence": 3.5,
            "justification": "Stronger concluding arguments.",
        },
        {
            "winner_id": "student::anchor_009",
            "loser_id": "student::anchor_011",
            "confidence": 4.0,
            "justification": "Clearer organization despite grammatical issues.",
        },
    ]


@pytest.fixture
def sample_comparisons_with_inversions() -> list[dict]:
    """Comparisons containing grade inversions for testing detection.

    Includes cases where lower-graded essays win against higher-graded.
    """
    return [
        # Normal: A beats B
        {
            "winner_id": "student::anchor_001",
            "loser_id": "student::anchor_003",
            "confidence": 4.0,
            "justification": "Superior vocabulary and structure.",
        },
        # INVERSION: E+ beats D-
        {
            "winner_id": "student::anchor_009",
            "loser_id": "student::anchor_008",
            "confidence": 3.5,
            "justification": "Clearer structure, deeper analysis.",
        },
        # INVERSION: F+ beats E-
        {
            "winner_id": "student::anchor_011",
            "loser_id": "student::anchor_010",
            "confidence": 3.5,
            "justification": "Better addresses assignment scope.",
        },
    ]
