"""Extractor for exam.net format essays with 4-paragraph header structure."""

from __future__ import annotations

import re
from typing import Any

from ..models import ExtractedIdentifier, ExtractionResult
from .base_extractor import BaseExtractor


class ExamnetExtractor(BaseExtractor):
    """Extract student information from exam.net format essays.

    Expected format:
    Paragraph 1: Student Name [possibly with numbers]
    Paragraph 2: [Header info]
    Paragraph 3: [Header info - may contain email]
    Paragraph 4: [Header info - may contain word count]
    Paragraph 5+: Essay content
    """

    def __init__(self) -> None:
        """Initialize the exam.net extractor."""
        super().__init__("examnet")
        # Email pattern
        self.email_pattern = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")
        # Number cleanup pattern (e.g., "John Smith 123" -> "John Smith")
        self.number_suffix_pattern = re.compile(r"\s+\d+$")

    async def extract(
        self,
        text: str,
        filename: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ExtractionResult:
        """Extract from exam.net format."""
        result = ExtractionResult()

        # Split into paragraphs
        paragraphs = [p.strip() for p in text.strip().split("\n\n") if p.strip()]

        if not paragraphs:
            self.logger.warning("No paragraphs found in text")
            return result

        # Extract from first paragraph (expected to be student name)
        if paragraphs:
            first_para = paragraphs[0].strip()

            # Look for a name-like pattern in the first paragraph
            if self._looks_like_name(first_para):
                # Clean up any trailing numbers
                cleaned_name = self.number_suffix_pattern.sub("", first_para).strip()

                if cleaned_name and len(cleaned_name) > 2:
                    result.possible_names.append(
                        ExtractedIdentifier(
                            value=cleaned_name,
                            source_strategy=self.name,
                            confidence=0.8,  # High confidence for first paragraph
                            location_hint="paragraph_1",
                        )
                    )
                    self.logger.debug(f"Extracted name from paragraph 1: {cleaned_name}")

        # Look for emails in paragraphs 2-4
        for i, para in enumerate(paragraphs[1:4], start=2):
            if i > len(paragraphs):
                break

            emails = self.email_pattern.findall(para)
            for email in emails:
                result.possible_emails.append(
                    ExtractedIdentifier(
                        value=email.lower(),
                        source_strategy=self.name,
                        confidence=0.9,  # High confidence for emails
                        location_hint=f"paragraph_{i}",
                    )
                )
                self.logger.debug(f"Extracted email from paragraph {i}: {email}")

        # Set metadata
        result.metadata["format_detected"] = "examnet"
        result.metadata["paragraph_count"] = len(paragraphs)

        return result

    def _looks_like_name(self, text: str) -> bool:
        """Check if text looks like a name (not a sentence or title)."""
        # Skip if too long (likely a sentence)
        if len(text) > 50:
            return False

        # Skip if it contains common non-name indicators
        non_name_indicators = [
            ":",
            "?",
            "!",
            ".",
            ",",
            ";",
            "(",
            ")",
            "[",
            "]",
            "essay",
            "assignment",
            "task",
            "question",
            "answer",
            "uppsats",
            "uppgift",
            "fråga",
            "svar",  # Swedish
        ]

        text_lower = text.lower()
        for indicator in non_name_indicators:
            if indicator in text_lower:
                return False

        # Should have at least one space (first and last name)
        # But not too many (not a sentence)
        space_count = text.count(" ")
        if space_count < 1 or space_count > 4:
            return False

        # Each word should start with a capital letter (with some exceptions)
        words = text.split()
        name_words = 0

        for word in words:
            # Skip short words like "av", "von", "de"
            if len(word) <= 3 and word.lower() in ["av", "von", "de", "van", "der", "la", "el"]:
                continue
            # Skip numbers
            if word.isdigit():
                continue
            # Check if word looks like a name (starts with capital)
            if word and word[0].isupper():
                name_words += 1

        # At least 2 name-like words
        return name_words >= 2
