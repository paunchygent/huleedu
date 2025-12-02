"""Pydantic schemas for docs/ frontmatter validation.

Covers:
- Runbooks in docs/operations/
- ADRs in docs/decisions/
- Epics in docs/product/epics/

Based on DOCS_STRUCTURE_SPEC.md requirements.
"""

from __future__ import annotations

from datetime import date
from typing import Literal, get_args

from pydantic import BaseModel, Field

# Type definitions using Literal for tight validation
RunbookSeverity = Literal["low", "medium", "high", "critical"]

DecisionStatus = Literal["proposed", "accepted", "superseded", "rejected"]

EpicStatus = Literal["draft", "active", "completed", "cancelled"]


class RunbookFrontmatter(BaseModel):
    """Schema for operations/ runbook files.

    Required fields per DOCS_STRUCTURE_SPEC.md section 5.
    """

    type: Literal["runbook"] = Field(
        default="runbook",
        description="Document type identifier",
    )

    service: str = Field(
        ...,
        description="Service this runbook applies to",
    )

    severity: RunbookSeverity = Field(
        ...,
        description="Incident severity level this runbook addresses",
    )

    last_reviewed: date = Field(
        ...,
        description="Date of last review (YYYY-MM-DD)",
    )


class DecisionFrontmatter(BaseModel):
    """Schema for decisions/ ADR files.

    Required fields per DOCS_STRUCTURE_SPEC.md section 6.
    """

    type: Literal["decision"] = Field(
        default="decision",
        description="Document type identifier",
    )

    id: str = Field(
        ...,
        description="Decision record ID (e.g., 'ADR-0019')",
        pattern=r"^ADR-\d{4}$",
    )

    status: DecisionStatus = Field(
        ...,
        description="Current status of the decision",
    )

    created: date = Field(
        ...,
        description="Date decision was created (YYYY-MM-DD)",
    )

    last_updated: date = Field(
        ...,
        description="Date of last update (YYYY-MM-DD)",
    )


class EpicFrontmatter(BaseModel):
    """Schema for product/epics/ files.

    Based on observed patterns in existing epic files.
    """

    type: Literal["epic"] = Field(
        default="epic",
        description="Document type identifier",
    )

    id: str = Field(
        ...,
        description="Epic ID (e.g., 'EPIC-007')",
        pattern=r"^EPIC-\d{3}$",
    )

    title: str = Field(
        ...,
        description="Epic title",
    )

    status: EpicStatus = Field(
        ...,
        description="Current epic status",
    )

    phase: int | None = Field(
        default=None,
        description="Current phase number",
    )

    sprint_target: str | None = Field(
        default=None,
        description="Target sprint identifier",
    )

    created: date = Field(
        ...,
        description="Date epic was created (YYYY-MM-DD)",
    )

    last_updated: date = Field(
        ...,
        description="Date of last update (YYYY-MM-DD)",
    )


def get_allowed_values() -> dict[str, list[str]]:
    """Return dict of field names to allowed values for CLI hints.

    Returns:
        Dict mapping enum field names to their allowed string values.
    """
    return {
        "runbook_severity": list(get_args(RunbookSeverity)),
        "decision_status": list(get_args(DecisionStatus)),
        "epic_status": list(get_args(EpicStatus)),
    }
