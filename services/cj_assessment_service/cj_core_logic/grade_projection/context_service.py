from __future__ import annotations

from uuid import UUID

from services.cj_assessment_service.cj_core_logic.context_builder import (
    AssessmentContext,
    ContextBuilder,
)
from services.cj_assessment_service.protocols import (
    AnchorRepositoryProtocol,
    AssessmentInstructionRepositoryProtocol,
    ContentClientProtocol,
    SessionProviderProtocol,
)


class ProjectionContextService:
    """Facade around ContextBuilder to hydrate assessment context."""

    def __init__(
        self,
        session_provider: SessionProviderProtocol,
        instruction_repository: AssessmentInstructionRepositoryProtocol,
        anchor_repository: AnchorRepositoryProtocol,
        context_builder: ContextBuilder | None = None,
    ) -> None:
        self._session_provider = session_provider
        self._instruction_repository = instruction_repository
        self._anchor_repository = anchor_repository
        self._context_builder = context_builder or ContextBuilder(
            session_provider=session_provider,
            instruction_repository=instruction_repository,
            anchor_repository=anchor_repository,
            min_anchors_required=0,
        )

    async def build_context(
        self,
        *,
        assignment_id: str | None,
        course_code: str,
        content_client: ContentClientProtocol,
        correlation_id: UUID,
    ) -> AssessmentContext:
        return await self._context_builder.build(
            assignment_id=assignment_id,
            course_code=course_code,
            content_client=content_client,
            correlation_id=correlation_id,
        )
