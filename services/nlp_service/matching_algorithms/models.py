"""Data models for the extraction and matching pipeline."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ExtractedIdentifier(BaseModel):
    """A single piece of information extracted from text."""

    value: str = Field(description="The extracted string (e.g., a name or email)")
    source_strategy: str = Field(description="The strategy that extracted this value")
    confidence: float = Field(
        ge=0.0, le=1.0, description="Extraction confidence (0.0 to 1.0)"
    )
    location_hint: str = Field(default="", description="Where in text it was found")


class ExtractionResult(BaseModel):
    """Consolidated output from the extraction pipeline."""

    possible_names: list[ExtractedIdentifier] = Field(default_factory=list)
    possible_emails: list[ExtractedIdentifier] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict, description="Extra info")

    def is_empty(self) -> bool:
        """Check if any identifiers were extracted."""
        return not self.possible_names and not self.possible_emails

    def highest_confidence_name(self) -> ExtractedIdentifier | None:
        """Get the name with highest extraction confidence."""
        if not self.possible_names:
            return None
        return max(self.possible_names, key=lambda x: x.confidence)

    def highest_confidence_email(self) -> ExtractedIdentifier | None:
        """Get the email with highest extraction confidence."""
        if not self.possible_emails:
            return None
        return max(self.possible_emails, key=lambda x: x.confidence)


class NameComponents(BaseModel):
    """Parsed name components for matching."""

    first_name: str
    last_name: str
    middle_names: list[str] = Field(default_factory=list)
    full_name: str

    @classmethod
    def from_full_name(cls, full_name: str) -> NameComponents:
        """Parse a full name into components (Swedish-aware).
        
        This is a placeholder - actual implementation will be in swedish_name_parser.py
        """
        # Simple placeholder logic - will be replaced by swedish_name_parser
        parts = full_name.strip().split()
        if len(parts) == 0:
            return cls(first_name="", last_name="", full_name=full_name)
        elif len(parts) == 1:
            return cls(first_name=parts[0], last_name="", full_name=full_name)
        elif len(parts) == 2:
            return cls(first_name=parts[0], last_name=parts[1], full_name=full_name)
        else:
            # More than 2 parts
            return cls(
                first_name=parts[0],
                last_name=parts[-1],
                middle_names=parts[1:-1],
                full_name=full_name,
            )


class MatchReason(str, Enum):
    """Reasons for student match."""

    EMAIL_EXACT = "email_exact"
    EMAIL_FUZZY = "email_fuzzy"
    NAME_EXACT = "name_exact"
    NAME_FUZZY = "name_fuzzy"
    NAME_PARTIAL = "name_partial"
    FIRST_LAST_MATCH = "first_last_match"


class StudentInfo(BaseModel):
    """Student information from class roster.
    
    This matches the structure expected from Class Management Service.
    """

    student_id: str = Field(description="Unique identifier for the student")
    first_name: str = Field(description="Student's first name")
    last_name: str = Field(description="Student's last name")
    full_legal_name: str = Field(description="Student's full legal name")
    email: str | None = Field(default=None, description="Student's email address")

    @property
    def display_name(self) -> str:
        """Get a display-friendly name."""
        return f"{self.first_name} {self.last_name}"


class MatchingResult(BaseModel):
    """Result from matching a single extracted identifier against roster."""

    student: StudentInfo
    confidence: float = Field(ge=0.0, le=1.0)
    match_reason: MatchReason
    match_details: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional details about the match (e.g., similarity score)",
    )


class MatchStatus(str, Enum):
    """Overall status of the matching attempt."""

    HIGH_CONFIDENCE = "HIGH_CONFIDENCE"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    NO_MATCH = "NO_MATCH"