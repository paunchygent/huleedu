"""Default implementation of PipelineResolutionServiceProtocol."""

from __future__ import annotations

from services.batch_conductor_service.api_models import (
    BCSPipelineDefinitionRequestV1,
    BCSPipelineDefinitionResponseV1,
)
from services.batch_conductor_service.protocols import (
    DlqProducerProtocol,
    PipelineGeneratorProtocol,
    PipelineRulesProtocol,
)


class DefaultPipelineResolutionService:
    """Default implementation of pipeline resolution service."""

    def __init__(
        self,
        pipeline_rules: PipelineRulesProtocol,
        pipeline_generator: PipelineGeneratorProtocol,
        dlq_producer: DlqProducerProtocol,
    ):
        self.pipeline_rules = pipeline_rules
        self.pipeline_generator = pipeline_generator
        self.dlq_producer = dlq_producer

    async def resolve_pipeline_request(
        self, request: BCSPipelineDefinitionRequestV1
    ) -> BCSPipelineDefinitionResponseV1:
        """Resolve a complete pipeline request from BOS."""

        # Resolve pipeline dependencies using event-driven state
        resolved_pipeline = await self.pipeline_rules.resolve_pipeline_dependencies(
            request.requested_pipeline, request.batch_id
        )

        # Create response
        return BCSPipelineDefinitionResponseV1(
            batch_id=request.batch_id,
            final_pipeline=resolved_pipeline,
            analysis_summary=f"Resolved '{request.requested_pipeline}' pipeline",
        )
