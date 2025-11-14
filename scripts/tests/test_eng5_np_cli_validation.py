"""CLI validation tests for ENG5 runner.

Skeleton suite aligned with:
- `.claude/tasks/TASK-ENG5-RUNNER-ASSUMPTION-HARDENING.md`
- `.claude/tasks/TASK-ENG5-RUNNER-TESTING-PLAN.md`

Covers Checkpoint 1 (R1, R2): comparison validation and batch UUID semantics.
"""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

import pytest

from scripts.cj_experiments_runners.eng5_np.inventory import (
    ComparisonValidationError,
    FileRecord,
    apply_comparison_limit,
)
from scripts.cj_experiments_runners.eng5_np.settings import RunnerMode, RunnerSettings


def _make_files(count: int) -> list[FileRecord]:
    """Create in-memory FileRecord instances for testing.

    We construct FileRecord directly rather than touching the filesystem to
    keep tests fast and deterministic.
    """

    return [FileRecord(path=Path(f"/fake/path/file_{i}.docx"), exists=True) for i in range(count)]


class TestEng5CliValidation:
    """Tests for ENG5 CLI validation and batch UUID behaviour.

    These tests are written to match the intent in:
    - `.claude/tasks/TASK-ENG5-RUNNER-ASSUMPTION-HARDENING.md`
    - `.claude/tasks/TASK-ENG5-RUNNER-TESTING-PLAN.md`

    These tests codify R1/R2 behaviour (comparison validation + canonical
    batch UUID). They serve as regression coverage for the hardened runner.
    """

    def test_apply_comparison_limit_rejects_max_comparisons_below_two(self) -> None:
        """`--max-comparisons < 2` should be rejected even with enough essays.

        Once R1 is implemented, either apply_comparison_limit or a dedicated
        validation helper should raise a clear error when max_comparisons < 2.
        """

        anchors = _make_files(3)
        students = _make_files(5)

        # Expected future behaviour: fail fast for max_comparisons < 2
        with pytest.raises(ComparisonValidationError):
            apply_comparison_limit(
                anchors=anchors,
                students=students,
                max_comparisons=1,
                emit_notice=False,
            )

    def test_apply_comparison_limit_rejects_when_no_pairs_possible(self) -> None:
        """Configurations with anchors×students < 1 should fail fast.

        For example: no anchors or no students should result in a clear
        validation error before we attempt to publish a batch.
        """

        anchors = _make_files(0)
        students = _make_files(5)

        with pytest.raises(ComparisonValidationError):
            apply_comparison_limit(
                anchors=anchors,
                students=students,
                max_comparisons=10,
                emit_notice=False,
            )

    def test_apply_comparison_limit_accepts_valid_configuration(self) -> None:
        """Valid configuration should pass and compute expected comparisons.

        After R1 is implemented, a configuration with anchors and students and
        `max_comparisons >= 2` should produce at least one comparison and no
        validation error.
        """

        anchors = _make_files(4)
        students = _make_files(10)

        limited_anchors, limited_students, actual = apply_comparison_limit(
            anchors=anchors,
            students=students,
            max_comparisons=9,
            emit_notice=False,
        )

        assert len(limited_anchors) >= 1
        assert len(limited_students) >= 1
        assert actual is not None
        assert actual >= 1

    def test_runner_settings_includes_canonical_batch_uuid(self) -> None:
        """RunnerSettings should expose a canonical batch_uuid alongside batch_id.

        This test encodes the desired contract: batch_id is a human label,
        while batch_uuid is the canonical ID used for cross-service tracing.
        """

        settings = RunnerSettings(
            assignment_id=UUID(int=1),
            course_id=UUID(int=2),
            grade_scale="eng5_np_legacy_9_step",
            mode=RunnerMode.PLAN,
            use_kafka=False,
            output_dir=Path("/tmp/out"),
            runner_version="0.1.0",
            git_sha="deadbeef",
            batch_uuid=UUID(int=4),
            batch_id="human-batch-label",
            user_id="user-1",
            org_id="org-1",
            course_code=None,  # type: ignore[arg-type]
            language=None,  # type: ignore[arg-type]
            correlation_id=UUID(int=3),
            kafka_bootstrap="kafka:9092",
            kafka_client_id="eng5-test",
            content_service_url="http://localhost:8001/v1/content",
        )

        assert isinstance(settings.batch_uuid, UUID)
        assert settings.batch_id == "human-batch-label"
