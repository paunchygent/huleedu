"""Pydantic schema for TASKS frontmatter to provide type hints and validation."""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    research = "research"
    blocked = "blocked"
    in_progress = "in_progress"
    paused = "paused"
    completed = "completed"
    archived = "archived"


class TaskPriority(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class TaskDomain(str, Enum):
    assessment = "assessment"
    content = "content"
    identity = "identity"
    frontend = "frontend"
    infrastructure = "infrastructure"
    security = "security"
    integrations = "integrations"
    architecture = "architecture"
    programs = "programs"


class TaskFrontmatter(BaseModel):
    """Typed representation of task frontmatter used across agents and scripts."""

    id: str
    title: str
    type: str = Field(default="task")
    status: TaskStatus
    priority: TaskPriority
    domain: TaskDomain
    owner_team: str
    created: date
    last_updated: date
    service: Optional[str] = ""
    owner: Optional[str] = ""
    program: Optional[str] = ""
    related: List[str] = Field(default_factory=list)
    labels: List[str] = Field(default_factory=list)

    class Config:
        extra = "allow"  # be tolerant of ancillary fields while providing type hints
