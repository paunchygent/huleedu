"""Email-based extractor that looks for names near email addresses."""

from __future__ import annotations

import re
from typing import Any

from ..models import ExtractedIdentifier, ExtractionResult
from .base_extractor import BaseExtractor


class EmailAnchorExtractor(BaseExtractor):
    """Extract student information by finding emails and looking for names nearby.

    Strategy:
    1. Find all email addresses in the text
    2. Look for names in proximity to the emails
    3. Extract names from the email prefix if no nearby names found
    """

    def __init__(self, context_window: int = 50):
        """Initialize with configurable context window.

        Args:
            context_window: Characters to search around email for names
        """
        super().__init__("email_anchor")
        self.context_window = context_window

        # Email pattern
        self.email_pattern = re.compile(r"\b([A-Za-z0-9._%+-]+)@([A-Za-z0-9.-]+\.[A-Z|a-z]{2,})\b")

        # Name-like pattern (capitalized words)
        self.name_pattern = re.compile(r"\b([A-Z][a-z]+(?:[-\s][A-Z][a-z]+)*)\b")

    async def extract(
        self,
        text: str,
        filename: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ExtractionResult:
        """Extract using email anchor strategy."""
        result = ExtractionResult()

        # Find all emails with their positions
        for match in self.email_pattern.finditer(text):
            email_full = match.group(0)
            email_prefix = match.group(1)
            match.group(2)
            email_start = match.start()
            email_end = match.end()

            # Add the email to results
            result.possible_emails.append(
                ExtractedIdentifier(
                    value=email_full.lower(),
                    source_strategy=self.name,
                    confidence=0.95,  # Very high confidence for emails
                    location_hint=f"position_{email_start}",
                )
            )

            # Look for names in context window around email
            context_start = max(0, email_start - self.context_window)
            context_end = min(len(text), email_end + self.context_window)
            context_text = text[context_start:context_end]

            # Find potential names in context
            names_found = []
            for name_match in self.name_pattern.finditer(context_text):
                potential_name = name_match.group(0)
                if self._is_valid_name(potential_name):
                    names_found.append(potential_name)

            # If names found nearby, add them
            if names_found:
                # Prefer names that appear multiple times or are closer to email
                for name in names_found:
                    result.possible_names.append(
                        ExtractedIdentifier(
                            value=name,
                            source_strategy=self.name,
                            confidence=0.7,  # Good confidence for proximity
                            location_hint=f"near_email_{email_full}",
                        )
                    )
                    self.logger.debug(f"Found name '{name}' near email '{email_full}'")
            else:
                # Try to extract name from email prefix
                extracted_name = self._extract_name_from_email(email_prefix)
                if extracted_name:
                    result.possible_names.append(
                        ExtractedIdentifier(
                            value=extracted_name,
                            source_strategy=self.name,
                            confidence=0.6,  # Lower confidence for email-derived
                            location_hint=f"from_email_{email_full}",
                        )
                    )
                    self.logger.debug(
                        f"Extracted name '{extracted_name}' from email '{email_full}'"
                    )

        # Set metadata
        result.metadata["emails_found"] = len(result.possible_emails)
        result.metadata["context_window"] = self.context_window

        return result

    def _is_valid_name(self, text: str) -> bool:
        """Check if text is a valid name."""
        # Skip single words (need at least first and last)
        if " " not in text and "-" not in text:
            return False

        # Skip if too short or too long
        if len(text) < 5 or len(text) > 50:
            return False

        # Skip common non-name words
        non_names = {
            "The",
            "This",
            "That",
            "These",
            "Those",
            "From",
            "Subject",
            "Date",
            "Time",
            "Email",
            "Name",
            "Student",
            "Author",
            "Written",
            "Assignment",
            "Essay",
            "Task",
            "Homework",
        }

        # Check each word
        words = text.replace("-", " ").split()
        for word in words:
            if word in non_names:
                return False

        return True

    def _extract_name_from_email(self, email_prefix: str) -> str | None:
        """Try to extract a name from email prefix.

        Common patterns:
        - firstname.lastname
        - firstname_lastname
        - firstnamelastname (harder)
        - firstname.m.lastname
        """
        # Remove numbers
        prefix_clean = re.sub(r"\d+", "", email_prefix)

        # Split on common separators
        parts = re.split(r"[._-]", prefix_clean)
        parts = [p for p in parts if p and len(p) > 1]

        if not parts:
            return None

        # Filter out common non-name parts
        non_name_parts = {"info", "contact", "admin", "student", "elev", "mail", "email"}
        parts = [p for p in parts if p.lower() not in non_name_parts]

        if not parts:
            return None

        # Capitalize and join
        if len(parts) >= 2:
            # Take first and last (skip middle initials if present)
            first = parts[0].capitalize()
            last = parts[-1].capitalize()

            # Handle Swedish names with special characters
            first = self._swedish_capitalize(first)
            last = self._swedish_capitalize(last)

            return f"{first} {last}"

        return None

    def _swedish_capitalize(self, name: str) -> str:
        """Properly capitalize Swedish names."""
        # Handle compound names
        if "-" in name:
            parts = name.split("-")
            return "-".join(p.capitalize() for p in parts)

        # Regular capitalization preserving Swedish characters
        return name.capitalize()
