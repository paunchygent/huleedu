"""ENG5 runner preflight helpers for CJ anchor availability.

ENG5 execute runs are student-only: anchors must already exist in CJ (DB-owned).
This module resolves the CJ anchor summary via admin endpoints and provides
strict failure behaviour when anchors are missing for the instruction grade_scale.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import aiohttp
from common_core.api_models.anchor_summary import AnchorSummaryResponse

from scripts.cj_experiments_runners.eng5_np.cj_client import build_admin_headers


class AnchorPreflightError(RuntimeError):
    """Base error for anchor preflight failures."""


class AnchorPreflightConfigError(AnchorPreflightError):
    """Raised when required configuration (URL/token) is missing."""


class AnchorPreflightAuthError(AnchorPreflightError):
    """Raised when CJ admin rejects authentication."""


class AnchorPreflightNotFoundError(AnchorPreflightError):
    """Raised when CJ has no instructions for the given assignment."""


class AnchorPreflightMissingAnchorsError(AnchorPreflightError):
    """Raised when CJ reports no anchors for the assignment grade_scale."""


@dataclass(frozen=True)
class AnchorPreflightResult:
    assignment_id: str
    grade_scale: str
    anchor_count: int
    anchor_count_total: int
    anchor_count_by_scale: dict[str, int]


def resolve_anchor_preflight(
    *,
    assignment_id: UUID | str,
    cj_service_url: str | None,
    headers: dict[str, str] | None = None,
) -> AnchorPreflightResult:
    """Resolve anchor availability from CJ admin API.

    Raises:
        AnchorPreflightConfigError: Missing URL/token configuration.
        AnchorPreflightAuthError: 401/403 from CJ admin surface.
        AnchorPreflightNotFoundError: 404 for missing instructions/assignment.
        AnchorPreflightMissingAnchorsError: anchor_count==0 for instruction grade_scale.
        AnchorPreflightError: Any other HTTP/client error.
    """
    if not cj_service_url:
        raise AnchorPreflightConfigError(
            "CJ service URL is required for anchor preflight. "
            "Set --cj-service-url or CJ_SERVICE_URL."
        )

    assignment_id_str = str(assignment_id)
    try:
        admin_headers = headers or build_admin_headers()
    except RuntimeError as exc:
        raise AnchorPreflightConfigError(str(exc)) from exc

    async def _fetch() -> AnchorPreflightResult:
        timeout = aiohttp.ClientTimeout(total=15)
        url = f"{cj_service_url.rstrip('/')}/admin/v1/anchors/assignment/{assignment_id_str}"
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, headers=admin_headers) as response:
                if response.status == 200:
                    payload: Any = await response.json()
                    model = AnchorSummaryResponse.model_validate(payload)
                    result = AnchorPreflightResult(
                        assignment_id=model.assignment_id,
                        grade_scale=model.grade_scale,
                        anchor_count=model.anchor_count,
                        anchor_count_total=model.anchor_count_total,
                        anchor_count_by_scale=dict(model.anchor_count_by_scale),
                    )
                    if result.anchor_count <= 0:
                        raise AnchorPreflightMissingAnchorsError(
                            "CJ reports zero anchors for assignment_id="
                            f"{assignment_id_str} grade_scale={result.grade_scale}. "
                            "Run one-time anchor registration "
                            "(`pdm run eng5-np-run register-anchors ...`) "
                            "or seed anchors via CJ admin workflows."
                        )
                    return result

                body = await response.text()
                if response.status == 404:
                    raise AnchorPreflightNotFoundError(
                        "CJ has no anchor summary for assignment_id="
                        f"{assignment_id_str}. Ensure assessment_instructions exist first "
                        "via `pdm run cj-admin instructions upsert ...`."
                    )
                if response.status in {401, 403}:
                    raise AnchorPreflightAuthError(
                        "CJ admin authentication failed (status="
                        f"{response.status}). Ensure a valid admin token is available "
                        "(HULEEDU_SERVICE_ACCOUNT_TOKEN/HULEEDU_ADMIN_TOKEN) or run "
                        "`pdm run eng5-np-run verify-auth` to confirm auth wiring."
                    )
                raise AnchorPreflightError(
                    f"CJ anchor preflight failed (status={response.status}): {body[:200]}"
                )

    return asyncio.run(_fetch())
