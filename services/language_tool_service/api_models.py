"""Internal API models for Language Tool Service.

This module contains ONLY intra-service models that are never exposed to other services.
Inter-service contracts are defined in common_core.api_models.language_tool.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

# ====================================================================
# Internal Models (not exposed to other services)
# ====================================================================


class LanguageToolRawResponse(BaseModel):
    """Raw response from LanguageTool Java process.

    This is an internal model for deserializing LanguageTool output
    before converting to common_core.GrammarError objects.
    This model is NEVER exposed to other services.
    """

    matches: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Raw matches from LanguageTool Java process",
    )
    language: dict[str, str] = Field(
        ...,
        description="Detected/used language information from LanguageTool",
    )
    software: dict[str, Any] = Field(
        default=None,
        description="LanguageTool software version information",
    )
    warnings: dict[str, Any] = Field(
        default=None,
        description="Any warnings from LanguageTool processing",
    )


class LanguageToolMatch(BaseModel):
    """Internal model for a single LanguageTool match.

    Used internally to parse LanguageTool Java output before
    converting to GrammarError objects.
    """

    message: str = Field(..., description="Error message")
    shortMessage: str = Field(default="", description="Short error message")
    offset: int = Field(..., description="Character offset in text")
    length: int = Field(..., description="Length of the error")
    replacements: list[dict[str, str]] = Field(
        default_factory=list,
        description="Suggested replacements",
    )
    context: dict[str, Any] = Field(..., description="Error context")
    sentence: str = Field(..., description="Sentence containing the error")
    type: dict[str, str] = Field(..., description="Error type information")
    rule: dict[str, Any] = Field(..., description="Grammar rule information")
    ignoreForIncompleteSentence: bool = Field(
        default=False,
        description="Whether to ignore for incomplete sentences",
    )
    contextForSureMatch: int = Field(
        default=0,
        description="Context confidence for match",
    )
