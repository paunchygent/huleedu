"""Default implementation of StudentMatcherProtocol for NLP Service."""

from __future__ import annotations

from uuid import UUID

from common_core.events.nlp_events import StudentMatchSuggestion
from huleedu_service_libs.logging_utils import create_service_logger

from services.nlp_service.features.student_matching.extraction.extraction_pipeline import (
    ExtractionPipeline,
)
from services.nlp_service.features.student_matching.matching.roster_matcher import RosterMatcher
from services.nlp_service.features.student_matching.models import StudentInfo
from services.nlp_service.protocols import StudentMatcherProtocol

logger = create_service_logger("nlp_service.student_matcher_impl")


class DefaultStudentMatcher(StudentMatcherProtocol):
    """Default implementation orchestrating extraction and matching pipelines."""

    def __init__(
        self,
        extraction_pipeline: ExtractionPipeline,
        roster_matcher: RosterMatcher,
    ) -> None:
        """Initialize student matcher.

        Args:
            extraction_pipeline: Pipeline for extracting identifiers from text
            roster_matcher: Matcher for comparing extracted info against roster
        """
        self.extraction_pipeline = extraction_pipeline
        self.roster_matcher = roster_matcher

    async def find_matches(
        self,
        essay_text: str,
        roster: list[dict],
        correlation_id: UUID,
    ) -> list[StudentMatchSuggestion]:
        """Find potential student matches in essay text.

        Args:
            essay_text: The essay text to analyze
            roster: List of student dictionaries from class roster
            correlation_id: Request correlation ID for tracing

        Returns:
            List of student match suggestions ordered by confidence
        """
        logger.debug(
            "Starting student matching process for essay",
            extra={"correlation_id": str(correlation_id), "roster_size": len(roster)},
        )

        # Convert roster dicts to StudentInfo models
        student_infos = []
        for student_dict in roster:
            try:
                student_info = StudentInfo(**student_dict)
                student_infos.append(student_info)
            except Exception as e:
                logger.warning(
                    f"Failed to parse student record: {e}",
                    extra={
                        "correlation_id": str(correlation_id),
                        "student_data": str(student_dict)[:200],
                    },
                )
                continue

        if not student_infos:
            logger.warning(
                "No valid students in roster after parsing",
                extra={"correlation_id": str(correlation_id)},
            )
            return []

        # Extract identifiers from essay text
        logger.debug(
            "Running extraction pipeline on essay text",
            extra={"correlation_id": str(correlation_id)},
        )

        extraction_result = await self.extraction_pipeline.extract(
            text=essay_text,
            filename=None,  # Could be passed if available
            metadata={"correlation_id": str(correlation_id)},
        )

        logger.info(
            f"Extraction complete: found {len(extraction_result.possible_names)} names, "
            f"{len(extraction_result.possible_emails)} emails",
            extra={
                "correlation_id": str(correlation_id),
                "name_count": len(extraction_result.possible_names),
                "email_count": len(extraction_result.possible_emails),
            },
        )

        # If no identifiers extracted, return empty list
        if extraction_result.is_empty():
            logger.info(
                "No identifiers extracted from essay text",
                extra={"correlation_id": str(correlation_id)},
            )
            return []

        # Match extracted info against roster
        logger.debug(
            "Running roster matching on extracted identifiers",
            extra={"correlation_id": str(correlation_id)},
        )

        match_suggestions, match_status = await self.roster_matcher.match_student(
            extracted=extraction_result,
            roster=student_infos,
        )

        # Convert internal suggestions to API model
        api_suggestions = []
        for suggestion in match_suggestions:
            api_suggestion = StudentMatchSuggestion(
                student_id=suggestion.student_id,
                student_name=suggestion.student_name,
                student_email=getattr(suggestion, 'student_email', None),
                confidence_score=suggestion.confidence_score,
                match_reasons=[suggestion.match_reasons.value] if hasattr(suggestion, 'match_reasons') else [],
                extraction_metadata={},
            )
            api_suggestions.append(api_suggestion)

        logger.info(
            f"Matching complete: found {len(api_suggestions)} potential matches",
            extra={
                "correlation_id": str(correlation_id),
                "match_count": len(api_suggestions),
                "top_confidence": api_suggestions[0].confidence_score if api_suggestions else 0.0,
            },
        )

        return api_suggestions
