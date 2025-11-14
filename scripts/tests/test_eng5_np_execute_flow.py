"""ENG5 execute flow tests.

Skeleton suite aligned with:
- `.claude/tasks/TASK-ENG5-RUNNER-ASSUMPTION-HARDENING.md`
- `.claude/tasks/TASK-ENG5-RUNNER-TESTING-PLAN.md`

Covers Checkpoint 3 (R4, R5): anchors as precondition and optional DB extraction.
"""

from __future__ import annotations

import pytest


class TestEng5ExecuteFlow:
    """TDD markers for ENG5 execute flow behaviour.

    These tests are aligned with:
    - `.claude/tasks/TASK-ENG5-RUNNER-ASSUMPTION-HARDENING.md`
    - `.claude/tasks/TASK-ENG5-RUNNER-TESTING-PLAN.md`

    They are marked as xfail until the anchor precondition and optional DB
    extraction wiring are implemented.
    """

    @pytest.mark.xfail(reason="R4: anchor precondition not enforced yet", strict=False)
    def test_execute_fails_fast_when_anchors_missing(self) -> None:
        """`execute` should fail fast when required anchors are missing in CJ."""

        raise NotImplementedError

    @pytest.mark.xfail(reason="R4: anchor precondition not enforced yet", strict=False)
    def test_execute_skips_anchor_upload_when_anchors_present(self) -> None:
        """`execute` should not upload anchors when CJ reports anchors as present."""

        raise NotImplementedError

    @pytest.mark.xfail(reason="R5: auto-extraction flag not implemented yet", strict=False)
    def test_execute_runs_db_extraction_when_auto_flag_set(self) -> None:
        """`--auto-extract-eng5-db` should trigger extraction after success."""

        raise NotImplementedError

    @pytest.mark.xfail(reason="R5: auto-extraction flag not implemented yet", strict=False)
    def test_execute_does_not_run_extraction_when_flag_not_set(self) -> None:
        """Extraction should not run when `--auto-extract-eng5-db` is omitted."""

        raise NotImplementedError

    @pytest.mark.xfail(reason="R5: auto-extraction failure handling not implemented", strict=False)
    def test_execute_reports_extraction_failure_but_not_batch_failure(self) -> None:
        """Extraction failure should be reported without hiding batch success."""

        raise NotImplementedError
