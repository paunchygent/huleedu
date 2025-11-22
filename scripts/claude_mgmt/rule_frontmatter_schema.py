#!/usr/bin/env python3
"""
Minimal Pydantic schema for .claude/rules/ frontmatter validation.

Based on comprehensive analysis of all 92 HuleEdu rules and critical evaluation
of operational value for each field.

Design Principles:
- Minimal: Only 8 fields (5 required, 3 optional)
- Purposeful: Every field has clear operational value
- Lintable: Ruff + MyPy compatible with Literal enums
- Type-safe: Strict validation with business rules
- Maintainable: No fuzzy metadata, no over-engineering

Analysis reports: .claude/work/reports/2025-11-22-rule-analysis-batch-{1,2,3,4-FINAL}.md
"""

from __future__ import annotations

import re
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

# =============================================================================
# Type Definitions (Tight, Meaningful Enums)
# =============================================================================

RuleType = Literal[
    "service",  # Service-specific architecture (020.X series)
    "architecture",  # System design, patterns, boundaries
    "implementation",  # Code patterns, DI, async, error handling
    "workflow",  # Processing flows, sequences (035-037 series)
    "testing",  # Test methodologies, debugging patterns
    "observability",  # Metrics, logs, traces (071.X series)
    "standards",  # Coding standards, conventions (050, 082, etc.)
    "operational",  # Guides, runbooks, how-tos
    "library",  # External libraries and usage patterns (Pydantic, SQLAlchemy)
]

RuleScope = Literal[
    "all",  # Entire codebase
    "backend",  # All backend services
    "frontend",  # UI layer
    "infrastructure",  # DevOps, containers, deployment
    "cross-service",  # Multi-service interactions
    "testing",  # Test infrastructure
    "documentation",  # Documentation system
]


# =============================================================================
# Pydantic Model (Minimal, 8 Fields)
# =============================================================================


