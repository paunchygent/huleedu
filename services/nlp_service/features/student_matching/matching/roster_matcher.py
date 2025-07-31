"""Main orchestrator for matching extracted information against class roster."""

from __future__ import annotations

from common_core.events.nlp_events import StudentMatchSuggestion
from huleedu_service_libs.logging_utils import create_service_logger

from ..models import ExtractionResult, MatchStatus, StudentInfo
from .confidence_calculator import ConfidenceCalculator
from .email_matcher import EmailMatcher
from .name_matcher import NameMatcher

logger = create_service_logger("nlp_service.matching.roster_matcher")


class RosterMatcher:
    """Main orchestrator for student roster matching."""

    def __init__(
        self,
        name_matcher: NameMatcher | None = None,
        email_matcher: EmailMatcher | None = None,
        confidence_calculator: ConfidenceCalculator | None = None,
    ):
        """Initialize with matching components.

        Args:
            name_matcher: Name matching strategy
            email_matcher: Email matching strategy
            confidence_calculator: Confidence calculation logic
        """
        self.name_matcher = name_matcher or NameMatcher()
        self.email_matcher = email_matcher or EmailMatcher()
        self.confidence_calculator = confidence_calculator or ConfidenceCalculator()

    async def match_student(
        self,
        extracted: ExtractionResult,
        roster: list[StudentInfo],
    ) -> tuple[list[StudentMatchSuggestion], MatchStatus]:
        """Match extracted information against roster.

        Args:
            extracted: Extracted identifiers from essay
            roster: Class roster to match against

        Returns:
            Tuple of (suggestions list, overall match status)
        """
        if not roster:
            logger.warning("Empty roster provided for matching")
            return [], MatchStatus.NO_MATCH

        if extracted.is_empty():
            logger.info("No identifiers extracted for matching")
            return [], MatchStatus.NO_MATCH

        all_matches = []

        # Email matching (highest priority)
        for email_identifier in extracted.possible_emails:
            email_matches = await self.email_matcher.match(email_identifier.value, roster)
            all_matches.extend(email_matches)

            if email_matches:
                logger.debug(
                    f"Email matching found {len(email_matches)} matches",
                    extra={"email": email_identifier.value},
                )

        # Name matching
        for name_identifier in extracted.possible_names:
            name_matches = await self.name_matcher.match(name_identifier.value, roster)
            all_matches.extend(name_matches)

            if name_matches:
                logger.debug(
                    f"Name matching found {len(name_matches)} matches",
                    extra={"name": name_identifier.value},
                )

        # Deduplicate matches
        deduped_matches = self._deduplicate_matches(all_matches)

        # Calculate match status
        match_status = self.confidence_calculator.determine_match_status(deduped_matches)

        # Filter to top matches
        top_matches = self.confidence_calculator.filter_top_matches(deduped_matches)

        # Convert to output format
        suggestions = self._convert_to_suggestions(top_matches)

        logger.info(
            "Matching completed",
            extra={
                "total_matches": len(deduped_matches),
                "suggestions_returned": len(suggestions),
                "match_status": match_status.value,
                "highest_confidence": max((m.confidence for m in top_matches), default=0.0),
            },
        )

        return suggestions, match_status

    def _deduplicate_matches(self, matches: list) -> list:
        """Deduplicate matches, keeping highest confidence per student."""
        if not matches:
            return []

        # Group by student ID
        student_matches = {}
        for match in matches:
            student_id = match.student.student_id

            if student_id not in student_matches:
                student_matches[student_id] = match
            else:
                # Keep the higher confidence match
                if match.confidence > student_matches[student_id].confidence:
                    student_matches[student_id] = match
                elif match.confidence == student_matches[student_id].confidence:
                    # If equal confidence, prefer email matches
                    if "email" in match.match_reason.value.lower():
                        student_matches[student_id] = match

        return list(student_matches.values())

    def _convert_to_suggestions(self, matches: list) -> list[StudentMatchSuggestion]:
        """Convert internal matching results to API format."""
        suggestions = []

        for match in matches:
            suggestion = StudentMatchSuggestion(
                student_id=match.student.student_id,
                student_name=match.student.display_name,
                student_email=getattr(match.student, 'email', None),
                confidence_score=match.confidence,
                match_reasons=[match.match_reason.value],
                extraction_metadata={},
            )
            suggestions.append(suggestion)

        return suggestions
