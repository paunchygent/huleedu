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

ReferenceStatus = Literal["active", "deprecated"]

ResearchStatus = Literal["active", "archived"]

ReviewStatus = Literal["pending", "approved", "changes_requested", "rejected"]


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


class ReferenceFrontmatter(BaseModel):
    """Schema for reference/ files.

    Lean, agent-first: stable knowledge, conventions, checklists, or canonical mappings.
    """

    type: Literal["reference"] = Field(
        default="reference",
        description="Document type identifier",
    )

    id: str = Field(
        ...,
        description="Reference doc ID (e.g., 'REF-task-lifecycle-v2')",
        pattern=r"^REF-[a-z0-9]+(-[a-z0-9]+)*$",
    )

    title: str = Field(
        ...,
        description="Reference doc title",
    )

    status: ReferenceStatus = Field(
        ...,
        description="Current status of the reference doc",
    )

    created: date = Field(
        ...,
        description="Date doc was created (YYYY-MM-DD)",
    )

    last_updated: date = Field(
        ...,
        description="Date of last update (YYYY-MM-DD)",
    )

    topic: str | None = Field(
        default=None,
        description="Optional topic tag (free-form)",
    )


class ResearchFrontmatter(BaseModel):
    """Schema for research/ files.

    Exploratory but still structured: spikes, experiments, and investigation notes.
    """

    type: Literal["research"] = Field(
        default="research",
        description="Document type identifier",
    )

    id: str = Field(
        ...,
        description="Research doc ID (e.g., 'RES-task-lifecycle-v2-migration')",
        pattern=r"^RES-[a-z0-9]+(-[a-z0-9]+)*$",
    )

    title: str = Field(
        ...,
        description="Research doc title",
    )

    status: ResearchStatus = Field(
        ...,
        description="Current status of the research doc",
    )

    created: date = Field(
        ...,
        description="Date doc was created (YYYY-MM-DD)",
    )

    last_updated: date = Field(
        ...,
        description="Date of last update (YYYY-MM-DD)",
    )


class ReviewFrontmatter(BaseModel):
    """Schema for product/reviews/ files.

    Reviews are the canonical approval record for moving stories from proposed -> approved.
    """

    type: Literal["review"] = Field(
        default="review",
        description="Document type identifier",
    )

    id: str = Field(
        ...,
        description="Review doc ID (e.g., 'REV-us-0123-some-story')",
        pattern=r"^REV-[a-z0-9]+(-[a-z0-9]+)*$",
    )

    title: str = Field(
        ...,
        description="Review doc title",
    )

    status: ReviewStatus = Field(
        ...,
        description="Current status of the review",
    )

    created: date = Field(
        ...,
        description="Date review was created (YYYY-MM-DD)",
    )

    last_updated: date = Field(
        ...,
        description="Date of last update (YYYY-MM-DD)",
    )

    story: str | None = Field(
        default=None,
        description="Optional TASKS story id being reviewed (kebab-case)",
    )

    reviewer: str | None = Field(
        default=None,
        description="Optional reviewer handle",
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
        "reference_status": list(get_args(ReferenceStatus)),
        "research_status": list(get_args(ResearchStatus)),
        "review_status": list(get_args(ReviewStatus)),
    }
