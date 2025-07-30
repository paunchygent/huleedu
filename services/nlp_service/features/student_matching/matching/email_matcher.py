"""Email-based matching against student roster."""

from __future__ import annotations

from rapidfuzz import fuzz, process

from ..models import MatchingResult, MatchReason, StudentInfo
from .base_matcher import BaseMatcher


class EmailMatcher(BaseMatcher):
    """Match extracted emails against student roster emails."""

    def __init__(
        self,
        exact_confidence: float = 0.98,
        fuzzy_confidence: float = 0.88,
        fuzzy_threshold: float = 0.9,
    ):
        """Initialize email matcher with confidence settings.

        Args:
            exact_confidence: Confidence score for exact email matches
            fuzzy_confidence: Confidence score for fuzzy email matches
            fuzzy_threshold: Minimum similarity score for fuzzy matching
        """
        super().__init__("email")
        self.exact_confidence = exact_confidence
        self.fuzzy_confidence = fuzzy_confidence
        self.fuzzy_threshold = fuzzy_threshold

    async def match(
        self,
        identifier: str,
        roster: list[StudentInfo],
    ) -> list[MatchingResult]:
        """Match an email against the student roster.

        Args:
            identifier: The extracted email to match
            roster: List of students to match against

        Returns:
            List of matching results with confidence scores
        """
        results = []

        # Normalize the identifier
        normalized_identifier = self.normalize_for_matching(identifier)

        # Build email lookup for exact matching
        email_to_students: dict[str, list[StudentInfo]] = {}
        for student in roster:
            if student.email:
                normalized_email = self.normalize_for_matching(student.email)
                if normalized_email not in email_to_students:
                    email_to_students[normalized_email] = []
                email_to_students[normalized_email].append(student)

        # First, check for exact match
        if normalized_identifier in email_to_students:
            for student in email_to_students[normalized_identifier]:
                results.append(
                    MatchingResult(
                        student=student,
                        confidence=self.exact_confidence,
                        match_reason=MatchReason.EMAIL_EXACT,
                        match_details={"email_matched": identifier, "exact_match": True},
                    )
                )
                self.logger.debug(f"Exact email match: {identifier} -> {student.display_name}")

        # If no exact match, try fuzzy matching
        if not results and email_to_students:
            # Get all unique emails for fuzzy matching
            roster_emails = list(email_to_students.keys())

            # Use rapidfuzz for efficient fuzzy matching
            matches = process.extract(
                normalized_identifier,
                roster_emails,
                scorer=fuzz.ratio,
                limit=3,  # Get top 3 matches
            )

            # Process fuzzy matches
            for matched_email, score, _ in matches:
                # Convert score from 0-100 to 0-1
                similarity = score / 100.0

                if similarity >= self.fuzzy_threshold:
                    for student in email_to_students[matched_email]:
                        results.append(
                            MatchingResult(
                                student=student,
                                confidence=self.fuzzy_confidence * similarity,
                                match_reason=MatchReason.EMAIL_FUZZY,
                                match_details={
                                    "email_matched": identifier,
                                    "actual_email": matched_email,
                                    "similarity_score": similarity,
                                    "edit_distance": self._calculate_edit_distance(
                                        normalized_identifier, matched_email
                                    ),
                                },
                            )
                        )
                        self.logger.debug(
                            f"Fuzzy email match: {identifier} -> {student.display_name} "
                            f"(similarity: {similarity:.2f})"
                        )

        return results

    def normalize_for_matching(self, email: str) -> str:
        """Normalize email for matching."""
        # Basic normalization: lowercase and strip
        email = email.strip().lower()

        # Remove common variations
        # Remove dots from gmail addresses (john.smith@gmail.com = johnsmith@gmail.com)
        if "@gmail.com" in email:
            local_part, domain = email.split("@")
            local_part = local_part.replace(".", "")
            email = f"{local_part}@{domain}"

        return email

    def _calculate_edit_distance(self, str1: str, str2: str) -> int:
        """Calculate Levenshtein edit distance between two strings."""
        # This is a simple implementation - rapidfuzz has optimized versions
        if len(str1) < len(str2):
            return self._calculate_edit_distance(str2, str1)

        if len(str2) == 0:
            return len(str1)

        previous_row = list(range(len(str2) + 1))
        for i, c1 in enumerate(str1):
            current_row = [i + 1]
            for j, c2 in enumerate(str2):
                # j+1 instead of j since previous_row and current_row are one character longer
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row

        return previous_row[-1]
