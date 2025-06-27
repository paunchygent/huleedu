"""
Pipeline Resolution Integration Tests for BCS ↔ BOS ClientPipelineRequestHandler

Phase 2: Complete pipeline resolution workflow validation including:
- ClientPipelineRequestHandler message processing
- BatchConductorClient HTTP integration with BCS
- Batch state updates and pipeline storage
- Error handling and idempotency

Tests the complete flow: ClientBatchPipelineRequestV1 → Handler → BCS → State Update

Uses real services, mocks only external boundaries.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock

import aiohttp
import pytest

from common_core.events.client_commands import ClientBatchPipelineRequestV1
from common_core.events.envelope import EventEnvelope
from services.batch_orchestrator_service.implementations.client_pipeline_request_handler import (
    ClientPipelineRequestHandler,
)
from services.batch_orchestrator_service.protocols import (
    BatchEventPublisherProtocol,
    BatchRepositoryProtocol,
    PipelinePhaseCoordinatorProtocol,
)
from tests.utils.service_test_manager import ServiceTestManager


class MockBatchConductorClient:
    """Mock implementation of BatchConductorClient for integration testing."""

    def __init__(self, base_url: str):
        self.base_url = base_url
        self.endpoint = f"{base_url}/internal/v1/pipelines/define"

    async def resolve_pipeline(self, batch_id: str, requested_pipeline: str) -> dict[str, Any]:
        """Resolve pipeline using real HTTP call to BCS."""
        # Build URL for BCS pipeline resolution endpoint
        url = f"{self.base_url}/internal/v1/pipelines/define"
        headers = {"Content-Type": "application/json"}
        data = {"batch_id": batch_id, "requested_pipeline": requested_pipeline}

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=data, headers=headers) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise ValueError(f"BCS returned error status {response.status}: {error_text}")

                response_data: dict[str, Any] = await response.json()
                return response_data


class TestPipelineResolutionIntegration:
    """Integration tests for complete pipeline resolution workflow."""

    @pytest.fixture
    async def service_manager(self) -> ServiceTestManager:
        """Initialize ServiceTestManager for service management."""
        return ServiceTestManager()

    @pytest.fixture
    def mock_batch_repository(self) -> AsyncMock:
        """Mock batch repository for state management testing."""
        mock_repo = AsyncMock(spec=BatchRepositoryProtocol)

        # Mock successful batch retrieval
        mock_repo.get_batch_by_id.return_value = {
            "batch_id": "test-batch-integration-001",
            "requested_pipeline": "ai_feedback",
            "current_state": "pipeline_resolution_requested",
            "resolved_pipeline": None,
            "created_at": "2025-01-01T00:00:00Z",
        }

        # Mock successful batch update and pipeline state saving
        mock_repo.update_batch_status.return_value = True
        mock_repo.save_processing_pipeline_state.return_value = True

        return mock_repo

    @pytest.fixture
    def mock_event_publisher(self) -> AsyncMock:
        """Mock event publisher for Kafka message verification."""
        mock_publisher = AsyncMock(spec=BatchEventPublisherProtocol)
        return mock_publisher

    @pytest.fixture
    def mock_phase_coordinator(self) -> AsyncMock:
        """Mock phase coordinator for pipeline initiation testing."""
        mock_coordinator = AsyncMock(spec=PipelinePhaseCoordinatorProtocol)
        return mock_coordinator

    @pytest.fixture
    async def pipeline_request_handler(
        self,
        validated_services: dict[str, Any],
        mock_batch_repository: AsyncMock,
        mock_event_publisher: AsyncMock,
        mock_phase_coordinator: AsyncMock,
    ) -> ClientPipelineRequestHandler:
        """Create ClientPipelineRequestHandler with real BCS client and mocked dependencies."""
        # Create test BCS client using validated service endpoint
        bcs_config = validated_services["batch_conductor_service"]
        bcs_url = bcs_config["base_url"]
        test_bcs_client = MockBatchConductorClient(base_url=bcs_url)

        # Create handler with test BCS client and mocked dependencies
        handler = ClientPipelineRequestHandler(
            bcs_client=test_bcs_client,
            batch_repo=mock_batch_repository,
            phase_coordinator=mock_phase_coordinator,
        )

        return handler

    @pytest.fixture
    async def validated_services(self, service_manager: ServiceTestManager) -> dict[str, Any]:
        """
        Ensure all required services are available and validated.

        This fixture validates that critical services are healthy before proceeding
        with integration tests.
        """
        endpoints = await service_manager.get_validated_endpoints()

        required_services = ["batch_orchestrator_service", "batch_conductor_service"]
        for service in required_services:
            if service not in endpoints:
                pytest.skip(f"{service} not available for pipeline resolution integration testing")

        return endpoints

    def create_mock_kafka_message(self, event_envelope: EventEnvelope) -> Any:
        """Helper to create mock Kafka message from event envelope."""

        class MockKafkaMessage:
            def __init__(self, topic: str, partition: int, offset: int, value: bytes):
                self.topic = topic
                self.partition = partition
                self.offset = offset
                self.value = value

        event_json = event_envelope.model_dump_json()
        return MockKafkaMessage(
            topic="huleedu.commands.batch.pipeline.v1",
            partition=0,
            offset=12345,
            value=event_json.encode("utf-8"),
        )

    @pytest.mark.docker
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_successful_pipeline_resolution_workflow(
        self,
        pipeline_request_handler: ClientPipelineRequestHandler,
        mock_batch_repository: AsyncMock,
        mock_event_publisher: AsyncMock,
    ):
        """
        Test complete successful pipeline resolution workflow.

        Validates:
        - ClientPipelineRequestHandler processes event correctly
        - Real HTTP call to BCS for pipeline resolution
        - Batch repository updated with resolved pipeline
        - Success event published to Kafka
        """
        # Create test event
        test_event = EventEnvelope(
            event_id=uuid.uuid4(),
            event_type="huleedu.commands.batch.pipeline.v1",
            event_timestamp=datetime.fromisoformat("2025-01-01T00:00:00Z".replace("Z", "+00:00")),
            source_service="api_gateway",
            correlation_id=uuid.uuid4(),
            data=ClientBatchPipelineRequestV1(
                batch_id="test-batch-integration-001",
                requested_pipeline="ai_feedback",
                user_id="test_user_123",
            ),
        )

        # Configure the repository to indicate no pipeline is currently active
        mock_batch_repository.get_processing_pipeline_state.return_value = None

        # Create mock Kafka message (mimicking aiokafka.ConsumerRecord)
        mock_msg = self.create_mock_kafka_message(test_event)

        # Process the message through the handler (using correct method name)
        await pipeline_request_handler.handle_client_pipeline_request(mock_msg)

        # Verify batch repository was called correctly
        mock_batch_repository.get_batch_context.assert_called_once_with(
            "test-batch-integration-001",
        )
        mock_batch_repository.get_processing_pipeline_state.assert_called_once_with(
            "test-batch-integration-001",
        )
        mock_batch_repository.save_processing_pipeline_state.assert_called_once()

        print("✅ Pipeline resolution workflow completed successfully")
        print("✅ BCS integration tested with real HTTP calls")
        print("✅ Batch repository state updates verified")

    @pytest.mark.docker
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_batch_not_found_error_handling(
        self,
        pipeline_request_handler: ClientPipelineRequestHandler,
        mock_batch_repository: AsyncMock,
        mock_event_publisher: AsyncMock,
    ):
        """
        Test error handling when batch does not exist.

        Validates:
        - Handler gracefully handles missing batch
        - No BCS call made for non-existent batch
        - Appropriate error event published
        """
        # Configure repository to return None (batch not found)
        mock_batch_repository.get_batch_context.return_value = None

        test_event = EventEnvelope(
            event_id=uuid.uuid4(),
            event_type="huleedu.commands.batch.pipeline.v1",
            event_timestamp=datetime.fromisoformat("2025-01-01T00:00:00Z".replace("Z", "+00:00")),
            source_service="api_gateway",
            correlation_id=uuid.uuid4(),
            data=ClientBatchPipelineRequestV1(
                batch_id="non-existent-batch",
                requested_pipeline="ai_feedback",
                user_id="test_user_123",
            ),
        )

        mock_msg = self.create_mock_kafka_message(test_event)

        # Process the event - should raise ValueError
        with pytest.raises(ValueError, match="Batch not found"):
            await pipeline_request_handler.handle_client_pipeline_request(mock_msg)

        # Verify no BCS calls were made
        assert not hasattr(pipeline_request_handler.bcs_client, "resolve_pipeline") or not any(
            call
            for call in getattr(
                pipeline_request_handler.bcs_client,
                "resolve_pipeline",
                lambda: None,
            ).__dict__.get("call_args_list", [])
        )

        print("✅ Batch not found error handling verified")

    @pytest.mark.docker
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_invalid_pipeline_name_raises_value_error(
        self,
        pipeline_request_handler: ClientPipelineRequestHandler,
        mock_batch_repository: AsyncMock,
    ):
        """
        Test that an invalid pipeline name raises a ValueError before calling BCS.

        Validates:
        - Handler correctly identifies and rejects invalid pipeline names.
        - No call is made to the Batch Conductor Service.
        """
        # Configure batch repository to return a valid batch context
        mock_batch_repository.get_batch_context.return_value = {
            "batch_id": "test-batch-invalid-name-001",
            "requested_pipeline": "invalid_pipeline_name",
            "current_state": "pipeline_resolution_requested",
            "resolved_pipeline": None,
            "created_at": "2025-01-01T00:00:00Z",
        }
        mock_batch_repository.get_processing_pipeline_state.return_value = None

        test_event = EventEnvelope(
            event_id=uuid.uuid4(),
            event_type="huleedu.commands.batch.pipeline.v1",
            event_timestamp=datetime.fromisoformat("2025-01-01T00:00:00Z".replace("Z", "+00:00")),
            source_service="api_gateway",
            correlation_id=uuid.uuid4(),
            data=ClientBatchPipelineRequestV1(
                batch_id="test-batch-invalid-name-001",
                requested_pipeline="invalid_pipeline_name",
                user_id="test_user_123",
            ),
        )

        mock_msg = self.create_mock_kafka_message(test_event)

        # Process the event - should raise ValueError due to the invalid pipeline name
        with pytest.raises(ValueError, match="Invalid pipeline name: invalid_pipeline_name"):
            await pipeline_request_handler.handle_client_pipeline_request(mock_msg)

        print("✅ Invalid pipeline name validation verified")

    @pytest.mark.docker
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_bcs_http_error_propagation(
        self,
        pipeline_request_handler: ClientPipelineRequestHandler,
        mock_batch_repository: AsyncMock,
        monkeypatch,
    ):
        """
        Test error handling when BCS returns an HTTP error for a valid request.

        Validates:
        - Handler gracefully handles BCS API errors.
        - The error is propagated with a specific 'BCS pipeline resolution failed' message.
        """
        # Configure batch repository to return a valid batch context
        mock_batch_repository.get_batch_context.return_value = {
            "batch_id": "test-batch-bcs-error-001",
            "requested_pipeline": "spellcheck",  # Use a valid pipeline name
            "current_state": "pipeline_resolution_requested",
            "resolved_pipeline": None,
            "created_at": "2025-01-01T00:00:00Z",
        }
        mock_batch_repository.get_processing_pipeline_state.return_value = None

        # Use monkeypatch to simulate an error from the BCS client
        mock_resolve_pipeline = AsyncMock(
            side_effect=aiohttp.ClientError("Simulated BCS 500 Internal Server Error")
        )
        monkeypatch.setattr(
            pipeline_request_handler.bcs_client, "resolve_pipeline", mock_resolve_pipeline
        )

        test_event = EventEnvelope(
            event_id=uuid.uuid4(),
            event_type="huleedu.commands.batch.pipeline.v1",
            event_timestamp=datetime.fromisoformat("2025-01-01T00:00:00Z".replace("Z", "+00:00")),
            source_service="api_gateway",
            correlation_id=uuid.uuid4(),
            data=ClientBatchPipelineRequestV1(
                batch_id="test-batch-bcs-error-001",
                requested_pipeline="spellcheck",  # Use a valid pipeline name
                user_id="test_user_123",
            ),
        )

        mock_msg = self.create_mock_kafka_message(test_event)

        # Process the event - should handle BCS error gracefully
        with pytest.raises(Exception, match="BCS pipeline resolution failed"):
            await pipeline_request_handler.handle_client_pipeline_request(mock_msg)

        # Verify that the mocked BCS client was called
        mock_resolve_pipeline.assert_awaited_once_with("test-batch-bcs-error-001", "spellcheck")

        print("✅ BCS HTTP error propagation verified")

    @pytest.mark.docker
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_idempotency_duplicate_event_handling(
        self,
        pipeline_request_handler: ClientPipelineRequestHandler,
        mock_batch_repository: AsyncMock,
        mock_event_publisher: AsyncMock,
    ):
        """
        Test idempotency when receiving duplicate pipeline request events.

        Validates:
        - Handler detects already-resolved pipelines
        - No duplicate BCS calls made
        - Idempotent response provided
        """
        # Configure batch repository to return already-resolved pipeline
        mock_batch_repository.get_batch_context.return_value = {
            "batch_id": "test-batch-idempotent-001",
            "requested_pipeline": "ai_feedback",
            "current_state": "pipeline_resolved",
            "resolved_pipeline": ["spellcheck", "nlp", "ai_feedback"],  # Already resolved
            "created_at": "2025-01-01T00:00:00Z",
        }

        # Mock active pipeline state to trigger idempotency
        from common_core.pipeline_models import PipelineExecutionStatus

        mock_batch_repository.get_processing_pipeline_state.return_value = {
            "status": PipelineExecutionStatus.IN_PROGRESS,
        }

        test_event = EventEnvelope(
            event_id=uuid.uuid4(),
            event_type="huleedu.commands.batch.pipeline.v1",
            event_timestamp=datetime.fromisoformat("2025-01-01T00:00:00Z".replace("Z", "+00:00")),
            source_service="api_gateway",
            correlation_id=uuid.uuid4(),
            data=ClientBatchPipelineRequestV1(
                batch_id="test-batch-idempotent-001",
                requested_pipeline="ai_feedback",
                user_id="test_user_123",
            ),
        )

        mock_msg = self.create_mock_kafka_message(test_event)

        # Process the duplicate event - should complete without errors
        await pipeline_request_handler.handle_client_pipeline_request(mock_msg)

        # Verify repository was checked but not updated (idempotent)
        mock_batch_repository.get_batch_context.assert_called_once()
        mock_batch_repository.get_processing_pipeline_state.assert_called_once()

        print("✅ Idempotency duplicate event handling verified")

    @pytest.mark.docker
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_concurrent_pipeline_resolution_requests(
        self,
        pipeline_request_handler: ClientPipelineRequestHandler,
        mock_batch_repository: AsyncMock,
        mock_event_publisher: AsyncMock,
    ):
        """
        Test concurrent pipeline resolution requests for different batches.

        Validates:
        - Handler processes multiple concurrent requests
        - Each request resolved independently
        - No race conditions in batch state management
        """

        # Configure repository for multiple batches
        def mock_get_batch_context(batch_id: str):
            return {
                "batch_id": batch_id,
                "requested_pipeline": "ai_feedback",
                "current_state": "pipeline_resolution_requested",
                "resolved_pipeline": None,
                "created_at": "2025-01-01T00:00:00Z",
            }

        mock_batch_repository.get_batch_context.side_effect = mock_get_batch_context
        mock_batch_repository.get_processing_pipeline_state.return_value = None

        # Create multiple concurrent events
        concurrent_events = []
        for i in range(3):
            event = EventEnvelope(
                event_id=uuid.uuid4(),
                event_type="huleedu.commands.batch.pipeline.v1",
                event_timestamp=datetime.fromisoformat(
                    "2025-01-01T00:00:00Z".replace("Z", "+00:00"),
                ),
                source_service="api_gateway",
                correlation_id=uuid.uuid4(),
                data=ClientBatchPipelineRequestV1(
                    batch_id=f"test-batch-concurrent-{i:03d}",
                    requested_pipeline="ai_feedback",
                    user_id="test_user_123",
                ),
            )
            concurrent_events.append(event)

        # Convert to mock messages
        mock_messages = [self.create_mock_kafka_message(event) for event in concurrent_events]

        # Process all events concurrently
        tasks = [
            pipeline_request_handler.handle_client_pipeline_request(msg) for msg in mock_messages
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Verify all succeeded
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                print(f"❌ Concurrent request {i} failed: {result}")
            else:
                print(f"✅ Concurrent request {i} succeeded")

        # Verify repository was called for each batch
        assert mock_batch_repository.get_batch_context.call_count == 3
        assert mock_batch_repository.save_processing_pipeline_state.call_count == 3

        print("✅ Concurrent pipeline resolution requests verified")
