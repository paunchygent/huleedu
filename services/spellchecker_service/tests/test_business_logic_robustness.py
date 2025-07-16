"""Business logic robustness tests for spellchecker service.

Tests real DefaultSpellLogic error handling robustness with boundary mocks only.
This validates that the actual business logic correctly handles all error scenarios
while only mocking external boundaries.

ULTRATHINK Requirements:
- Use REAL business logic: DefaultSpellLogic, process_single_message
- Mock ONLY boundaries: HTTP clients, storage, Kafka publishing
- Test actual error handling robustness, not just passing tests
- Verify correlation ID propagation through real business flows
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
from huleedu_service_libs.error_handling.huleedu_error import HuleEduError

from common_core.error_enums import ErrorCode
from common_core.essay_service_models import EssayLifecycleSpellcheckRequestV1
from common_core.models.error_models import ErrorDetail
from common_core.event_enums import ProcessingEvent
from common_core.events.envelope import EventEnvelope
from common_core.metadata_models import EntityReference, SystemProcessingMetadata
from common_core.status_enums import EssayStatus, ProcessingStage
from services.spellchecker_service.event_processor import process_single_message
from services.spellchecker_service.implementations.spell_logic_impl import DefaultSpellLogic
from services.spellchecker_service.protocols import (
    ContentClientProtocol,
    ResultStoreProtocol,
    SpellcheckEventPublisherProtocol,
)


class TestRealBusinessLogicRobustness:
    """Test real business logic robustness with only boundary mocking."""

    @pytest.fixture
    def boundary_mocks(self) -> dict[str, AsyncMock]:
        """Create mocks for external boundaries only."""
        # Mock external boundaries
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
            result_store=boundary_mocks["result_store"], http_session=boundary_mocks["http_session"]
        )

    def create_valid_kafka_message(self, correlation_id: UUID) -> ConsumerRecord:
        """Create a valid Kafka message for testing."""
        entity_ref = EntityReference(entity_id=str(uuid4()), entity_type="essay")
        system_metadata = SystemProcessingMetadata(
            entity=entity_ref,
            event=ProcessingEvent.ESSAY_SPELLCHECK_REQUESTED,
            processing_stage=ProcessingStage.PENDING,
        )

        request_data = EssayLifecycleSpellcheckRequestV1(
            event_name=ProcessingEvent.ESSAY_SPELLCHECK_REQUESTED,
            entity_ref=entity_ref,
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

    async def test_real_business_logic_handles_content_service_errors(
        self, boundary_mocks: dict[str, AsyncMock], real_spell_logic: DefaultSpellLogic
    ) -> None:
        """Test that real business logic properly handles content service errors."""
        correlation_id = uuid4()

        # Configure content client boundary to fail
        error_detail = ErrorDetail(
            error_code=ErrorCode.CONTENT_SERVICE_ERROR,
            message="Content service error for testing",
            correlation_id=correlation_id,
            timestamp=datetime.now(UTC),
            service="spellchecker_service",
            operation="test_content_service_errors_through_real_business_logic",
        )
        content_error = HuleEduError(error_detail)
        boundary_mocks["content_client"].fetch_content.side_effect = content_error

        # Create valid message
        kafka_message = self.create_valid_kafka_message(correlation_id)

        # Test real business logic with boundary failure
        result = await process_single_message(
            kafka_message,
            boundary_mocks["http_session"],
            boundary_mocks["content_client"],
            boundary_mocks["result_store"],
            boundary_mocks["event_publisher"],
            real_spell_logic,
            boundary_mocks["kafka_bus"],
        )

        # Should handle error gracefully and publish error event
        assert result is True  # Message processing completed
        boundary_mocks["event_publisher"].publish_spellcheck_result.assert_called_once()

        # Verify correlation ID propagated through real business logic
        published_args = boundary_mocks["event_publisher"].publish_spellcheck_result.call_args[0]
        published_correlation_id = published_args[2]
        assert published_correlation_id == correlation_id

    async def test_real_parsing_logic_handles_invalid_messages(
        self, boundary_mocks: dict[str, AsyncMock], real_spell_logic: DefaultSpellLogic
    ) -> None:
        """Test that real message parsing logic handles invalid messages."""
        # Create invalid Kafka message - real business logic should handle this
        record = MagicMock(spec=ConsumerRecord)
        record.topic = "test-topic"
        record.partition = 0
        record.offset = 123
        record.value = b"invalid json data"

        # Real business logic should raise structured error
        with pytest.raises(HuleEduError) as exc_info:
            await process_single_message(
                record,
                boundary_mocks["http_session"],
                boundary_mocks["content_client"],
                boundary_mocks["result_store"],
                boundary_mocks["event_publisher"],
                real_spell_logic,
                boundary_mocks["kafka_bus"],
            )

        # Verify real business logic correctly categorized the error
        assert exc_info.value.error_detail.error_code == ErrorCode.PARSING_ERROR
        assert isinstance(exc_info.value.error_detail.correlation_id, UUID)

    async def test_real_correlation_id_validation_logic(
        self, boundary_mocks: dict[str, AsyncMock], real_spell_logic: DefaultSpellLogic
    ) -> None:
        """Test that real business logic validates correlation IDs properly."""
        # Create a valid message first, then create envelope with null correlation_id
        correlation_id = uuid4()
        kafka_message = self.create_valid_kafka_message(correlation_id)

        # Parse the valid message and modify it to have null correlation_id
        valid_envelope_data = json.loads(kafka_message.value.decode("utf-8"))
        valid_envelope_data["correlation_id"] = None

        # Create new message with null correlation_id
        message_value = json.dumps(valid_envelope_data).encode("utf-8")

        record = MagicMock(spec=ConsumerRecord)
        record.topic = "test-topic"
        record.partition = 0
        record.offset = 123
        record.value = message_value

        # Real business logic should raise parsing error due to null UUID
        with pytest.raises(HuleEduError) as exc_info:
            await process_single_message(
                record,
                boundary_mocks["http_session"],
                boundary_mocks["content_client"],
                boundary_mocks["result_store"],
                boundary_mocks["event_publisher"],
                real_spell_logic,
                boundary_mocks["kafka_bus"],
            )

        # Should be a parsing error since null UUID fails Pydantic validation
        assert exc_info.value.error_detail.error_code == ErrorCode.PARSING_ERROR

    async def test_real_business_logic_with_successful_flow(
        self, boundary_mocks: dict[str, AsyncMock], real_spell_logic: DefaultSpellLogic
    ) -> None:
        """Test that real business logic works correctly when boundaries succeed."""
        correlation_id = uuid4()

        # Configure boundary mocks to succeed
        boundary_mocks[
            "content_client"
        ].fetch_content.return_value = "This is test text with mistaeks"
        boundary_mocks["result_store"].store_content.return_value = str(uuid4())

        # Create valid message
        kafka_message = self.create_valid_kafka_message(correlation_id)

        # Test complete real business logic flow
        result = await process_single_message(
            kafka_message,
            boundary_mocks["http_session"],
            boundary_mocks["content_client"],
            boundary_mocks["result_store"],
            boundary_mocks["event_publisher"],
            real_spell_logic,
            boundary_mocks["kafka_bus"],
        )

        # Should complete successfully
        assert result is True

        # Verify real business logic called boundaries correctly
        boundary_mocks["content_client"].fetch_content.assert_called_once()
        boundary_mocks["event_publisher"].publish_spellcheck_result.assert_called_once()

        # Verify correlation ID propagated through real business logic
        published_args = boundary_mocks["event_publisher"].publish_spellcheck_result.call_args[0]
        published_correlation_id = published_args[2]
        assert published_correlation_id == correlation_id

    async def test_real_business_logic_handles_result_store_errors(
        self, boundary_mocks: dict[str, AsyncMock], real_spell_logic: DefaultSpellLogic
    ) -> None:
        """Test real business logic handling of result store boundary failures."""
        correlation_id = uuid4()

        # Configure content client to succeed, result store to fail
        boundary_mocks["content_client"].fetch_content.return_value = "Test text with errors"

        # Configure result store boundary to fail during spell check
        error_detail = ErrorDetail(
            error_code=ErrorCode.PROCESSING_ERROR,
            message="Result store error for testing",
            correlation_id=correlation_id,
            timestamp=datetime.now(UTC),
            service="spellchecker_service",
            operation="test_real_business_logic_handles_result_store_errors",
        )
        store_error = HuleEduError(error_detail)
        boundary_mocks["result_store"].store_content.side_effect = store_error

        kafka_message = self.create_valid_kafka_message(correlation_id)

        # Real business logic should handle store failure gracefully
        result = await process_single_message(
            kafka_message,
            boundary_mocks["http_session"],
            boundary_mocks["content_client"],
            boundary_mocks["result_store"],
            boundary_mocks["event_publisher"],
            real_spell_logic,
            boundary_mocks["kafka_bus"],
        )

        # Should complete and publish error event
        assert result is True
        boundary_mocks["event_publisher"].publish_spellcheck_result.assert_called_once()

        # Verify correlation ID preserved through real business logic
        published_args = boundary_mocks["event_publisher"].publish_spellcheck_result.call_args[0]
        published_correlation_id = published_args[2]
        assert published_correlation_id == correlation_id

    async def test_real_business_logic_handles_empty_content(
        self, boundary_mocks: dict[str, AsyncMock], real_spell_logic: DefaultSpellLogic
    ) -> None:
        """Test real business logic validation of empty content."""
        correlation_id = uuid4()

        # Configure content client to return empty content
        boundary_mocks["content_client"].fetch_content.return_value = ""

        kafka_message = self.create_valid_kafka_message(correlation_id)

        # Real business logic should validate and handle empty content
        result = await process_single_message(
            kafka_message,
            boundary_mocks["http_session"],
            boundary_mocks["content_client"],
            boundary_mocks["result_store"],
            boundary_mocks["event_publisher"],
            real_spell_logic,
            boundary_mocks["kafka_bus"],
        )

        # Should handle validation error and publish error event
        assert result is True
        boundary_mocks["event_publisher"].publish_spellcheck_result.assert_called_once()

        # Verify error event with correlation ID
        published_args = boundary_mocks["event_publisher"].publish_spellcheck_result.call_args[0]
        published_correlation_id = published_args[2]
        assert published_correlation_id == correlation_id


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
