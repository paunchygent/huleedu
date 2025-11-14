"""Tests for ENG5 assignment metadata preflight.

These tests validate the preflight helper that resolves assignment metadata
from the CJ admin API before ENG5 runner modes (`plan`, `execute`, `register-anchors`).

See `.claude/tasks/TASK-ENG5-RUNNER-TESTING-PLAN.md` for the full test plan.
"""

from __future__ import annotations

from uuid import uuid4

import pytest


class TestAssignmentPreflight:
    """TDD markers for ENG5 assignment metadata preflight.

    These tests are aligned with:
    - `.claude/tasks/TASK-ENG5-RUNNER-ASSUMPTION-HARDENING.md`
    - `.claude/tasks/TASK-ENG5-RUNNER-TESTING-PLAN.md`

    They are marked as xfail until the CJ assignment preflight helper is
    implemented and wired into the ENG5 CLI.
    """

    @pytest.mark.xfail(reason="R3: assignment preflight helper not implemented", strict=False)
    def test_preflight_assignment_metadata_happy_path(self) -> None:
        """Resolves assignment metadata successfully from CJ admin API."""

        # TODO: implement using HTTP client mocking (e.g., responses or httpx_mock)
        raise NotImplementedError

    @pytest.mark.xfail(reason="R3: assignment preflight helper not implemented", strict=False)
    def test_preflight_assignment_metadata_404_gives_user_guidance(self) -> None:
        """404 from CJ admin should guide user to cj-admin instructions commands."""

        raise NotImplementedError

    @pytest.mark.xfail(reason="R3: assignment preflight helper not implemented", strict=False)
    def test_preflight_assignment_metadata_auth_error_on_401_or_403(self) -> None:
        """401/403 from CJ admin should surface as configuration/auth errors."""

        raise NotImplementedError

    @pytest.mark.xfail(reason="R3: assignment preflight helper not implemented", strict=False)
    def test_preflight_assignment_metadata_config_error_on_missing_url_or_token(self) -> None:
        """Missing/invalid CJ admin URL or token should raise config error."""

        raise NotImplementedError

    @pytest.mark.xfail(reason="R3: assignment preflight helper not implemented", strict=False)
    def test_preflight_assignment_metadata_logs_correlation_id(self) -> None:
        """Correlation ID should propagate into logs and headers."""

        _ = uuid4()  # placeholder to prevent unused import for now
        raise NotImplementedError
