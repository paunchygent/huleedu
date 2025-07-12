"""Comprehensive error scenario tests for spellchecker service Phase 3 validation.

This test suite validates error handling robustness by testing real business logic
while only mocking external boundaries:

- Uses REAL business logic: DefaultSpellLogic, _categorize_processing_error, message processing
- Mocks ONLY boundaries: HTTP clients, storage, Kafka publishing
- Tests actual error handling robustness, not just passing tests

ULTRATHINK Requirements:
- Test actual behavior rather than assumptions
- Only mock external boundaries, never business logic
- Verify correlation ID propagation through real business flows
- Focused testing approach (NOT test-all)
"""

from __future__ import annotations

import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import aiohttp
import pytest
from aiokafka import ConsumerRecord
from huleedu_service_libs.error_handling.huleedu_error import HuleEduError
from pydantic import ValidationError

from common_core.error_enums import ErrorCode
from common_core.essay_service_models import EssayLifecycleSpellcheckRequestV1
from common_core.event_enums import ProcessingEvent
from common_core.events.envelope import EventEnvelope
from common_core.metadata_models import EntityReference, SystemProcessingMetadata
from common_core.status_enums import EssayStatus, ProcessingStage
from services.spellchecker_service.event_processor import (
    _categorize_processing_error,
    process_single_message,
)
from services.spellchecker_service.implementations.spell_logic_impl import DefaultSpellLogic
from services.spellchecker_service.protocols import (
    ContentClientProtocol,
    ResultStoreProtocol,
    SpellcheckEventPublisherProtocol,
)


class TestErrorCategorizationBusinessLogic:
    """Test the real _categorize_processing_error business logic works correctly."""

    def test_categorize_preserves_correlation_id(self) -> None:
        """Test that error categorization preserves correlation ID."""
        correlation_id = uuid4()
        exc = Exception("Test error")

        error_detail = _categorize_processing_error(exc, correlation_id)

        assert error_detail.correlation_id == correlation_id
        assert error_detail.service == "spellchecker_service"
        assert error_detail.operation == "categorize_processing_error"

    def test_categorize_preserves_original_error_context(self) -> None:
        """Test that error categorization preserves original error information."""
        correlation_id = uuid4()
        original_message = "Database connection failed"
        exc = RuntimeError(original_message)

        error_detail = _categorize_processing_error(exc, correlation_id)

        assert error_detail.details["original_exception_type"] == "RuntimeError"
        assert error_detail.details["original_message"] == original_message
        assert original_message in error_detail.message

    def test_categorize_huleedu_error_passthrough(self) -> None:
        """Test that HuleEduError instances are passed through unchanged."""
        correlation_id = uuid4()
        original_error_detail = MagicMock()
        original_error_detail.error_code = ErrorCode.CONTENT_SERVICE_ERROR
        original_error_detail.correlation_id = correlation_id

        huleedu_error = HuleEduError(original_error_detail)

        result = _categorize_processing_error(huleedu_error, uuid4())

        # Should return the original error detail unchanged
        assert result == original_error_detail

    def test_categorize_timeout_detection(self) -> None:
        """Test actual timeout error detection logic."""
        correlation_id = uuid4()

        # Test exceptions that actually contain "timeout" (not "timed out")
        timeout_exceptions = [
            Exception("Request timeout occurred"),
            aiohttp.ServerTimeoutError("Server timeout"),
            Exception("Connection timeout"),
        ]

        for exc in timeout_exceptions:
            error_detail = _categorize_processing_error(exc, correlation_id)
            assert error_detail.error_code == ErrorCode.TIMEOUT

        # Test that "timed out" does NOT match (falls back to PROCESSING_ERROR)
        timed_out_exception = Exception("Operation timed out")
        error_detail = _categorize_processing_error(timed_out_exception, correlation_id)
        assert error_detail.error_code == ErrorCode.PROCESSING_ERROR

    def test_categorize_connection_detection(self) -> None:
        """Test actual connection error detection logic."""
        correlation_id = uuid4()

        connection_exceptions = [
            Exception("Connection refused"),
            aiohttp.ClientConnectionError("Failed to connect"),
            Exception("Lost connection to server"),
        ]

        for exc in connection_exceptions:
            error_detail = _categorize_processing_error(exc, correlation_id)
            assert error_detail.error_code == ErrorCode.CONNECTION_ERROR

    def test_categorize_validation_detection(self) -> None:
        """Test actual validation error detection logic."""
        correlation_id = uuid4()

        validation_exceptions = [
            ValidationError.from_exception_data("TestModel", []),
            Exception("Validation failed for field"),
        ]

        for exc in validation_exceptions:
            error_detail = _categorize_processing_error(exc, correlation_id)
            assert error_detail.error_code == ErrorCode.VALIDATION_ERROR

    def test_categorize_parsing_detection(self) -> None:
        """Test actual parsing error detection logic."""
        correlation_id = uuid4()

        parsing_exceptions = [
            Exception("Failed to parse JSON"),
            json.JSONDecodeError("Invalid JSON", "", 0),
        ]

        for exc in parsing_exceptions:
            error_detail = _categorize_processing_error(exc, correlation_id)
            assert error_detail.error_code == ErrorCode.PARSING_ERROR

    def test_categorize_defaults_to_processing_error(self) -> None:
        """Test that unknown exceptions default to PROCESSING_ERROR."""
        correlation_id = uuid4()

        unknown_exceptions = [
            RuntimeError("Unknown runtime error"),
            ValueError("Invalid value provided"),
            KeyError("Missing key"),
        ]

        for exc in unknown_exceptions:
            error_detail = _categorize_processing_error(exc, correlation_id)
            assert error_detail.error_code == ErrorCode.PROCESSING_ERROR


