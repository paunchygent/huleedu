"""Default implementation of PipelineResolutionServiceProtocol."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from common_core.events.envelope import EventEnvelope
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
        self, batch_id: str, requested_pipeline: str
    ) -> tuple[bool, list[str], str]:
        """
        Resolve pipeline for batch processing with error handling and metrics.

        Returns:
            (success: bool, resolved_pipeline: list[str], error_message: str)
        """
        try:
            # Validate that the requested pipeline exists
            pipeline_steps = self.pipeline_generator.get_pipeline_steps(requested_pipeline)
            if not pipeline_steps:
                error_msg = f"Unknown pipeline: '{requested_pipeline}'"
                logger.warning(
                    f"Pipeline resolution failed: {error_msg}",
                    extra={
                        "batch_id": batch_id,
                        "requested_pipeline": requested_pipeline,
                        "error": "unknown_pipeline",
                    },
                )

                await self._track_failure_metrics(requested_pipeline, "unknown_pipeline")
                return False, [], error_msg

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
                    },
                )

                await self._track_success_metrics(requested_pipeline)
                return True, resolved_pipeline, ""

            except Exception as resolution_error:
                error_msg = f"Pipeline dependency resolution failed: {resolution_error}"
                logger.error(
                    f"Pipeline resolution error: {error_msg}",
                    extra={
                        "batch_id": batch_id,
                        "requested_pipeline": requested_pipeline,
                        "error": str(resolution_error),
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
                return False, [], error_msg

        except Exception as e:
            error_msg = f"Unexpected pipeline resolution error: {e}"
            logger.error(
                f"Critical pipeline resolution failure: {error_msg}",
                extra={
                    "batch_id": batch_id,
                    "requested_pipeline": requested_pipeline,
                    "error": str(e),
                },
                exc_info=True,
            )

            # Publish critical failure to DLQ
            await self._publish_resolution_failure_to_dlq(
                batch_id, requested_pipeline, "critical_resolution_failure", str(e)
            )

            await self._track_failure_metrics(requested_pipeline, "critical_failure")
            return False, [], error_msg

    async def resolve_pipeline_request(
        self, request: BCSPipelineDefinitionRequestV1
    ) -> BCSPipelineDefinitionResponseV1:
        """Resolve a complete pipeline request from BOS with duration tracking."""
        start_time = time.time()

        try:
            success, resolved_pipeline, error_message = await self.resolve_pipeline(
                request.batch_id, request.requested_pipeline
            )

            # Track duration regardless of success/failure
            duration = time.time() - start_time
            await self._track_duration_metrics(request.requested_pipeline, duration)

            if not success:
                # Return error response for API consumers
                return BCSPipelineDefinitionResponseV1(
                    batch_id=request.batch_id,
                    final_pipeline=[],
                    analysis_summary=f"Pipeline resolution failed: {error_message}",
                )

            # Create successful response
            return BCSPipelineDefinitionResponseV1(
                batch_id=request.batch_id,
                final_pipeline=resolved_pipeline,
                analysis_summary=(
                    f"Resolved '{request.requested_pipeline}' pipeline to "
                    f"{len(resolved_pipeline)} steps"
                ),
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
                correlation_id=None,
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
                counter.labels(requested_pipeline=requested_pipeline, outcome="success").inc()

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
        additional_metadata: dict | None = None,
    ) -> dict[str, Any]:
        """Resolve optimal pipeline configuration for a batch."""
        success, resolved_pipeline, error_message = await self.resolve_pipeline(
            batch_id, requested_pipeline
        )

        result = {
            "success": success,
            "batch_id": batch_id,
            "requested_pipeline": requested_pipeline,
            "resolved_pipeline": resolved_pipeline,
            "error_message": error_message,
        }

        if additional_metadata:
            result["additional_metadata"] = additional_metadata

        return result
