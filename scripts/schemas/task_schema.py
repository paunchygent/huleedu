"""Pydantic schema for TASKS frontmatter with type hints and validation."""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field
from pydantic.config import ConfigDict


class TaskStatus(str, Enum):
    """Allowed status values for task frontmatter."""

    proposed = "proposed"
    in_review = "in_review"
    approved = "approved"
    blocked = "blocked"
    in_progress = "in_progress"
    paused = "paused"
    done = "done"
    archived = "archived"


class TaskPriority(str, Enum):
    """Allowed priority values for task frontmatter."""

    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class TaskDomain(str, Enum):
    """Allowed domain values for task frontmatter."""

    assessment = "assessment"
    content = "content"
    identity = "identity"
    frontend = "frontend"
    infrastructure = "infrastructure"
    security = "security"
    integrations = "integrations"
    architecture = "architecture"
    programs = "programs"
    # Frontend-specific domains (for frontend/TASKS/)
    accessibility = "accessibility"
    integration = "integration"
    design = "design"


class TaskType(str, Enum):
    """Allowed task type categories for TASKS frontmatter.

    Keep this list in sync with TASKS/_REORGANIZATION_PROPOSAL.md and
    docs/reference/ref-tasks-overview.md.
    """

    task = "task"
    story = "story"
    programme = "programme"


class TaskFrontmatter(BaseModel):
    """Typed representation of task frontmatter used across agents and scripts."""

    id: str
    title: str
    type: TaskType = Field(default=TaskType.task)
    status: TaskStatus
    priority: TaskPriority
    domain: TaskDomain
    owner_team: str
    created: date
    last_updated: date
    service: Optional[str] = ""
    owner: Optional[str] = ""
    program: Optional[str] = ""
    related: list[str] = Field(default_factory=list)
    labels: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="allow")

    def _allowed_statuses_for_type(self) -> set[str]:
        if self.type == TaskType.story:
            return {
                TaskStatus.proposed.value,
                TaskStatus.in_review.value,
                TaskStatus.approved.value,
                TaskStatus.in_progress.value,
                TaskStatus.blocked.value,
                TaskStatus.paused.value,
                TaskStatus.done.value,
                TaskStatus.archived.value,
            }

        if self.type == TaskType.task:
            # Keep tasks lean: no review gate, but still support "proposed" as a backlog state.
            return {
                TaskStatus.proposed.value,
                TaskStatus.in_progress.value,
                TaskStatus.blocked.value,
                TaskStatus.paused.value,
                TaskStatus.done.value,
                TaskStatus.archived.value,
            }

        if self.type == TaskType.programme:
            return {
                TaskStatus.proposed.value,
                TaskStatus.in_progress.value,
                TaskStatus.blocked.value,
                TaskStatus.paused.value,
                TaskStatus.done.value,
                TaskStatus.archived.value,
            }

        # Docs in TASKS are excluded from validation today, but keep a sane default.
        return {e.value for e in TaskStatus}

    def model_post_init(self, __context: object) -> None:  # noqa: D401
        allowed = self._allowed_statuses_for_type()
        if self.status.value not in allowed:
            allowed_str = ", ".join(sorted(allowed))
            raise ValueError(
                f"status '{self.status.value}' invalid for type '{self.type.value}' "
                f"(allowed: {allowed_str})"
            )


def get_allowed_values() -> dict[str, list[str]]:
    """Return dict of field names to allowed values for CLI hints.

    Returns:
        Dict mapping enum field names to their allowed string values.
    """
    return {
        "status": [e.value for e in TaskStatus],
        "priority": [e.value for e in TaskPriority],
        "domain": [e.value for e in TaskDomain],
        "type": [e.value for e in TaskType],
    }
