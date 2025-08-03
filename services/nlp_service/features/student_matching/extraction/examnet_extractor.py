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

        # Extract from first paragraph - check first line specifically
        if paragraphs:
            first_para = paragraphs[0].strip()

            # Split the first paragraph into lines
            first_para_lines = first_para.split("\n")
            if first_para_lines:
                first_line = first_para_lines[0].strip()

                # Check if first line contains a date pattern (indicating name + date format)
                date_pattern = re.compile(r"\d{4}-\d{2}-\d{2}")
                if date_pattern.search(first_line):
                    # Extract the part before the date as the name
                    name_part = date_pattern.split(first_line)[0].strip()
                    if name_part and self._looks_like_name(name_part):
                        result.possible_names.append(
                            ExtractedIdentifier(
                                value=name_part,
                                source_strategy=self.name,
                                confidence=0.85,  # High confidence for name + date pattern
                                location_hint="line_1",
                            )
                        )
                        self.logger.debug(f"Extracted name from first line: {name_part}")
                # If no date, check if the entire first line looks like a name
                elif self._looks_like_name(first_line):
                    # Clean up any trailing numbers
                    cleaned_name = self.number_suffix_pattern.sub("", first_line).strip()

                    if cleaned_name and len(cleaned_name) > 2:
                        result.possible_names.append(
                            ExtractedIdentifier(
                                value=cleaned_name,
                                source_strategy=self.name,
                                confidence=0.8,  # High confidence for first line
                                location_hint="line_1",
                            )
                        )
                        self.logger.debug(f"Extracted name from first line: {cleaned_name}")

            # Also try the original logic for backward compatibility
            if not result.possible_names and self._looks_like_name(first_para):
                # Clean up any trailing numbers
                cleaned_name = self.number_suffix_pattern.sub("", first_para).strip()

                if cleaned_name and len(cleaned_name) > 2:
                    result.possible_names.append(
                        ExtractedIdentifier(
                            value=cleaned_name,
                            source_strategy=self.name,
                            confidence=0.7,  # Lower confidence for full paragraph
                            location_hint="paragraph_1",
                        )
                    )
                    self.logger.debug(f"Extracted name from paragraph 1: {cleaned_name}")

        # Also look for emails in the first paragraph (sometimes in header lines)
        if paragraphs:
            first_para_lines = paragraphs[0].split("\n")
            for line_idx, line in enumerate(first_para_lines[:5]):  # Check first 5 lines
                emails = self.email_pattern.findall(line)
                for email in emails:
                    result.possible_emails.append(
                        ExtractedIdentifier(
                            value=email.lower(),
                            source_strategy=self.name,
                            confidence=0.9,  # High confidence for emails
                            location_hint=f"line_{line_idx + 1}",
                        )
                    )
                    self.logger.debug(f"Extracted email from line {line_idx + 1}: {email}")

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

        # Check space count - require at least one space (first and last name)
        space_count = text.count(" ")
        if space_count == 0:  # Single word, not a full name
            return False
        if space_count > 4:  # Too many spaces, probably a sentence
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

        # At least 1 name-like word
        return name_words >= 1
