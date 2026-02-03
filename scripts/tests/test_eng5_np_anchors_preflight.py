"""Tests for ENG5 anchor preflight."""

from __future__ import annotations

from uuid import uuid4

import pytest
from aioresponses import aioresponses

from scripts.cj_experiments_runners.eng5_np.anchors_preflight import (
    AnchorPreflightAuthError,
    AnchorPreflightConfigError,
    AnchorPreflightMissingAnchorsError,
    AnchorPreflightNotFoundError,
    resolve_anchor_preflight,
)


class TestAnchorPreflight:
    def test_preflight_anchor_summary_happy_path(self) -> None:
        assignment_id = uuid4()
        cj_service_url = "http://cj.local"
        url = f"{cj_service_url}/admin/v1/anchors/assignment/{assignment_id}"
        payload = {
            "assignment_id": str(assignment_id),
            "grade_scale": "eng5_np_legacy_9_step",
            "anchor_count": 2,
            "anchors": [
                {
                    "id": 1,
                    "assignment_id": str(assignment_id),
                    "anchor_label": "A1",
                    "grade": "A",
                    "grade_scale": "eng5_np_legacy_9_step",
                    "text_storage_id": "content-1",
                    "created_at": "2025-01-01T00:00:00Z",
                },
                {
                    "id": 2,
                    "assignment_id": str(assignment_id),
                    "anchor_label": "B1",
                    "grade": "B",
                    "grade_scale": "eng5_np_legacy_9_step",
                    "text_storage_id": "content-2",
                    "created_at": "2025-01-01T00:00:00Z",
                },
            ],
            "anchor_count_total": 2,
            "anchor_count_by_scale": {"eng5_np_legacy_9_step": 2},
        }

        with aioresponses() as mocked:
            mocked.get(url, status=200, payload=payload)
            result = resolve_anchor_preflight(
                assignment_id=assignment_id,
                cj_service_url=cj_service_url,
                headers={"Authorization": "Bearer test", "Content-Type": "application/json"},
            )

        assert result.assignment_id == str(assignment_id)
        assert result.grade_scale == "eng5_np_legacy_9_step"
        assert result.anchor_count == 2

    def test_preflight_anchor_summary_404_is_user_guidance(self) -> None:
        assignment_id = uuid4()
        cj_service_url = "http://cj.local"
        url = f"{cj_service_url}/admin/v1/anchors/assignment/{assignment_id}"

        with aioresponses() as mocked:
            mocked.get(url, status=404, body="not found")
            with pytest.raises(AnchorPreflightNotFoundError) as excinfo:
                resolve_anchor_preflight(
                    assignment_id=assignment_id,
                    cj_service_url=cj_service_url,
                    headers={"Authorization": "Bearer test", "Content-Type": "application/json"},
                )

        assert "assessment_instructions" in str(excinfo.value)

    def test_preflight_anchor_summary_auth_error_on_401_or_403(self) -> None:
        assignment_id = uuid4()
        cj_service_url = "http://cj.local"
        url = f"{cj_service_url}/admin/v1/anchors/assignment/{assignment_id}"

        with aioresponses() as mocked:
            mocked.get(url, status=403, body="forbidden")
            with pytest.raises(AnchorPreflightAuthError):
                resolve_anchor_preflight(
                    assignment_id=assignment_id,
                    cj_service_url=cj_service_url,
                    headers={"Authorization": "Bearer test", "Content-Type": "application/json"},
                )

    def test_preflight_anchor_summary_config_error_on_missing_url_or_token(self) -> None:
        assignment_id = uuid4()
        with pytest.raises(AnchorPreflightConfigError):
            resolve_anchor_preflight(
                assignment_id=assignment_id,
                cj_service_url=None,
                headers={"Authorization": "Bearer test", "Content-Type": "application/json"},
            )

    def test_preflight_anchor_summary_fails_when_anchor_count_is_zero(self) -> None:
        assignment_id = uuid4()
        cj_service_url = "http://cj.local"
        url = f"{cj_service_url}/admin/v1/anchors/assignment/{assignment_id}"
        payload = {
            "assignment_id": str(assignment_id),
            "grade_scale": "eng5_np_legacy_9_step",
            "anchor_count": 0,
            "anchors": [],
            "anchor_count_total": 0,
            "anchor_count_by_scale": {},
        }

        with aioresponses() as mocked:
            mocked.get(url, status=200, payload=payload)
            with pytest.raises(AnchorPreflightMissingAnchorsError):
                resolve_anchor_preflight(
                    assignment_id=assignment_id,
                    cj_service_url=cj_service_url,
                    headers={"Authorization": "Bearer test", "Content-Type": "application/json"},
                )
