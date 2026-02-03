"""ENG5 runner preflight helpers for CJ assignment metadata.

The ENG5 runner treats CJ Assessment Service as the source of truth for
assignment configuration (notably `grade_scale`). This module provides a small,
testable preflight that resolves assignment metadata via CJ admin endpoints.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import aiohttp
from common_core.api_models.assessment_instructions import AssessmentInstructionResponse

from scripts.cj_experiments_runners.eng5_np.cj_client import build_admin_headers


class AssignmentPreflightError(RuntimeError):
    """Base error for assignment preflight failures."""


class AssignmentPreflightConfigError(AssignmentPreflightError):
    """Raised when required configuration (URL/token) is missing."""


class AssignmentPreflightAuthError(AssignmentPreflightError):
    """Raised when CJ admin rejects authentication."""


class AssignmentPreflightNotFoundError(AssignmentPreflightError):
    """Raised when CJ has no instructions for the given assignment."""


@dataclass(frozen=True)
class AssignmentPreflightResult:
    """Resolved, CJ-owned assignment configuration."""

    assignment_id: str
    grade_scale: str
    context_origin: str
    student_prompt_storage_id: str | None


def resolve_assignment_preflight(
    *,
    assignment_id: UUID | str,
    cj_service_url: str | None,
    headers: dict[str, str] | None = None,
) -> AssignmentPreflightResult:
    """Resolve assignment metadata from CJ admin API.

    Args:
        assignment_id: Assignment identifier (UUID or string).
        cj_service_url: Base URL for CJ service (e.g. http://localhost:9095).
        headers: Optional override for admin headers (primarily for tests).

    Raises:
        AssignmentPreflightConfigError: Missing URL/token configuration.
        AssignmentPreflightAuthError: 401/403 from CJ admin surface.
        AssignmentPreflightNotFoundError: 404 for assignment instruction.
        AssignmentPreflightError: Any other HTTP/client error.
    """
    if not cj_service_url:
        raise AssignmentPreflightConfigError(
            "CJ service URL is required for assignment preflight. "
            "Set --cj-service-url or CJ_SERVICE_URL."
        )

    assignment_id_str = str(assignment_id)
    try:
        admin_headers = headers or build_admin_headers()
    except RuntimeError as exc:
        raise AssignmentPreflightConfigError(str(exc)) from exc

    async def _fetch() -> AssignmentPreflightResult:
        timeout = aiohttp.ClientTimeout(total=15)
        url = (
            f"{cj_service_url.rstrip('/')}"
            f"/admin/v1/assessment-instructions/assignment/{assignment_id_str}"
        )
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, headers=admin_headers) as response:
                if response.status == 200:
                    payload: Any = await response.json()
                    model = AssessmentInstructionResponse.model_validate(payload)
                    if not model.assignment_id:
                        raise AssignmentPreflightError(
                            "CJ returned an invalid instruction payload: assignment_id is missing."
                        )
                    return AssignmentPreflightResult(
                        assignment_id=model.assignment_id,
                        grade_scale=model.grade_scale,
                        context_origin=model.context_origin,
                        student_prompt_storage_id=model.student_prompt_storage_id,
                    )

                body = await response.text()
                if response.status == 404:
                    raise AssignmentPreflightNotFoundError(
                        "No assessment instructions found in CJ for assignment_id="
                        f"{assignment_id_str}. Seed it via the CJ admin CLI, e.g. "
                        "`pdm run cj-admin instructions upsert ...` or "
                        "`pdm run cj-admin instructions list`."
                    )
                if response.status in {401, 403}:
                    raise AssignmentPreflightAuthError(
                        "CJ admin authentication failed (status="
                        f"{response.status}). Ensure a valid admin token is available "
                        "(HULEEDU_SERVICE_ACCOUNT_TOKEN/HULEEDU_ADMIN_TOKEN) or run "
                        "`pdm run eng5-np-run verify-auth` to confirm auth wiring."
                    )
                raise AssignmentPreflightError(
                    f"CJ assignment preflight failed (status={response.status}): {body[:200]}"
                )

    return asyncio.run(_fetch())
