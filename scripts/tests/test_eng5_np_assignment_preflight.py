"""Tests for ENG5 assignment metadata preflight."""

from __future__ import annotations

from uuid import uuid4

import pytest
from aioresponses import aioresponses

from scripts.cj_experiments_runners.eng5_np.assignment_preflight import (
    AssignmentPreflightAuthError,
    AssignmentPreflightConfigError,
    AssignmentPreflightNotFoundError,
    resolve_assignment_preflight,
)


class TestAssignmentPreflight:
    def test_preflight_assignment_metadata_happy_path(self) -> None:
        """Resolves assignment metadata successfully from CJ admin API."""

        assignment_id = uuid4()
        cj_service_url = "http://cj.local"
        url = f"{cj_service_url}/admin/v1/assessment-instructions/assignment/{assignment_id}"
        payload = {
            "id": 1,
            "assignment_id": str(assignment_id),
            "course_id": None,
            "instructions_text": "x" * 20,
            "grade_scale": "eng5_np_legacy_9_step",
            "student_prompt_storage_id": None,
            "created_at": "2025-01-01T00:00:00Z",
        }

        with aioresponses() as mocked:
            mocked.get(url, status=200, payload=payload)
            result = resolve_assignment_preflight(
                assignment_id=assignment_id,
                cj_service_url=cj_service_url,
                headers={"Authorization": "Bearer test", "Content-Type": "application/json"},
            )

        assert result.assignment_id == str(assignment_id)
        assert result.grade_scale == "eng5_np_legacy_9_step"

    def test_preflight_assignment_metadata_404_gives_user_guidance(self) -> None:
        """404 from CJ admin should guide user to cj-admin instructions commands."""

        assignment_id = uuid4()
        cj_service_url = "http://cj.local"
        url = f"{cj_service_url}/admin/v1/assessment-instructions/assignment/{assignment_id}"

        with aioresponses() as mocked:
            mocked.get(url, status=404, body="not found")
            with pytest.raises(AssignmentPreflightNotFoundError) as excinfo:
                resolve_assignment_preflight(
                    assignment_id=assignment_id,
                    cj_service_url=cj_service_url,
                    headers={"Authorization": "Bearer test", "Content-Type": "application/json"},
                )

        assert "cj-admin instructions" in str(excinfo.value)

    def test_preflight_assignment_metadata_auth_error_on_401_or_403(self) -> None:
        """401/403 from CJ admin should surface as configuration/auth errors."""

        assignment_id = uuid4()
        cj_service_url = "http://cj.local"
        url = f"{cj_service_url}/admin/v1/assessment-instructions/assignment/{assignment_id}"

        with aioresponses() as mocked:
            mocked.get(url, status=401, body="unauthorized")
            with pytest.raises(AssignmentPreflightAuthError):
                resolve_assignment_preflight(
                    assignment_id=assignment_id,
                    cj_service_url=cj_service_url,
                    headers={"Authorization": "Bearer test", "Content-Type": "application/json"},
                )

    def test_preflight_assignment_metadata_config_error_on_missing_url_or_token(self) -> None:
        """Missing/invalid CJ admin URL or token should raise config error."""

        assignment_id = uuid4()
        with pytest.raises(AssignmentPreflightConfigError):
            resolve_assignment_preflight(
                assignment_id=assignment_id,
                cj_service_url=None,
                headers={"Authorization": "Bearer test", "Content-Type": "application/json"},
            )
