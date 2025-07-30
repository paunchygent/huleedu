"""Confidence calculation and match status determination."""

from __future__ import annotations

from huleedu_service_libs.logging_utils import create_service_logger

from ..models import MatchingResult, MatchStatus

logger = create_service_logger("nlp_service.matching.confidence")


class ConfidenceCalculator:
    """Calculate final confidence scores and determine match status."""

    def __init__(
        self,
        high_confidence_threshold: float = 0.85,
        review_threshold: float = 0.60,
    ):
        """Initialize with confidence thresholds.

        Args:
            high_confidence_threshold: Min score for HIGH_CONFIDENCE status
            review_threshold: Min score for NEEDS_REVIEW status
        """
        self.high_confidence_threshold = high_confidence_threshold
        self.review_threshold = review_threshold

    def calculate_combined_confidence(
        self,
        matching_results: list[MatchingResult],
    ) -> float:
        """Calculate combined confidence from multiple match results.

        Takes the highest confidence score, with slight boost if multiple
        independent matches point to the same student.
        """
        if not matching_results:
            return 0.0

        # Group by student
        student_matches: dict[str, list[MatchingResult]] = {}
        for result in matching_results:
            student_id = result.student.student_id
            if student_id not in student_matches:
                student_matches[student_id] = []
            student_matches[student_id].append(result)

        # Calculate confidence for each student
        student_confidences = {}
        for student_id, matches in student_matches.items():
            # Base confidence is the highest single match
            base_confidence = max(m.confidence for m in matches)

            # Boost if we have multiple different types of matches
            match_types = set(m.match_reason for m in matches)

            # Email + Name match is very strong
            if any("email" in str(t).lower() for t in match_types) and any(
                "name" in str(t).lower() for t in match_types
            ):
                # Boost by 5% but cap at 0.99
                boosted = min(base_confidence * 1.05, 0.99)
            elif len(match_types) > 1:
                # Multiple match types, smaller boost
                boosted = min(base_confidence * 1.02, 0.98)
            else:
                boosted = base_confidence

            student_confidences[student_id] = boosted

            logger.debug(
                f"Student {student_id} confidence: {base_confidence:.2f} -> {boosted:.2f}",
                extra={
                    "student_id": student_id,
                    "match_count": len(matches),
                    "match_types": list(match_types),
                },
            )

        # Return the highest confidence across all students
        return max(student_confidences.values()) if student_confidences else 0.0

    def determine_match_status(
        self,
        matching_results: list[MatchingResult],
    ) -> MatchStatus:
        """Determine overall match status based on results.

        Args:
            matching_results: All matching results

        Returns:
            MatchStatus indicating confidence level
        """
        if not matching_results:
            return MatchStatus.NO_MATCH

        # Calculate combined confidence
        combined_confidence = self.calculate_combined_confidence(matching_results)

        # Determine status based on thresholds
        if combined_confidence >= self.high_confidence_threshold:
            return MatchStatus.HIGH_CONFIDENCE
        elif combined_confidence >= self.review_threshold:
            return MatchStatus.NEEDS_REVIEW
        else:
            return MatchStatus.NO_MATCH

    def filter_top_matches(
        self,
        matching_results: list[MatchingResult],
        max_results: int = 3,
    ) -> list[MatchingResult]:
        """Filter and return only the top matching results.

        Args:
            matching_results: All matching results
            max_results: Maximum number of results to return

        Returns:
            Top matches sorted by confidence
        """
        if not matching_results:
            return []

        # Sort by confidence (highest first)
        sorted_results = sorted(matching_results, key=lambda r: r.confidence, reverse=True)

        # If we have a very high confidence match, only return matches
        # for that same student (to avoid confusion)
        if sorted_results[0].confidence >= self.high_confidence_threshold:
            top_student_id = sorted_results[0].student.student_id
            same_student_results = [
                r for r in sorted_results if r.student.student_id == top_student_id
            ]
            return same_student_results[:max_results]

        # Otherwise, return top matches (might be different students)
        return sorted_results[:max_results]
