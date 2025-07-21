"""Default implementation of PipelineResolutionServiceProtocol."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from common_core.events.envelope import EventEnvelope
from common_core.status_enums import OperationStatus
from huleedu_service_libs.error_handling.batch_conductor_factories import (
    raise_pipeline_dependency_resolution_failed,
)
from huleedu_service_libs.error_handling.factories import (
    raise_processing_error,
    raise_resource_not_found,
)
from huleedu_service_libs.error_handling.huleedu_error import HuleEduError
from huleedu_service_libs.logging_utils import create_service_logger
from services.batch_conductor_service.api_models import (
    BCSPipelineDefinitionRequestV1,
    BCSPipelineDefinitionResponseV1,
)
from services.batch_conductor_service.protocols import (
    DlqProducerProtocol,
    PipelineGeneratorProtocol,
    PipelineResolutionServiceProtocol,
    PipelineRulesProtocol,
)

if TYPE_CHECKING:
    pass

logger = create_service_logger("bcs.pipeline_resolution_service")


class DefaultPipelineResolutionService(PipelineResolutionServiceProtocol):
    """Default implementation of pipeline resolution service with DLQ and metrics support."""

    def __init__(
        self,
        pipeline_rules: PipelineRulesProtocol,
        pipeline_generator: PipelineGeneratorProtocol,
        dlq_producer: DlqProducerProtocol,
    ):
        self.pipeline_rules = pipeline_rules
        self.pipeline_generator = pipeline_generator
        self.dlq_producer = dlq_producer
        self._metrics: dict[str, Any] | None = None

    def set_metrics(self, metrics: dict[str, Any]) -> None:
        """Set Prometheus metrics for tracking pipeline resolutions."""
        self._metrics = metrics

    async def resolve_pipeline(
        self, batch_id: str, requested_pipeline: str, correlation_id: UUID
    ) -> list[str]:
        """
        Resolve pipeline for batch processing with error handling and metrics.

        Args:
            batch_id: Batch identifier for pipeline resolution
            requested_pipeline: Name of the requested pipeline
            correlation_id: Correlation ID for request tracing

        Returns:
            List of resolved pipeline steps in execution order
            
        Raises:
            HuleEduError: If pipeline resolution fails (unknown pipeline, dependency issues, etc.)
        """
        try:
            # Validate that the requested pipeline exists
            pipeline_steps = self.pipeline_generator.get_pipeline_steps(requested_pipeline)
            if not pipeline_steps:
                logger.warning(
                    f"Pipeline resolution failed: Unknown pipeline '{requested_pipeline}'",
                    extra={
                        "batch_id": batch_id,
                        "requested_pipeline": requested_pipeline,
                        "error": "unknown_pipeline",
                        "correlation_id": str(correlation_id),
                    },
                )

                await self._track_failure_metrics(requested_pipeline, "unknown_pipeline")
                raise_resource_not_found(
                    service="batch_conductor_service",
                    operation="resolve_pipeline",
                    resource_type="pipeline",
                    resource_id=requested_pipeline,
                    correlation_id=correlation_id,
                    batch_id=batch_id,
                )

            # Resolve pipeline dependencies using event-driven state
            try:
                resolved_pipeline = await self.pipeline_rules.resolve_pipeline_dependencies(
                    requested_pipeline, batch_id
                )

                logger.info(
                    f"Pipeline resolved successfully: {requested_pipeline}",
                    extra={
                        "batch_id": batch_id,
                        "requested_pipeline": requested_pipeline,
                        "resolved_steps": len(resolved_pipeline),
                        "final_pipeline": resolved_pipeline,
                        "correlation_id": str(correlation_id),
                    },
                )

                await self._track_success_metrics(requested_pipeline)
                return resolved_pipeline

            except Exception as resolution_error:
                logger.error(
                    f"Pipeline dependency resolution failed: {resolution_error}",
                    extra={
                        "batch_id": batch_id,
                        "requested_pipeline": requested_pipeline,
                        "error": str(resolution_error),
                        "correlation_id": str(correlation_id),
                    },
                    exc_info=True,
                )

                # Publish failure to DLQ for analysis
                await self._publish_resolution_failure_to_dlq(
                    batch_id,
                    requested_pipeline,
                    "dependency_resolution_failed",
                    str(resolution_error),
                )

                await self._track_failure_metrics(
                    requested_pipeline, "dependency_resolution_failed"
                )
                raise_pipeline_dependency_resolution_failed(
                    service="batch_conductor_service",
                    operation="resolve_pipeline_dependencies",
                    message=f"Pipeline dependency resolution failed: {resolution_error}",
                    correlation_id=correlation_id,
                    batch_id=batch_id,
                    requested_pipeline=requested_pipeline,
                    resolution_stage="dependency_analysis",
                    dependency_error=str(resolution_error),
                )

        except Exception as e:
            logger.error(
                f"Critical pipeline resolution failure: Unexpected error: {e}",
                extra={
                    "batch_id": batch_id,
                    "requested_pipeline": requested_pipeline,
                    "error": str(e),
                    "correlation_id": str(correlation_id),
                },
                exc_info=True,
            )

            # Publish critical failure to DLQ
            await self._publish_resolution_failure_to_dlq(
                batch_id, requested_pipeline, "critical_resolution_failure", str(e)
            )

            await self._track_failure_metrics(requested_pipeline, "critical_failure")
            raise_processing_error(
                service="batch_conductor_service",
                operation="resolve_pipeline",
                message=f"Unexpected pipeline resolution error: {e}",
                correlation_id=correlation_id,
                batch_id=batch_id,
                requested_pipeline=requested_pipeline,
            )

    async def resolve_pipeline_request(
        self, request: BCSPipelineDefinitionRequestV1
    ) -> BCSPipelineDefinitionResponseV1:
        """Resolve a complete pipeline request from BOS with duration tracking."""
        start_time = time.time()
        correlation_id = uuid4()

        try:
            resolved_pipeline = await self.resolve_pipeline(
                request.batch_id, request.requested_pipeline, correlation_id
            )

            # Track duration for successful resolution
            duration = time.time() - start_time
            await self._track_duration_metrics(request.requested_pipeline, duration)

            # Create successful response
            return BCSPipelineDefinitionResponseV1(
                batch_id=request.batch_id,
                final_pipeline=resolved_pipeline,
                analysis_summary=(
                    f"Resolved '{request.requested_pipeline}' pipeline to "
                    f"{len(resolved_pipeline)} steps"
                ),
            )
        except HuleEduError as e:
            # Track duration for failed resolution
            duration = time.time() - start_time
            await self._track_duration_metrics(request.requested_pipeline, duration)

            # Return error response for API consumers with structured error information
            return BCSPipelineDefinitionResponseV1(
                batch_id=request.batch_id,
                final_pipeline=[],
                analysis_summary=f"Pipeline resolution failed: {e.error_detail.message}",
            )
        except Exception:
            # Track duration even for unexpected errors
            duration = time.time() - start_time
            await self._track_duration_metrics(request.requested_pipeline, duration)

            # Re-raise the exception
            raise

    async def _publish_resolution_failure_to_dlq(
        self, batch_id: str, requested_pipeline: str, failure_reason: str, error_details: str
    ) -> None:
        """Publish pipeline resolution failure to DLQ for analysis."""
        try:
            # Create a synthetic event envelope for the failed resolution request
            synthetic_envelope = EventEnvelope[Any](
                event_id=uuid4(),
                event_type="huleedu.batch.pipeline.resolution.failed.v1",
                event_timestamp=datetime.now(UTC),
                source_service="batch_conductor_service",
                correlation_id=uuid4(),
                data={
                    "batch_id": batch_id,
                    "requested_pipeline": requested_pipeline,
                    "failure_reason": failure_reason,
                    "error_details": error_details,
                },
            )

            success = await self.dlq_producer.publish_to_dlq(
                base_topic="huleedu.pipelines.resolution",
                failed_event_envelope=synthetic_envelope,
                dlq_reason=failure_reason,
                additional_metadata={
                    "batch_id": batch_id,
                    "requested_pipeline": requested_pipeline,
                    "error_details": error_details,
                },
            )

            if not success:
                logger.error(
                    "Failed to publish pipeline resolution failure to DLQ",
                    extra={
                        "batch_id": batch_id,
                        "requested_pipeline": requested_pipeline,
                        "failure_reason": failure_reason,
                    },
                )

        except Exception as e:
            logger.error(
                f"Error publishing to DLQ: {e}",
                extra={
                    "batch_id": batch_id,
                    "requested_pipeline": requested_pipeline,
                    "failure_reason": failure_reason,
                },
                exc_info=True,
            )

    async def _track_success_metrics(self, requested_pipeline: str) -> None:
        """Track successful pipeline resolution in Prometheus metrics."""
        if self._metrics and "pipeline_resolutions_total" in self._metrics:
            counter = self._metrics["pipeline_resolutions_total"]
            # Safely handle the counter metric
            if hasattr(counter, "labels") and hasattr(counter, "inc"):
                counter.labels(
                    requested_pipeline=requested_pipeline, outcome=OperationStatus.SUCCESS.value
                ).inc()

    async def _track_failure_metrics(self, requested_pipeline: str, failure_reason: str) -> None:
        """Track failed pipeline resolution in Prometheus metrics."""
        if self._metrics and "pipeline_resolutions_total" in self._metrics:
            counter = self._metrics["pipeline_resolutions_total"]
            # Safely handle the counter metric
            if hasattr(counter, "labels") and hasattr(counter, "inc"):
                counter.labels(requested_pipeline=requested_pipeline, outcome=failure_reason).inc()

    async def _track_duration_metrics(self, requested_pipeline: str, duration: float) -> None:
        """Track pipeline resolution duration in Prometheus metrics."""
        if self._metrics and "pipeline_resolution_duration_seconds" in self._metrics:
            histogram = self._metrics["pipeline_resolution_duration_seconds"]
            # Safely handle the histogram metric
            if hasattr(histogram, "labels") and hasattr(histogram, "observe"):
                histogram.labels(requested_pipeline=requested_pipeline).observe(duration)

    async def resolve_optimal_pipeline(
        self,
        batch_id: str,
        requested_pipeline: str,
        correlation_id: UUID,
        additional_metadata: dict | None = None,
    ) -> dict[str, Any]:
        """Resolve optimal pipeline configuration for a batch."""
        try:
            resolved_pipeline = await self.resolve_pipeline(
                batch_id, requested_pipeline, correlation_id
            )

            result = {
                "success": True,
                "batch_id": batch_id,
                "requested_pipeline": requested_pipeline,
                "resolved_pipeline": resolved_pipeline,
                "error_message": "",
            }

            if additional_metadata:
                result["additional_metadata"] = additional_metadata

            return result

        except HuleEduError as e:
            result = {
                "success": False,
                "batch_id": batch_id,
                "requested_pipeline": requested_pipeline,
                "resolved_pipeline": [],
                "error_message": e.error_detail.message,
            }

            if additional_metadata:
                result["additional_metadata"] = additional_metadata

            return result