class TestRealBusinessLogicWithBoundaryMocks:
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
            result_store=boundary_mocks["result_store"],
            http_session=boundary_mocks["http_session"]
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
        content_error = HuleEduError(MagicMock())
        content_error.error_detail.correlation_id = correlation_id
        content_error.error_detail.error_code = ErrorCode.CONTENT_SERVICE_ERROR
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
        # Create message with null correlation_id
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

        # Create envelope data with null correlation_id manually
        envelope_data = {
            "event_id": str(uuid4()),
            "event_type": "essay.spellcheck.requested.v1",
            "event_timestamp": datetime.now().isoformat(),
            "source_service": "test-service",
            "correlation_id": None,  # Test real validation logic
            "data": request_data.model_dump(mode="json"),
        }

        message_value = json.dumps(envelope_data).encode("utf-8")

        record = MagicMock(spec=ConsumerRecord)
        record.topic = "test-topic"
        record.partition = 0
        record.offset = 123
        record.value = message_value

        # Real business logic should detect missing correlation_id
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

        # Should use the service-specific correlation error (real business logic)
        assert "Missing correlation_id" in str(exc_info.value.error_detail.message)

    async def test_real_business_logic_with_successful_flow(
        self, boundary_mocks: dict[str, AsyncMock], real_spell_logic: DefaultSpellLogic
    ) -> None:
        """Test that real business logic works correctly when boundaries succeed."""
        correlation_id = uuid4()

        # Configure boundary mocks to succeed
        boundary_mocks["content_client"].fetch_content.return_value = (
            "This is test text with mistaeks"
        )
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


# Prometheus registry cleanup for test isolation
@pytest.fixture(autouse=True)
def _clear_prometheus_registry() -> None:
    """Clear Prometheus registry between tests to avoid metric conflicts."""
    from prometheus_client import REGISTRY

    collectors = list(REGISTRY._collector_to_names.keys())
    for collector in collectors:
        try:
            REGISTRY.unregister(collector)
        except KeyError:
            pass  # Already unregistered
    yield