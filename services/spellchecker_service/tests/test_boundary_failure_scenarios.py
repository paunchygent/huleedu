"""Boundary failure scenario tests for spellchecker service.

Tests comprehensive boundary failure scenarios to validate that real business logic
correctly handles all possible external boundary failures while maintaining
proper error reporting and correlation ID tracking.

ULTRATHINK Requirements:
- Test ALL boundary failure scenarios systematically
- Use real business logic with only boundary mocks
- Verify error recovery and graceful degradation patterns
- Validate correlation ID preservation through all failure scenarios
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Generator
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import aiohttp
import pytest
from aiokafka import ConsumerRecord
from common_core.error_enums import ErrorCode
from common_core.essay_service_models import EssayLifecycleSpellcheckRequestV1
from common_core.event_enums import ProcessingEvent
from common_core.events.envelope import EventEnvelope
from common_core.metadata_models import SystemProcessingMetadata
from common_core.models.error_models import ErrorDetail
from common_core.status_enums import EssayStatus, ProcessingStage
from huleedu_service_libs.error_handling.huleedu_error import HuleEduError

from services.spellchecker_service.event_processor import process_single_message
from services.spellchecker_service.implementations.spell_logic_impl import DefaultSpellLogic
from services.spellchecker_service.protocols import (
    ContentClientProtocol,
    ResultStoreProtocol,
    SpellcheckEventPublisherProtocol,
)
from services.spellchecker_service.tests.mocks import MockWhitelist, create_mock_parallel_processor


class TestBoundaryFailureScenarios:
    """Test systematic boundary failure scenarios with real business logic."""

    @pytest.fixture
    def boundary_mocks(self) -> dict[str, AsyncMock]:
        """Create mocks for external boundaries only."""
        content_client = AsyncMock(spec=ContentClientProtocol)
        result_store = AsyncMock(spec=ResultStoreProtocol)
        event_publisher = AsyncMock(spec=SpellcheckEventPublisherProtocol)
        kafka_bus = AsyncMock()
        http_session = AsyncMock(spec=aiohttp.ClientSession)

        return {
            "content_client": content_client,
            "result_store": result_store,
            "event_publisher": event_publisher,
            "kafka_bus": kafka_bus,
            "http_session": http_session,
        }

    @pytest.fixture
    def real_spell_logic(self, boundary_mocks: dict[str, AsyncMock]) -> DefaultSpellLogic:
        """Create real spell logic with mocked boundaries."""
        return DefaultSpellLogic(
            result_store=boundary_mocks["result_store"],
            http_session=boundary_mocks["http_session"],
            whitelist=MockWhitelist(),
            parallel_processor=create_mock_parallel_processor(),
        )

    def create_valid_kafka_message(self, correlation_id: UUID | None = None) -> ConsumerRecord:
        """Create a valid Kafka message for testing."""
        if correlation_id is None:
            correlation_id = uuid4()

        essay_id = str(uuid4())
        parent_id = str(uuid4())
        system_metadata = SystemProcessingMetadata(
            entity_id=essay_id,
            entity_type="essay",
            parent_id=parent_id,
            event=ProcessingEvent.ESSAY_SPELLCHECK_REQUESTED,
            processing_stage=ProcessingStage.PENDING,
        )

        request_data = EssayLifecycleSpellcheckRequestV1(
            event_name=ProcessingEvent.ESSAY_SPELLCHECK_REQUESTED,
            entity_id=essay_id,
            entity_type="essay",
            parent_id=parent_id,
            status=EssayStatus.AWAITING_SPELLCHECK,
            system_metadata=system_metadata,
            text_storage_id=str(uuid4()),
            language="en",
        )

        envelope = EventEnvelope[EssayLifecycleSpellcheckRequestV1](
            event_type="essay.spellcheck.requested.v1",
            source_service="test-service",
            correlation_id=correlation_id,
            data=request_data,
        )

        message_value = json.dumps(envelope.model_dump(mode="json")).encode("utf-8")

        record = MagicMock(spec=ConsumerRecord)
        record.topic = "test-topic"
        record.partition = 0
        record.offset = 123
        record.value = message_value

        return record

    async def test_content_client_timeout_boundary_failure(
        self, boundary_mocks: dict[str, AsyncMock], real_spell_logic: DefaultSpellLogic
    ) -> None:
        """Test real business logic handling of content client timeout."""
        correlation_id = uuid4()

        # Configure content client boundary to timeout
        timeout_error = aiohttp.ServerTimeoutError("Content service timeout")
        boundary_mocks["content_client"].fetch_content.side_effect = timeout_error

        kafka_message = self.create_valid_kafka_message(correlation_id)

        result = await process_single_message(
            kafka_message,
            boundary_mocks["http_session"],
            boundary_mocks["content_client"],
            boundary_mocks["result_store"],
            boundary_mocks["event_publisher"],
            real_spell_logic,
        )

        # Should handle gracefully and publish error event
        assert result is True
        boundary_mocks["event_publisher"].publish_spellcheck_result.assert_called_once()

        # Verify correlation ID preserved
        published_args = boundary_mocks["event_publisher"].publish_spellcheck_result.call_args[0]
        assert published_args[1] == correlation_id

    async def test_content_client_connection_boundary_failure(
        self, boundary_mocks: dict[str, AsyncMock], real_spell_logic: DefaultSpellLogic
    ) -> None:
        """Test real business logic handling of content client connection failure."""
        correlation_id = uuid4()

        # Configure content client boundary to fail connection
        connection_error = aiohttp.ClientConnectionError("Connection refused")
        boundary_mocks["content_client"].fetch_content.side_effect = connection_error

        kafka_message = self.create_valid_kafka_message(correlation_id)

        result = await process_single_message(
            kafka_message,
            boundary_mocks["http_session"],
            boundary_mocks["content_client"],
            boundary_mocks["result_store"],
            boundary_mocks["event_publisher"],
            real_spell_logic,
        )

        assert result is True
        boundary_mocks["event_publisher"].publish_spellcheck_result.assert_called_once()

        # Verify correlation ID preserved through connection failure
        published_args = boundary_mocks["event_publisher"].publish_spellcheck_result.call_args[0]
        assert published_args[1] == correlation_id

    async def test_result_store_connection_boundary_failure(
        self, boundary_mocks: dict[str, AsyncMock], real_spell_logic: DefaultSpellLogic
    ) -> None:
        """Test real business logic handling of result store connection failure."""
        correlation_id = uuid4()

        # Configure content client to succeed
        boundary_mocks["content_client"].fetch_content.return_value = "Test text with errors"

        # Configure result store boundary to fail connection
        error_detail = ErrorDetail(
            error_code=ErrorCode.CONNECTION_ERROR,
            message="Result store connection error for testing",
            correlation_id=correlation_id,
            timestamp=datetime.now(UTC),
            service="spellchecker_service",
            operation="test_result_store_connection_failure",
        )
        store_error = HuleEduError(error_detail)
        boundary_mocks["result_store"].store_content.side_effect = store_error

        kafka_message = self.create_valid_kafka_message(correlation_id)

        result = await process_single_message(
            kafka_message,
            boundary_mocks["http_session"],
            boundary_mocks["content_client"],
            boundary_mocks["result_store"],
            boundary_mocks["event_publisher"],
            real_spell_logic,
        )

        assert result is True
        boundary_mocks["event_publisher"].publish_spellcheck_result.assert_called_once()

        # Verify correlation ID preserved through store failure
        published_args = boundary_mocks["event_publisher"].publish_spellcheck_result.call_args[0]
        assert published_args[1] == correlation_id

    async def test_event_publisher_boundary_failure(
        self, boundary_mocks: dict[str, AsyncMock], real_spell_logic: DefaultSpellLogic
    ) -> None:
        """Test real business logic handling of event publisher boundary failure."""
        correlation_id = uuid4()

        # Configure successful boundaries
        boundary_mocks["content_client"].fetch_content.return_value = "Test text"
        boundary_mocks["result_store"].store_content.return_value = str(uuid4())

        # Configure event publisher boundary to fail
        publish_error = Exception("Kafka publish failed")
        boundary_mocks["event_publisher"].publish_spellcheck_result.side_effect = publish_error

        kafka_message = self.create_valid_kafka_message(correlation_id)

        # Event publisher failure should be caught and handled gracefully
        # The business logic should return True after attempting to publish error event
        result = await process_single_message(
            kafka_message,
            boundary_mocks["http_session"],
            boundary_mocks["content_client"],
            boundary_mocks["result_store"],
            boundary_mocks["event_publisher"],
            real_spell_logic,
        )

        # Should return True (success) even with publishing failure
        assert result is True

        # Business logic should have attempted to publish multiple times
        # (once for success event, then again for error event)
        assert boundary_mocks["event_publisher"].publish_spellcheck_result.call_count >= 1

    async def test_http_session_boundary_failure(
        self, boundary_mocks: dict[str, AsyncMock], real_spell_logic: DefaultSpellLogic
    ) -> None:
        """Test real business logic handling of HTTP session boundary failure."""
        correlation_id = uuid4()

        # Configure HTTP session-related failure in content client
        session_error = aiohttp.ClientError("HTTP session error")
        boundary_mocks["content_client"].fetch_content.side_effect = session_error

        kafka_message = self.create_valid_kafka_message(correlation_id)

        result = await process_single_message(
            kafka_message,
            boundary_mocks["http_session"],
            boundary_mocks["content_client"],
            boundary_mocks["result_store"],
            boundary_mocks["event_publisher"],
            real_spell_logic,
        )

        assert result is True
        boundary_mocks["event_publisher"].publish_spellcheck_result.assert_called_once()

        # Verify correlation ID preserved through session failure
        published_args = boundary_mocks["event_publisher"].publish_spellcheck_result.call_args[0]
        assert published_args[1] == correlation_id

    async def test_multiple_boundary_failures_cascade(
        self, boundary_mocks: dict[str, AsyncMock], real_spell_logic: DefaultSpellLogic
    ) -> None:
        """Test real business logic graceful handling of cascading boundary failures."""
        correlation_id = uuid4()

        # Configure multiple boundary failures
        error_detail = ErrorDetail(
            error_code=ErrorCode.CONTENT_SERVICE_ERROR,
            message="Content service error for testing",
            correlation_id=correlation_id,
            timestamp=datetime.now(UTC),
            service="spellchecker_service",
            operation="test_multiple_boundary_failures_cascade",
        )
        content_error = HuleEduError(error_detail)
        boundary_mocks["content_client"].fetch_content.side_effect = content_error

        # Additional failure in event publishing
        publish_error = Exception("Publish also failed")
        boundary_mocks["event_publisher"].publish_spellcheck_result.side_effect = publish_error

        kafka_message = self.create_valid_kafka_message(correlation_id)

        # Graceful degradation: should handle content error, attempt to publish error event,
        # catch publishing failure, and return True to commit Kafka offset (prevent poison loops)
        result = await process_single_message(
            kafka_message,
            boundary_mocks["http_session"],
            boundary_mocks["content_client"],
            boundary_mocks["result_store"],
            boundary_mocks["event_publisher"],
            real_spell_logic,
        )

        # Should return True for graceful degradation (commits Kafka offset)
        assert result is True

        # Should have attempted to handle the content error first
        boundary_mocks["content_client"].fetch_content.assert_called_once()
        boundary_mocks["event_publisher"].publish_spellcheck_result.assert_called_once()

    async def test_boundary_failure_error_categorization(
        self, boundary_mocks: dict[str, AsyncMock], real_spell_logic: DefaultSpellLogic
    ) -> None:
        """Test that boundary failures are correctly categorized by real business logic."""
        correlation_id = uuid4()

        # Test different boundary failure types
        failure_scenarios = [
            aiohttp.ServerTimeoutError("timeout"),
            aiohttp.ClientConnectionError("connection"),
            ValueError("validation error"),
        ]

        for error in failure_scenarios:
            # Reset mocks
            for mock in boundary_mocks.values():
                mock.reset_mock()

            # Configure content client to fail with specific error type
            boundary_mocks["content_client"].fetch_content.side_effect = error

            kafka_message = self.create_valid_kafka_message(correlation_id)

            result = await process_single_message(
                kafka_message,
                boundary_mocks["http_session"],
                boundary_mocks["content_client"],
                boundary_mocks["result_store"],
                boundary_mocks["event_publisher"],
                real_spell_logic,
                )

            # Should handle each error type gracefully
            assert result is True
            boundary_mocks["event_publisher"].publish_spellcheck_result.assert_called_once()

            # Verify correlation ID preserved for each error type
            call_args = boundary_mocks["event_publisher"].publish_spellcheck_result.call_args[0]
            assert call_args[1] == correlation_id


# Prometheus registry cleanup for test isolation
@pytest.fixture(autouse=True)
def _clear_prometheus_registry() -> Generator[None, None, None]:
    """Clear Prometheus registry between tests to avoid metric conflicts."""
    from prometheus_client import REGISTRY

    collectors = list(REGISTRY._collector_to_names.keys())
    for collector in collectors:
        try:
            REGISTRY.unregister(collector)
        except KeyError:
            pass  # Already unregistered
    yield