class RuleFrontmatter(BaseModel):
    """
    Minimal frontmatter schema for HuleEdu .claude/rules/ files.

    8 fields total:
    - 5 required: id, type, created, last_updated, scope
    - 3 optional: parent_rule, child_rules, service_name

    All fields validated for type safety and business rules.
    """

    # -------------------------------------------------------------------------
    # Required Fields (5)
    # -------------------------------------------------------------------------

    id: str = Field(
        ...,
        description="Rule ID matching filename stem (e.g., '020.7-cj-assessment-service')",
        pattern=r"^\d{3}(?:\.\d+)?-[a-z0-9-]+$",
    )

    type: RuleType = Field(
        ...,
        description="Rule type from tight 9-value taxonomy",
    )

    created: date = Field(
        ...,
        description="Date rule was created (YYYY-MM-DD) - audit trail",
    )

    last_updated: date = Field(
        ...,
        description="Date of last significant update (YYYY-MM-DD) - staleness indicator",
    )

    scope: RuleScope = Field(
        ...,
        description="Where this rule applies (technical scope)",
    )

    # -------------------------------------------------------------------------
    # Optional Fields (3)
    # -------------------------------------------------------------------------

    parent_rule: str | None = Field(
        default=None,
        description="Parent rule ID for sub-rules (e.g., '020' for '020.7')",
        pattern=r"^\d{3}-[a-z0-9-]+$",
    )

    child_rules: list[str] | None = Field(
        default=None,
        description="List of child rule IDs for parent rules",
    )

    service_name: str | None = Field(
        default=None,
        description="Service name for service-type rules (e.g., 'cj_assessment_service')",
        pattern=r"^[a-z][a-z0-9_]*$",
    )

    # -------------------------------------------------------------------------
    # Validators
    # -------------------------------------------------------------------------

    @field_validator("id")
    @classmethod
    def validate_id_format(cls, v: str) -> str:
        """Validate rule ID follows NNN-name or NNN.N-name pattern."""
        if not re.match(r"^\d{3}(?:\.\d+)?-[a-z0-9-]+$", v):
            msg = f"Rule ID '{v}' must match pattern 'NNN-name' or 'NNN.N-name'"
            raise ValueError(msg)
        return v

    @field_validator("parent_rule")
    @classmethod
    def validate_parent_format(cls, v: str | None) -> str | None:
        """Validate parent rule ID format if provided."""
        if v is not None and not re.match(r"^\d{3}-[a-z0-9-]+$", v):
            msg = f"Parent rule ID '{v}' must match pattern 'NNN-name' (no decimal)"
            raise ValueError(msg)
        return v

    @field_validator("child_rules")
    @classmethod
    def validate_child_format(cls, v: list[str] | None) -> list[str] | None:
        """Validate all child rule IDs follow correct format."""
        if v is not None:
            for child_id in v:
                if not re.match(r"^\d{3}(?:\.\d+)?-[a-z0-9-]+$", child_id):
                    msg = (
                        f"Child rule ID '{child_id}' must match pattern 'NNN-name' or 'NNN.N-name'"
                    )
                    raise ValueError(msg)
        return v

    @field_validator("last_updated")
    @classmethod
    def validate_last_updated_after_created(cls, v: date, info) -> date:
        """Ensure last_updated is not before created date."""
        if "created" in info.data and v < info.data["created"]:
            msg = f"last_updated ({v}) cannot be before created ({info.data['created']})"
            raise ValueError(msg)
        return v

    @model_validator(mode="after")
    def validate_service_type_has_service_name(self) -> RuleFrontmatter:
        """Ensure service-type rules have service_name."""
        if self.type == "service" and not self.service_name:
            msg = "Rules with type='service' must have service_name field"
            raise ValueError(msg)
        return self

    @model_validator(mode="after")
    def validate_sub_rule_has_parent(self) -> RuleFrontmatter:
        """Ensure sub-rules (X.Y format) have parent_rule field."""
        if "." in self.id and not self.parent_rule:
            msg = f"Sub-rule '{self.id}' must have parent_rule field"
            raise ValueError(msg)
        return self

    @model_validator(mode="after")
    def validate_parent_child_consistency(self) -> RuleFrontmatter:
        """Ensure parent rules don't have parent_rule field."""
        if self.child_rules and self.parent_rule:
            msg = f"Rule '{self.id}' cannot be both a parent and a child"
            raise ValueError(msg)
        return self


# =============================================================================
# Example Usage
# =============================================================================

if __name__ == "__main__":
    from datetime import date

    # Example 1: Service rule
    service_rule = RuleFrontmatter(
        id="020.7-cj-assessment-service",
        type="service",
        created=date(2025, 6, 15),
        last_updated=date(2025, 11, 20),
        scope="backend",
        parent_rule="020-architectural-mandates",
        service_name="cj_assessment_service",
    )

    print("✓ Valid service rule:")
    print(service_rule.model_dump_json(indent=2))

    # Example 2: Architecture rule
    arch_rule = RuleFrontmatter(
        id="030-event-driven-architecture-eda-standards",
        type="architecture",
        created=date(2025, 5, 1),
        last_updated=date(2025, 11, 18),
        scope="all",
    )

    print("\n✓ Valid architecture rule:")
    print(arch_rule.model_dump_json(indent=2))

    # Example 3: Observability parent with children
    obs_parent = RuleFrontmatter(
        id="071-observability-index",
        type="observability",
        created=date(2025, 7, 1),
        last_updated=date(2025, 11, 15),
        scope="backend",
        child_rules=[
            "071.1-observability-core-patterns",
            "071.2-prometheus-metrics-patterns",
            "071.3-jaeger-tracing-patterns",
            "071.4-grafana-loki-patterns",
            "071.5-llm-debugging-with-observability",
        ],
    )

    print("\n✓ Valid observability parent:")
    print(obs_parent.model_dump_json(indent=2))

    # Example 4: Library rule
    library_rule = RuleFrontmatter(
        id="051-pydantic-v2-standards",
        type="library",
        created=date(2025, 6, 10),
        last_updated=date(2025, 11, 15),
        scope="backend",
    )

    print("\n✓ Valid library rule:")
    print(library_rule.model_dump_json(indent=2))
