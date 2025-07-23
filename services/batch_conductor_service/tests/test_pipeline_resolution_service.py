"""
Robust tests for Pipeline Resolution Service Implementation.

Tests focus on business behavior and realistic scenarios rather than implementation details.
Only mocks external protocol boundaries, never internal business logic.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from common_core.events.envelope import EventEnvelope
from services.batch_conductor_service.api_models import (
    BCSPipelineDefinitionRequestV1,
    BCSPipelineDefinitionResponseV1,
)
from services.batch_conductor_service.implementations.pipeline_resolution_service_impl import (
    DefaultPipelineResolutionService,
)
from services.batch_conductor_service.protocols import (
    DlqProducerProtocol,
    PipelineGeneratorProtocol,
    PipelineRulesProtocol,
)


class TestPipelineResolutionServiceBehavior:
    """Test business behavior of pipeline resolution service with realistic scenarios."""

    @pytest.fixture
    def mock_pipeline_generator(self) -> AsyncMock:
        """Mock pipeline generator that returns realistic pipeline configurations."""
        mock = AsyncMock(spec=PipelineGeneratorProtocol)

        # Set up realistic pipeline configurations
        pipeline_configs = {
            "spellcheck": ["spellcheck"],
            "ai_feedback": ["spellcheck", "ai_feedback"],
            "cj_assessment": ["spellcheck", "cj_assessment"],
            "full_analysis": ["spellcheck", "ai_feedback", "cj_assessment", "report_generation"],
        }

        def get_pipeline_steps(pipeline_name: str) -> list[str] | None:
            return pipeline_configs.get(pipeline_name)

        mock.get_pipeline_steps.side_effect = get_pipeline_steps
        return mock

    @pytest.fixture
    def mock_pipeline_rules(self) -> AsyncMock:
        """Mock pipeline rules that provides realistic dependency resolution."""
        mock = AsyncMock(spec=PipelineRulesProtocol)

        async def resolve_dependencies(
            requested_pipeline: str, batch_id: str | None = None
        ) -> list[str]:
            # Simulate realistic dependency resolution logic
            if requested_pipeline == "spellcheck":
                return ["spellcheck"]
            elif requested_pipeline == "ai_feedback":
                # AI feedback requires spellcheck to be complete first
                return ["spellcheck", "ai_feedback"]
            elif requested_pipeline == "cj_assessment":
                # CJ assessment also requires spellcheck
                return ["spellcheck", "cj_assessment"]
            elif requested_pipeline == "full_analysis":
                # Full analysis requires all components
                return ["spellcheck", "ai_feedback", "cj_assessment", "report_generation"]
            else:
                # Unknown pipeline should raise an appropriate error
                raise ValueError(f"Unknown pipeline dependencies for: {requested_pipeline}")

        mock.resolve_pipeline_dependencies.side_effect = resolve_dependencies
        return mock

    @pytest.fixture
    def mock_dlq_producer(self) -> AsyncMock:
        """Mock DLQ producer that tracks publications."""
        mock = AsyncMock(spec=DlqProducerProtocol)
        mock.publish_to_dlq.return_value = True
        return mock

    @pytest.fixture
    def service(
        self,
        mock_pipeline_generator: AsyncMock,
        mock_pipeline_rules: AsyncMock,
        mock_dlq_producer: AsyncMock,
    ) -> DefaultPipelineResolutionService:
        """Create service instance with realistic external dependencies."""
        return DefaultPipelineResolutionService(
            pipeline_rules=mock_pipeline_rules,
            pipeline_generator=mock_pipeline_generator,
            dlq_producer=mock_dlq_producer,
        )

    # Test Category 1: Successful Pipeline Resolution

    async def test_simple_spellcheck_pipeline_resolution(
        self, service: DefaultPipelineResolutionService
    ) -> None:
        """Test resolution of simple spellcheck pipeline."""
        # Arrange
        request = BCSPipelineDefinitionRequestV1(
            batch_id="batch_essays_001", requested_pipeline="spellcheck"
        )

        # Act
        response = await service.resolve_pipeline_request(request)

        # Assert
        assert isinstance(response, BCSPipelineDefinitionResponseV1)
        assert response.batch_id == "batch_essays_001"
        assert response.final_pipeline == ["spellcheck"]
        assert response.analysis_summary is not None
        assert "1 steps" in response.analysis_summary
        assert "spellcheck" in response.analysis_summary

    async def test_ai_feedback_pipeline_with_dependencies(
        self, service: DefaultPipelineResolutionService
    ) -> None:
        """Test resolution of AI feedback pipeline including required spellcheck dependency."""
        # Arrange
        request = BCSPipelineDefinitionRequestV1(
            batch_id="batch_essays_002", requested_pipeline="ai_feedback"
        )

        # Act
        response = await service.resolve_pipeline_request(request)

        # Assert
        assert response.batch_id == "batch_essays_002"
        assert response.final_pipeline == ["spellcheck", "ai_feedback"]
        assert response.analysis_summary is not None
        assert "2 steps" in response.analysis_summary
        assert "ai_feedback" in response.analysis_summary

    async def test_cj_assessment_pipeline_resolution(
        self, service: DefaultPipelineResolutionService
    ) -> None:
        """Test resolution of comparative judgment assessment pipeline."""
        # Arrange
        request = BCSPipelineDefinitionRequestV1(
            batch_id="batch_cj_study_001", requested_pipeline="cj_assessment"
        )

        # Act
        response = await service.resolve_pipeline_request(request)

        # Assert
        assert response.batch_id == "batch_cj_study_001"
        assert response.final_pipeline == ["spellcheck", "cj_assessment"]
        assert len(response.final_pipeline) == 2
        assert response.final_pipeline[0] == "spellcheck"  # Dependency comes first
        assert response.final_pipeline[1] == "cj_assessment"

    async def test_complex_full_analysis_pipeline(
        self, service: DefaultPipelineResolutionService
    ) -> None:
        """Test resolution of complex pipeline with multiple dependencies."""
        # Arrange
        request = BCSPipelineDefinitionRequestV1(
            batch_id="batch_comprehensive_001", requested_pipeline="full_analysis"
        )

        # Act
        response = await service.resolve_pipeline_request(request)

        # Assert
        assert response.batch_id == "batch_comprehensive_001"
        expected_pipeline = ["spellcheck", "ai_feedback", "cj_assessment", "report_generation"]
        assert response.final_pipeline == expected_pipeline
        assert response.analysis_summary is not None
        assert "4 steps" in response.analysis_summary

    # Test Category 2: Pipeline Validation Failures

    async def test_unknown_pipeline_request(
        self, service: DefaultPipelineResolutionService
    ) -> None:
        """Test graceful handling of unknown pipeline requests."""
        # Arrange
        request = BCSPipelineDefinitionRequestV1(
            batch_id="batch_unknown_001", requested_pipeline="nonexistent_pipeline"
        )

        # Act
        response = await service.resolve_pipeline_request(request)

        # Assert - Should return error response, not raise exception
        assert response.batch_id == "batch_unknown_001"
        assert response.final_pipeline == []
        assert response.analysis_summary is not None
        assert "Pipeline resolution failed" in response.analysis_summary
        assert (
            "pipeline with ID" in response.analysis_summary
            and "not found" in response.analysis_summary
        )
        assert "nonexistent_pipeline" in response.analysis_summary

    async def test_multiple_unknown_pipeline_requests(
        self, service: DefaultPipelineResolutionService
    ) -> None:
        """Test that multiple unknown pipeline requests are handled consistently."""
        # Arrange
        unknown_pipelines = ["invalid_pipe_1", "invalid_pipe_2", "nonexistent_analysis"]

        for pipeline_name in unknown_pipelines:
            request = BCSPipelineDefinitionRequestV1(
                batch_id=f"batch_{pipeline_name}", requested_pipeline=pipeline_name
            )

            # Act
            response = await service.resolve_pipeline_request(request)

            # Assert - Each should fail gracefully with same pattern
            assert response.final_pipeline == []
            assert response.analysis_summary is not None
            assert "Pipeline resolution failed" in response.analysis_summary
            assert pipeline_name in response.analysis_summary

    # Test Category 3: Dependency Resolution Failures

    async def test_dependency_resolution_with_circular_dependency(
        self, service: DefaultPipelineResolutionService, mock_pipeline_rules: AsyncMock
    ) -> None:
        """Test handling of circular dependency detection during resolution."""

        # Arrange - Override dependency resolution to simulate circular dependency
        async def circular_dependency_error(
            requested_pipeline: str, batch_id: str | None = None
        ) -> list[str]:
            raise ValueError(
                "Circular dependency detected: ai_feedback -> spellcheck -> ai_feedback"
            )

        mock_pipeline_rules.resolve_pipeline_dependencies.side_effect = circular_dependency_error

        request = BCSPipelineDefinitionRequestV1(
            batch_id="batch_circular_001", requested_pipeline="ai_feedback"
        )

        # Act
        response = await service.resolve_pipeline_request(request)

        # Assert - Should handle dependency error gracefully
        assert response.batch_id == "batch_circular_001"
        assert response.final_pipeline == []
        assert response.analysis_summary is not None
        assert "Pipeline resolution failed" in response.analysis_summary
        assert "dependency resolution failed" in response.analysis_summary

    async def test_dependency_resolution_with_missing_prerequisites(
        self, service: DefaultPipelineResolutionService, mock_pipeline_rules: AsyncMock
    ) -> None:
        """Test handling of missing prerequisite detection."""

        # Arrange - Override to simulate missing prerequisites
        async def missing_prerequisites_error(
            requested_pipeline: str, batch_id: str | None = None
        ) -> list[str]:
            raise ValueError("Missing prerequisite: required service 'nlp_parser' not available")

        mock_pipeline_rules.resolve_pipeline_dependencies.side_effect = missing_prerequisites_error

        request = BCSPipelineDefinitionRequestV1(
            batch_id="batch_missing_prereq_001", requested_pipeline="ai_feedback"
        )

        # Act
        response = await service.resolve_pipeline_request(request)

        # Assert
        assert response.final_pipeline == []
        assert response.analysis_summary is not None
        assert "Pipeline resolution failed" in response.analysis_summary

    # Test Category 4: External Service Failures

    async def test_pipeline_generator_service_failure(
        self, service: DefaultPipelineResolutionService, mock_pipeline_generator: AsyncMock
    ) -> None:
        """Test handling of pipeline generator service failures."""
        # Arrange - Simulate external service failure
        mock_pipeline_generator.get_pipeline_steps.side_effect = RuntimeError(
            "Pipeline configuration service unavailable"
        )

        request = BCSPipelineDefinitionRequestV1(
            batch_id="batch_generator_fail_001", requested_pipeline="ai_feedback"
        )

        # Act
        response = await service.resolve_pipeline_request(request)

        # Assert - Should handle external failure gracefully
        assert response.batch_id == "batch_generator_fail_001"
        assert response.final_pipeline == []
        assert response.analysis_summary is not None
        assert "Pipeline resolution failed" in response.analysis_summary

    async def test_dlq_service_failure_does_not_block_operation(
        self,
        service: DefaultPipelineResolutionService,
        mock_dlq_producer: AsyncMock,
        mock_pipeline_rules: AsyncMock,
    ) -> None:
        """Test that DLQ service failures do not prevent error reporting."""

        # Arrange - Set up dependency failure that should trigger DLQ, but DLQ fails
        async def dependency_error(
            requested_pipeline: str, batch_id: str | None = None
        ) -> list[str]:
            raise ValueError("Simulated dependency resolution failure")

        mock_pipeline_rules.resolve_pipeline_dependencies.side_effect = dependency_error
        mock_dlq_producer.publish_to_dlq.side_effect = Exception("DLQ service unavailable")

        request = BCSPipelineDefinitionRequestV1(
            batch_id="batch_dlq_fail_001", requested_pipeline="ai_feedback"
        )

        # Act - Should complete despite DLQ failure
        response = await service.resolve_pipeline_request(request)

        # Assert - Primary operation should still complete with error response
        assert response.batch_id == "batch_dlq_fail_001"
        assert response.final_pipeline == []
        assert response.analysis_summary is not None
        assert "Pipeline resolution failed" in response.analysis_summary
        assert "dependency resolution failed" in response.analysis_summary

    # Test Category 5: DLQ Integration Behavior

    async def test_dlq_publication_on_dependency_resolution_failure(
        self,
        service: DefaultPipelineResolutionService,
        mock_dlq_producer: AsyncMock,
        mock_pipeline_rules: AsyncMock,
    ) -> None:
        """Test that dependency resolution failures are properly published to DLQ."""
        # Arrange
        failure_message = "Complex dependency validation failed"

        async def dependency_failure(
            requested_pipeline: str, batch_id: str | None = None
        ) -> list[str]:
            raise ValueError(failure_message)

        mock_pipeline_rules.resolve_pipeline_dependencies.side_effect = dependency_failure

        request = BCSPipelineDefinitionRequestV1(
            batch_id="batch_dlq_test_001", requested_pipeline="cj_assessment"
        )

        # Act
        await service.resolve_pipeline_request(request)

        # Assert - Verify DLQ publication occurred
        # (may be called multiple times due to comprehensive error handling)
        assert mock_dlq_producer.publish_to_dlq.call_count >= 1
        call_kwargs = mock_dlq_producer.publish_to_dlq.call_args.kwargs

        # Check DLQ call structure
        assert call_kwargs["base_topic"] == "huleedu.pipelines.resolution"
        # With comprehensive error handling, the final DLQ call will be for
        # critical_resolution_failure
        assert call_kwargs["dlq_reason"] == "critical_resolution_failure"

        # Check event envelope
        envelope = call_kwargs["failed_event_envelope"]
        assert isinstance(envelope, EventEnvelope)
        assert envelope.source_service == "batch_conductor_service"
        assert envelope.data["batch_id"] == "batch_dlq_test_001"
        assert envelope.data["requested_pipeline"] == "cj_assessment"
        assert failure_message in envelope.data["error_details"]

        # Check additional metadata
        metadata = call_kwargs["additional_metadata"]
        assert metadata["batch_id"] == "batch_dlq_test_001"
        assert metadata["requested_pipeline"] == "cj_assessment"

    async def test_dlq_publication_for_unknown_pipeline(
        self, service: DefaultPipelineResolutionService, mock_dlq_producer: AsyncMock
    ) -> None:
        """Test that unknown pipeline requests trigger DLQ publication for error tracking."""
        # Arrange
        request = BCSPipelineDefinitionRequestV1(
            batch_id="batch_no_dlq_001", requested_pipeline="completely_unknown_pipeline"
        )

        # Act
        await service.resolve_pipeline_request(request)

        # Assert - DLQ publication should occur for unknown pipeline errors
        mock_dlq_producer.publish_to_dlq.assert_called_once()

        # Verify DLQ call includes proper error tracking
        call_args = mock_dlq_producer.publish_to_dlq.call_args
        assert call_args[1]["base_topic"] == "huleedu.pipelines.resolution"
        assert call_args[1]["dlq_reason"] == "critical_resolution_failure"

    # Test Category 6: Business Logic Integration

    async def test_resolve_optimal_pipeline_interface(
        self, service: DefaultPipelineResolutionService
    ) -> None:
        """Test the resolve_optimal_pipeline interface for BOS integration."""
        # Arrange
        from uuid import uuid4

        batch_id = "batch_optimal_001"
        requested_pipeline = "ai_feedback"
        correlation_id = uuid4()
        additional_metadata = {"user_preference": "detailed_analysis", "priority": "high"}

        # Act
        result = await service.resolve_optimal_pipeline(
            batch_id, requested_pipeline, correlation_id, additional_metadata
        )

        # Assert - Check complete result structure
        assert result["success"] is True
        assert result["batch_id"] == batch_id
        assert result["requested_pipeline"] == requested_pipeline
        assert result["resolved_pipeline"] == ["spellcheck", "ai_feedback"]
        assert result["error_message"] == ""
        assert result["additional_metadata"] == additional_metadata

    async def test_resolve_optimal_pipeline_failure_case(
        self, service: DefaultPipelineResolutionService
    ) -> None:
        """Test resolve_optimal_pipeline failure handling."""
        # Arrange
        from uuid import uuid4

        batch_id = "batch_optimal_fail_001"
        requested_pipeline = "invalid_pipeline_name"
        correlation_id = uuid4()

        # Act
        result = await service.resolve_optimal_pipeline(
            batch_id, requested_pipeline, correlation_id
        )

        # Assert
        assert result["success"] is False
        assert result["batch_id"] == batch_id
        assert result["requested_pipeline"] == requested_pipeline
        assert result["resolved_pipeline"] == []
        assert (
            "pipeline with ID" in result["error_message"] and "not found" in result["error_message"]
        )
        assert "additional_metadata" not in result

    # Test Category 7: Edge Cases and Robustness

    async def test_concurrent_pipeline_resolution_requests(
        self, service: DefaultPipelineResolutionService
    ) -> None:
        """Test that service handles concurrent requests independently."""
        # Arrange - Multiple different requests
        requests = [
            BCSPipelineDefinitionRequestV1(
                batch_id="batch_concurrent_1", requested_pipeline="spellcheck"
            ),
            BCSPipelineDefinitionRequestV1(
                batch_id="batch_concurrent_2", requested_pipeline="ai_feedback"
            ),
            BCSPipelineDefinitionRequestV1(
                batch_id="batch_concurrent_3", requested_pipeline="cj_assessment"
            ),
        ]

        # Act - Process requests concurrently (simulate concurrent usage)
        import asyncio

        responses = await asyncio.gather(
            *[service.resolve_pipeline_request(req) for req in requests]
        )

        # Assert - Each response should be correct and independent
        assert len(responses) == 3

        # Check each response independently
        assert responses[0].batch_id == "batch_concurrent_1"
        assert responses[0].final_pipeline == ["spellcheck"]

        assert responses[1].batch_id == "batch_concurrent_2"
        assert responses[1].final_pipeline == ["spellcheck", "ai_feedback"]

        assert responses[2].batch_id == "batch_concurrent_3"
        assert responses[2].final_pipeline == ["spellcheck", "cj_assessment"]

    async def test_batch_specific_pipeline_resolution(
        self, service: DefaultPipelineResolutionService, mock_pipeline_rules: AsyncMock
    ) -> None:
        """Test that pipeline resolution can be batch-specific."""

        # Arrange - Set up batch-aware dependency resolution
        async def batch_aware_dependencies(
            requested_pipeline: str, batch_id: str | None = None
        ) -> list[str]:
            if batch_id == "batch_already_spellchecked":
                # This batch already completed spellcheck, so skip it
                if requested_pipeline == "ai_feedback":
                    return ["ai_feedback"]  # Skip spellcheck dependency

            # Default behavior for other batches
            if requested_pipeline == "ai_feedback":
                return ["spellcheck", "ai_feedback"]
            return [requested_pipeline]

        mock_pipeline_rules.resolve_pipeline_dependencies.side_effect = batch_aware_dependencies

        # Act - Test both scenarios
        normal_request = BCSPipelineDefinitionRequestV1(
            batch_id="batch_normal_001", requested_pipeline="ai_feedback"
        )
        optimized_request = BCSPipelineDefinitionRequestV1(
            batch_id="batch_already_spellchecked", requested_pipeline="ai_feedback"
        )

        normal_response = await service.resolve_pipeline_request(normal_request)
        optimized_response = await service.resolve_pipeline_request(optimized_request)

        # Assert - Different resolutions based on batch state
        assert normal_response.final_pipeline == ["spellcheck", "ai_feedback"]
        assert optimized_response.final_pipeline == ["ai_feedback"]  # Optimized
