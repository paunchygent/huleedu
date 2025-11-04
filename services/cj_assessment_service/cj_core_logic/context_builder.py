"""Context builder for assessment instructions and anchors.

This module resolves assessment context for grade projections, including
instructions and anchor essays from either assignment-specific or course-level
configurations.
"""

from __future__ import annotations

from typing import NamedTuple
from uuid import UUID

from huleedu_service_libs.error_handling import (
    HuleEduError,
)
from huleedu_service_libs.logging_utils import create_service_logger
from sqlalchemy.ext.asyncio import AsyncSession

from services.cj_assessment_service.models_db import (
    AnchorEssayReference,
)
from services.cj_assessment_service.protocols import (
    ContentClientProtocol,
)

logger = create_service_logger("cj_assessment.context_builder")


class AssessmentContext(NamedTuple):
    """Resolved context for assessment."""

    assessment_instructions: str
    anchor_essay_refs: list[AnchorEssayReference]
    anchor_contents: dict[str, str]  # content_id -> text
    context_source: str  # "assignment" or "course"
    grade_scale: str


class InsufficientAnchorsError(HuleEduError):
    """Raised when too few anchors for reliable assessment."""

    error_code = "INSUFFICIENT_ANCHORS"


class ContextBuilder:
    """Resolves assessment context from assignment or course.

    Fetches assessment instructions and anchor essays, with fallback
    from assignment-specific to course-level context when needed.
    """

    def __init__(
        self,
        min_anchors_required: int = 0,  # Default to 0 to allow graceful degradation
    ):
        self.logger = logger
        self.min_anchors = min_anchors_required

    async def build(
        self,
        session: AsyncSession,
        assignment_id: str | None,
        course_code: str,
        content_client: ContentClientProtocol,
        correlation_id: UUID,
    ) -> AssessmentContext:
        """Build assessment context - assignment or course fallback.

        Args:
            session: Database session for queries
            assignment_id: Optional assignment ID for predefined context
            course_code: Course code for fallback context
            content_client: Client for fetching anchor essay content
            correlation_id: Request correlation ID for tracing

        Returns:
            AssessmentContext with instructions and anchor essays

        Raises:
            ValidationError: If no instructions found
            InsufficientAnchorsError: If too few anchors (when min_anchors > 0)
        """
        self.logger.info(
            "Building assessment context",
            extra={
                "correlation_id": str(correlation_id),
                "assignment_id": assignment_id,
                "course_code": course_code,
            },
        )

        # Import here to avoid circular dependency
        from services.cj_assessment_service.implementations.db_access_impl import (
            get_anchor_essay_references,
            get_assessment_instruction,
        )

        instructions = None
        anchor_refs = []
        context_source = "none"
        grade_scale = "swedish_8_anchor"

        # Try assignment-specific context first
        if assignment_id:
            instructions = await get_assessment_instruction(
                session, assignment_id=assignment_id, course_id=None
            )
            if instructions:
                grade_scale = instructions.grade_scale
                anchor_refs = await get_anchor_essay_references(
                    session,
                    assignment_id=assignment_id,
                    grade_scale=grade_scale,
                )
                context_source = "assignment"
                self.logger.info(
                    f"Found assignment-specific context with {len(anchor_refs)} anchors",
                    extra={
                        "correlation_id": str(correlation_id),
                        "assignment_id": assignment_id,
                        "anchor_count": len(anchor_refs),
                    },
                )

        # Fall back to course-level context if needed
        if not instructions:
            instructions = await get_assessment_instruction(
                session, assignment_id=None, course_id=course_code
            )
            if instructions:
                grade_scale = instructions.grade_scale
                # For course-level, we don't have course-specific anchors yet
                # This could be extended in the future
                anchor_refs = []
                context_source = "course"
                self.logger.info(
                    "Using course-level context (no anchors)",
                    extra={
                        "correlation_id": str(correlation_id),
                        "course_code": course_code,
                    },
                )

        # If still no instructions, use a default
        if not instructions:
            self.logger.warning(
                "No instructions found, using default",
                extra={
                    "correlation_id": str(correlation_id),
                    "assignment_id": assignment_id,
                    "course_code": course_code,
                },
            )
            # Create a default instruction object
            from services.cj_assessment_service.models_db import AssessmentInstruction

            instructions = AssessmentInstruction(
                instructions_text=(
                    "Compare the essays based on overall quality, clarity, "
                    "argumentation, and adherence to academic standards."
                ),
                grade_scale=grade_scale,
            )
            context_source = "default"

        # Check anchor count if required
        if self.min_anchors > 0 and len(anchor_refs) < self.min_anchors:
            self.logger.warning(
                f"Insufficient anchors: {len(anchor_refs)} < {self.min_anchors}",
                extra={
                    "correlation_id": str(correlation_id),
                    "anchor_count": len(anchor_refs),
                    "min_required": self.min_anchors,
                },
            )
            # Don't raise error - allow graceful degradation

        # Fetch anchor content from Content Service
        anchor_contents = {}
        for ref in anchor_refs:
            try:
                content = await content_client.fetch_content(ref.text_storage_id, correlation_id)
                anchor_contents[ref.text_storage_id] = content
                self.logger.debug(
                    f"Fetched anchor content for grade {ref.grade}",
                    extra={
                        "correlation_id": str(correlation_id),
                        "content_id": ref.text_storage_id,
                        "grade": ref.grade,
                    },
                )
            except Exception as e:
                self.logger.error(
                    f"Failed to fetch anchor content: {e}",
                    extra={
                        "correlation_id": str(correlation_id),
                        "content_id": ref.text_storage_id,
                        "error": str(e),
                    },
                )
                # Continue without this anchor

        return AssessmentContext(
            assessment_instructions=instructions.instructions_text,
            anchor_essay_refs=anchor_refs,
            anchor_contents=anchor_contents,
            context_source=context_source,
            grade_scale=grade_scale,
        )
