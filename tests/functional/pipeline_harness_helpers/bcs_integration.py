"""BCS integration helper for pipeline tests."""

from typing import Any, Dict, Optional

from huleedu_service_libs.logging_utils import create_service_logger

logger = create_service_logger("test.bcs_integration")


class BCSIntegrationHelper:
    """Helper for BCS integration testing with Kafka-based pipeline triggering.

    This helper provides methods specifically for testing the Batch Orchestrator Service (BOS)
    and Batch Conductor Service (BCS) integration. It focuses on:
    - Triggering pipelines via Kafka events (bypassing API Gateway)
    - Validating BCS received and processed pipeline resolution requests
    - Monitoring workflow events specific to BCS integration
    """

    @staticmethod
    async def trigger_pipeline_via_kafka(
        kafka_manager: Any,  # KafkaTestManager
        batch_id: str,
        pipeline_name: str,
        correlation_id: Optional[str] = None,
    ) -> str:
        """
        Trigger pipeline via ClientBatchPipelineRequestV1 Kafka event.

        This bypasses API Gateway to test BOS ↔ BCS integration directly
        at the event processing level.

        Args:
            kafka_manager: Kafka test manager for publishing events
            batch_id: ID of the batch to process
            pipeline_name: Name of the pipeline to trigger (e.g., "cj_assessment")
            correlation_id: Optional correlation ID for event tracking

        Returns:
            request_correlation_id used for the pipeline request
        """
        from tests.functional.client_pipeline_test_utils import publish_client_pipeline_request

        request_correlation_id = await publish_client_pipeline_request(
            kafka_manager, batch_id, pipeline_name, correlation_id
        )

        logger.info(
            f"📤 Published ClientBatchPipelineRequestV1 for {pipeline_name}",
            extra={
                "batch_id": batch_id,
                "pipeline": pipeline_name,
                "correlation_id": request_correlation_id,
            },
        )

        return request_correlation_id

    @staticmethod
    async def validate_bcs_integration(
        service_manager: Any,  # ServiceTestManager
        batch_id: str,
        pipeline_name: str,
    ) -> Dict[str, Any]:
        """
        Validate that BCS integration occurred correctly.

        This checks:
        - BCS received HTTP requests from BOS
        - Pipeline was successfully resolved
        - Dependency resolution was performed

        Args:
            service_manager: Service test manager for API requests
            batch_id: ID of the batch being processed
            pipeline_name: Name of the pipeline that was requested

        Returns:
            Dictionary containing integration evidence and validation results
        """
        from tests.functional.pipeline_validation_utils import (
            validate_bcs_dependency_resolution,
            validate_bcs_integration_occurred,
        )

        # Get integration evidence from BCS metrics and BOS state
        integration_evidence = await validate_bcs_integration_occurred(
            service_manager, batch_id, pipeline_name
        )

        # Validate dependency resolution logic was applied
        bcs_validated = await validate_bcs_dependency_resolution(integration_evidence)

        return {**integration_evidence, "dependency_resolution_validated": bcs_validated}

    @staticmethod
    async def monitor_workflow_for_bcs_integration(
        consumer: Any,
        batch_id: str,
        request_correlation_id: str,
        timeout_seconds: int = 120,
    ) -> Dict[str, Any]:
        """
        Monitor pipeline resolution workflow for BCS integration events.

        This is a simplified monitoring focused on BCS integration validation,
        checking for key events that prove BOS ↔ BCS communication occurred.

        Args:
            consumer: Kafka consumer instance
            batch_id: ID of the batch being processed
            request_correlation_id: Correlation ID of the pipeline request
            timeout_seconds: Maximum time to wait for workflow completion

        Returns:
            Dictionary containing workflow monitoring results
        """
        from tests.functional.workflow_monitoring_utils import monitor_pipeline_resolution_workflow

        return await monitor_pipeline_resolution_workflow(
            consumer, batch_id, request_correlation_id, timeout_seconds
        )
