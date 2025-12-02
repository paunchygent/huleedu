"""Consolidated frontmatter schemas for HuleEdu documentation system.

This package provides Pydantic schemas for validating frontmatter in:
- TASKS/ markdown files (task_schema)
- .claude/rules/ markdown files (rule_schema)
- docs/ markdown files (docs_schema)

Each schema module also exports a get_allowed_values() helper for CLI hints.
"""

from scripts.schemas.docs_schema import (
    DecisionFrontmatter,
    DecisionStatus,
    EpicFrontmatter,
    EpicStatus,
    RunbookFrontmatter,
    RunbookSeverity,
)
from scripts.schemas.rule_schema import (
    RuleFrontmatter,
    RuleScope,
    RuleType,
)
from scripts.schemas.task_schema import (
    TaskDomain,
    TaskFrontmatter,
    TaskPriority,
    TaskStatus,
    TaskType,
)

__all__ = [
    # Task schema
    "TaskFrontmatter",
    "TaskStatus",
    "TaskPriority",
    "TaskDomain",
    "TaskType",
    # Rule schema
    "RuleFrontmatter",
    "RuleType",
    "RuleScope",
    # Docs schema
    "RunbookFrontmatter",
    "RunbookSeverity",
    "DecisionFrontmatter",
    "DecisionStatus",
    "EpicFrontmatter",
    "EpicStatus",
]
