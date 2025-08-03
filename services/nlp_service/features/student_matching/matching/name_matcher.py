"""Name-based matching against student roster."""

from __future__ import annotations

from rapidfuzz import fuzz

from ..models import MatchingResult, MatchReason, NameComponents, StudentInfo
from .base_matcher import BaseMatcher
from .simple_name_parser import SimpleNameParser


class NameMatcher(BaseMatcher):
    """Match extracted names against student roster names."""

    def __init__(
        self,
        name_parser: SimpleNameParser | None = None,
        exact_confidence: float = 0.95,
        fuzzy_confidence: float = 0.75,
        partial_confidence: float = 0.85,
        fuzzy_threshold: float = 0.6,
    ):
        """Initialize name matcher with confidence settings.

        Args:
            name_parser: Name parser for parsing extracted names
            exact_confidence: Confidence score for exact name matches
            fuzzy_confidence: Confidence score for fuzzy name matches
            partial_confidence: Confidence score for first+last matches
            fuzzy_threshold: Minimum similarity score for fuzzy matching
        """
        super().__init__("name")
        self.exact_confidence = exact_confidence
        self.fuzzy_confidence = fuzzy_confidence
        self.partial_confidence = partial_confidence
        self.fuzzy_threshold = fuzzy_threshold
        self.name_parser = name_parser or SimpleNameParser()

    async def match(
        self,
        identifier: str,
        roster: list[StudentInfo],
    ) -> list[MatchingResult]:
        """Match a name against the student roster.

        Args:
            identifier: The extracted name to match
            roster: List of students to match against

        Returns:
            List of matching results with confidence scores
        """
        results = []

        # Parse the extracted name
        extracted_name = self.name_parser.parse_name(identifier)

        # Get variations of the extracted name for matching
        extracted_variations = self.name_parser.get_match_variations(extracted_name)

        # Process each student in roster
        for student in roster:
            # Try exact matching first
            exact_match = self._check_exact_match(extracted_name, extracted_variations, student)

            if exact_match:
                results.append(exact_match)
                continue

            # Try partial matching (first + last only)
            partial_match = self._check_partial_match(extracted_name, student)

            if partial_match:
                results.append(partial_match)
                continue

            # Try fuzzy matching
            fuzzy_match = self._check_fuzzy_match(identifier, extracted_variations, student)

            if fuzzy_match:
                results.append(fuzzy_match)

        # Sort by confidence (highest first)
        results.sort(key=lambda r: r.confidence, reverse=True)

        return results

    def _check_exact_match(
        self,
        extracted_name: NameComponents,
        extracted_variations: list[str],
        student: StudentInfo,
    ) -> MatchingResult | None:
        """Check for exact name match."""
        # Check against full legal name
        if self._normalize_compare(student.full_legal_name) in [
            self._normalize_compare(v) for v in extracted_variations
        ]:
            return MatchingResult(
                student=student,
                confidence=self.exact_confidence,
                match_reason=MatchReason.NAME_EXACT,
                match_details={
                    "matched_field": "full_legal_name",
                    "matched_value": student.full_legal_name,
                },
            )

        # Check against display name (first + last)
        student_display = f"{student.first_name} {student.last_name}"
        if self._normalize_compare(student_display) in [
            self._normalize_compare(v) for v in extracted_variations
        ]:
            return MatchingResult(
                student=student,
                confidence=self.exact_confidence,
                match_reason=MatchReason.NAME_EXACT,
                match_details={"matched_field": "display_name", "matched_value": student_display},
            )

        return None

    def _check_partial_match(
        self,
        extracted_name: NameComponents,
        student: StudentInfo,
    ) -> MatchingResult | None:
        """Check for partial match (first + last name only)."""
        if not extracted_name.first_name or not extracted_name.last_name:
            return None

        # Normalize for comparison
        extracted_first = self._normalize_compare(extracted_name.first_name)
        extracted_last = self._normalize_compare(extracted_name.last_name)
        student_first = self._normalize_compare(student.first_name)
        student_last = self._normalize_compare(student.last_name)

        # Check if first and last names match
        if extracted_first == student_first and extracted_last == student_last:
            return MatchingResult(
                student=student,
                confidence=self.partial_confidence,
                match_reason=MatchReason.FIRST_LAST_MATCH,
                match_details={
                    "matched_first": student.first_name,
                    "matched_last": student.last_name,
                    "ignored_middle": bool(extracted_name.middle_names),
                },
            )

        return None

    def _check_fuzzy_match(
        self,
        identifier: str,
        extracted_variations: list[str],
        student: StudentInfo,
    ) -> MatchingResult | None:
        """Check for fuzzy name match using rapidfuzz."""
        # Create list of student name variations
        student_variations = [
            student.full_legal_name,
            f"{student.first_name} {student.last_name}",
            f"{student.last_name}, {student.first_name}",
        ]

        # Find best match across all variations
        best_score = 0.0
        best_match_info = None

        for extracted_var in extracted_variations:
            for student_var in student_variations:
                # Use token sort ratio for better name matching
                score = (
                    fuzz.token_sort_ratio(
                        self._normalize_compare(extracted_var), self._normalize_compare(student_var)
                    )
                    / 100.0
                )

                if score > best_score:
                    best_score = score
                    best_match_info = {
                        "extracted_form": extracted_var,
                        "matched_form": student_var,
                        "similarity_score": score,
                    }

        # Check if best score meets threshold
        if best_score >= self.fuzzy_threshold:
            return MatchingResult(
                student=student,
                confidence=self.fuzzy_confidence * best_score,
                match_reason=MatchReason.NAME_FUZZY,
                match_details=best_match_info,
            )

        return None

    def _normalize_compare(self, text: str) -> str:
        """Normalize text for comparison."""
        # Lowercase, strip, and remove extra spaces
        normalized = " ".join(text.strip().lower().split())

        # Remove common punctuation
        normalized = normalized.replace(",", "").replace(".", "")

        return normalized
