"""Language Tool Service HTTP API contracts.

This module defines the inter-service HTTP contracts for the Language Tool Service.
These models are used by the NLP Service when calling the Language Tool Service.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# ====================================================================
# Request Models
# ====================================================================


class GrammarCheckRequest(BaseModel):
    """Request model for Language Tool Service grammar check endpoint.

    Used by NLP Service when requesting grammar analysis.
    """

    text: str = Field(
        ...,
        min_length=1,
        max_length=50000,
        description="Text content to check for grammar errors",
    )
    language: str = Field(
        default="en-US",
        pattern="^([a-z]{2}-[A-Z]{2}|auto)$",
        description="Language code for grammar checking (e.g., en-US, sv-SE, auto)",
    )
    level: Literal["default", "picky"] | None = Field(
        default=None,
        description="LanguageTool rule activation level. Use 'picky' for stricter checks.",
    )
    enabled_categories: list[str] | None = Field(
        default=None,
        alias="enabledCategories",
        description="LanguageTool categories to explicitly enable (e.g., GRAMMAR,STYLE)",
    )
    disabled_categories: list[str] | None = Field(
        default=None,
        alias="disabledCategories",
        description="LanguageTool categories to disable.",
    )
    enabled_rules: list[str] | None = Field(
        default=None,
        alias="enabledRules",
        description="Specific LanguageTool rule IDs to enable.",
    )
    disabled_rules: list[str] | None = Field(
        default=None,
        alias="disabledRules",
        description="Specific LanguageTool rule IDs to disable.",
    )
    enabled_only: bool | None = Field(
        default=None,
        alias="enabledOnly",
        description="If true, only the explicitly enabled categories/rules are applied.",
    )

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    def to_languagetool_payload(self) -> dict[str, str]:
        """Convert request options into LanguageTool HTTP API parameters."""

        payload: dict[str, str] = {}

        if self.level:
            payload["level"] = self.level

        if self.enabled_categories:
            payload["enabledCategories"] = ",".join(self.enabled_categories)

        if self.disabled_categories:
            payload["disabledCategories"] = ",".join(self.disabled_categories)

        if self.enabled_rules:
            payload["enabledRules"] = ",".join(self.enabled_rules)

        if self.disabled_rules:
            payload["disabledRules"] = ",".join(self.disabled_rules)

        if self.enabled_only is not None:
            payload["enabledOnly"] = "true" if self.enabled_only else "false"

        return payload


# ====================================================================
# Response Models
# ====================================================================


class GrammarCheckResponse(BaseModel):
    """Response model from Language Tool Service grammar check endpoint.

    Returns grammar analysis results to the NLP Service.
    Note: The errors field contains serialized GrammarError objects from
    common_core.events.nlp_events for consistency with event-driven architecture.
    """

    errors: list[dict[str, Any]] = Field(
        default_factory=list,
        description="List of grammar errors found (serialized GrammarError objects)",
    )
    total_grammar_errors: int = Field(
        ...,
        ge=0,
        description="Total number of grammar errors found",
    )
    grammar_category_counts: dict[str, int] = Field(
        default_factory=dict,
        description="Error count by category (e.g., GRAMMAR: 2, PUNCTUATION: 1)",
    )
    grammar_rule_counts: dict[str, int] = Field(
        default_factory=dict,
        description="Error count by rule ID",
    )
    language: str = Field(
        ...,
        description="Language used for checking",
    )
    processing_time_ms: int = Field(
        ...,
        ge=0,
        description="Time taken to process the request in milliseconds",
    )
