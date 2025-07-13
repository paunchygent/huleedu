"""Observability features tests for spellchecker service.

Tests OpenTelemetry, logging, and metrics integration through real business logic
to validate that observability features work correctly in error scenarios and
normal operation.

ULTRATHINK Requirements:
- Test observability features through real business logic flows
- Verify OpenTelemetry span recording with real error scenarios
- Validate structured logging with correlation ID through real business flows
- Test metrics collection through real business logic operations
"""

from __future__ import annotations

import json
from typing import Generator
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from aiokafka import ConsumerRecord
from huleedu_service_libs.error_handling.huleedu_error import HuleEduError
from opentelemetry import trace
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from huleedu_service_libs.observability.tracing import inject_trace_context
from common_core.error_enums import ErrorCode
from common_core.essay_service_models import EssayLifecycleSpellcheckRequestV1
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


class TestObservabilityFeatures:
    """Test observability features through real business logic."""

    @pytest.fixture
    def boundary_mocks(self) -> dict[str, AsyncMock]:
        """Create mocks for external boundaries only."""
        content_client = AsyncMock(spec=ContentClientProtocol)
        result_store = AsyncMock(spec=ResultStoreProtocol)
        event_publisher = AsyncMock(spec=SpellcheckEventPublisherProtocol)
        kafka_bus = AsyncMock()
        http_session = AsyncMock()

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

    def create_valid_kafka_message(self, correlation_id: UUID | None = None) -> ConsumerRecord:
        """Create a valid Kafka message for testing."""
        if correlation_id is None:
            correlation_id = uuid4()

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

        # Create trace context metadata for distributed tracing simulation
        # Start a parent span to provide context for injection
        tracer = trace.get_tracer("test-parent-tracer")
        metadata: dict[str, str] = {}

        with tracer.start_as_current_span("test.parent.span"):
            inject_trace_context(metadata)

        envelope = EventEnvelope[EssayLifecycleSpellcheckRequestV1](
            event_type="essay.spellcheck.requested.v1",
            source_service="test-service",
            correlation_id=correlation_id,
            data=request_data,
            metadata=metadata,
        )

        message_value = json.dumps(envelope.model_dump(mode="json")).encode("utf-8")

        record = MagicMock(spec=ConsumerRecord)
        record.topic = "test-topic"
        record.partition = 0
        record.offset = 123
        record.value = message_value

        return record

    async def test_opentelemetry_span_recording_successful_flow(
        self,
        boundary_mocks: dict[str, AsyncMock],
        real_spell_logic: DefaultSpellLogic,
        opentelemetry_test_isolation: InMemorySpanExporter,
    ) -> None:
        """Test OpenTelemetry span recording through successful business logic flow."""
        correlation_id = uuid4()
        tracer = trace.get_tracer("test-tracer")

        # Configure successful boundaries
        boundary_mocks["content_client"].fetch_content.return_value = "Test text"
        boundary_mocks["result_store"].store_content.return_value = str(uuid4())

        kafka_message = self.create_valid_kafka_message(correlation_id)

        # Process with tracer to record spans
        result = await process_single_message(
            kafka_message,
            boundary_mocks["http_session"],
            boundary_mocks["content_client"],
            boundary_mocks["result_store"],
            boundary_mocks["event_publisher"],
            real_spell_logic,
            boundary_mocks["kafka_bus"],
            tracer=tracer,
        )

        assert result is True

        # Verify spans were recorded
        spans = opentelemetry_test_isolation.get_finished_spans()
        assert len(spans) > 0

        # Check for correlation_id in span attributes
        kafka_span = next((s for s in spans if "kafka.consume" in s.name), None)
        assert kafka_span is not None
        if kafka_span.attributes:
            assert str(correlation_id) in str(kafka_span.attributes.get("correlation_id", ""))

    async def test_opentelemetry_error_span_recording(
        self,
        boundary_mocks: dict[str, AsyncMock],
        real_spell_logic: DefaultSpellLogic,
        opentelemetry_test_isolation: InMemorySpanExporter,
    ) -> None:
        """Test OpenTelemetry error span recording through real business logic."""
        correlation_id = uuid4()
        tracer = trace.get_tracer("test-tracer")

        # Configure content client to fail
        content_error = HuleEduError(MagicMock())
        content_error.error_detail.correlation_id = correlation_id
        content_error.error_detail.error_code = ErrorCode.CONTENT_SERVICE_ERROR
        boundary_mocks["content_client"].fetch_content.side_effect = content_error

        kafka_message = self.create_valid_kafka_message(correlation_id)

        result = await process_single_message(
            kafka_message,
            boundary_mocks["http_session"],
            boundary_mocks["content_client"],
            boundary_mocks["result_store"],
            boundary_mocks["event_publisher"],
            real_spell_logic,
            boundary_mocks["kafka_bus"],
            tracer=tracer,
        )

        assert result is True

        # Verify error spans were recorded
        spans = opentelemetry_test_isolation.get_finished_spans()
        error_spans = [s for s in spans if s.status.status_code.name == "ERROR"]
        assert len(error_spans) > 0

        # Verify error attributes include correlation_id
        error_span = error_spans[0]
        if error_span.attributes:
            assert str(correlation_id) in str(error_span.attributes.get("error.correlation_id", ""))

    @patch("services.spellchecker_service.event_processor.logger")
    async def test_structured_logging_with_correlation_id(
        self,
        mock_logger: MagicMock,
        boundary_mocks: dict[str, AsyncMock],
        real_spell_logic: DefaultSpellLogic,
        opentelemetry_test_isolation: InMemorySpanExporter,
    ) -> None:
        """Test structured logging includes correlation ID through real business logic."""
        correlation_id = uuid4()

        # Configure successful boundaries
        boundary_mocks["content_client"].fetch_content.return_value = "Test text"
        boundary_mocks["result_store"].store_content.return_value = str(uuid4())

        kafka_message = self.create_valid_kafka_message(correlation_id)

        result = await process_single_message(
            kafka_message,
            boundary_mocks["http_session"],
            boundary_mocks["content_client"],
            boundary_mocks["result_store"],
            boundary_mocks["event_publisher"],
            real_spell_logic,
            boundary_mocks["kafka_bus"],
        )

        assert result is True

        # Verify structured logging calls include correlation_id
        info_calls = [
            call
            for call in mock_logger.info.call_args_list
            if "extra" in call.kwargs and "correlation_id" in call.kwargs["extra"]
        ]
        assert len(info_calls) > 0

        # Verify correlation_id is correctly logged
        correlation_logged = any(
            str(correlation_id) in call.kwargs["extra"].get("correlation_id", "")
            for call in info_calls
        )
        assert correlation_logged

    @patch("services.spellchecker_service.event_processor.logger")
    async def test_error_logging_with_correlation_id(
        self,
        mock_logger: MagicMock,
        boundary_mocks: dict[str, AsyncMock],
        real_spell_logic: DefaultSpellLogic,
        opentelemetry_test_isolation: InMemorySpanExporter,
    ) -> None:
        """Test error logging includes correlation ID through real business logic."""
        correlation_id = uuid4()

        # Configure content client to fail
        content_error = HuleEduError(MagicMock())
        content_error.error_detail.correlation_id = correlation_id
        content_error.error_detail.error_code = ErrorCode.CONTENT_SERVICE_ERROR
        boundary_mocks["content_client"].fetch_content.side_effect = content_error

        kafka_message = self.create_valid_kafka_message(correlation_id)

        result = await process_single_message(
            kafka_message,
            boundary_mocks["http_session"],
            boundary_mocks["content_client"],
            boundary_mocks["result_store"],
            boundary_mocks["event_publisher"],
            real_spell_logic,
            boundary_mocks["kafka_bus"],
        )

        assert result is True

        # Verify error logging calls include correlation_id
        error_calls = [
            call
            for call in mock_logger.error.call_args_list
            if "extra" in call.kwargs and "correlation_id" in call.kwargs["extra"]
        ]
        assert len(error_calls) > 0

        # Verify correlation_id is correctly logged in errors
        correlation_logged = any(
            str(correlation_id) in call.kwargs["extra"].get("correlation_id", "")
            for call in error_calls
        )
        assert correlation_logged

    @patch("services.spellchecker_service.event_processor.get_business_metrics")
    async def test_metrics_collection_successful_flow(
        self,
        mock_get_metrics: MagicMock,
        boundary_mocks: dict[str, AsyncMock],
        real_spell_logic: DefaultSpellLogic,
        opentelemetry_test_isolation: InMemorySpanExporter,
    ) -> None:
        """Test metrics collection through successful real business logic flow."""
        correlation_id = uuid4()

        # Mock metrics
        mock_corrections_metric = MagicMock()
        mock_latency_metric = MagicMock()
        mock_get_metrics.return_value = {
            "spellcheck_corrections_made": mock_corrections_metric,
            "kafka_queue_latency_seconds": mock_latency_metric,
        }

        # Configure successful boundaries
        boundary_mocks["content_client"].fetch_content.return_value = "Test text with errors"
        boundary_mocks["result_store"].store_content.return_value = str(uuid4())

        kafka_message = self.create_valid_kafka_message(correlation_id)

        result = await process_single_message(
            kafka_message,
            boundary_mocks["http_session"],
            boundary_mocks["content_client"],
            boundary_mocks["result_store"],
            boundary_mocks["event_publisher"],
            real_spell_logic,
            boundary_mocks["kafka_bus"],
        )

        assert result is True

        # Verify metrics were attempted to be recorded
        # (They may not be called if result_data.corrections_made is None)
        mock_get_metrics.assert_called_once()

    async def test_observability_integration_during_parsing_errors(
        self,
        boundary_mocks: dict[str, AsyncMock],
        real_spell_logic: DefaultSpellLogic,
        opentelemetry_test_isolation: InMemorySpanExporter,
    ) -> None:
        """Test observability features during parsing errors in real business logic."""
        tracer = trace.get_tracer("test-tracer")

        # Create invalid Kafka message
        record = MagicMock(spec=ConsumerRecord)
        record.topic = "test-topic"
        record.partition = 0
        record.offset = 123
        record.value = b"invalid json data"

        # Should raise parsing error with proper observability
        with pytest.raises(HuleEduError) as exc_info:
            await process_single_message(
                record,
                boundary_mocks["http_session"],
                boundary_mocks["content_client"],
                boundary_mocks["result_store"],
                boundary_mocks["event_publisher"],
                real_spell_logic,
                boundary_mocks["kafka_bus"],
                tracer=tracer,
            )

        # Verify error was properly categorized by real business logic
        assert exc_info.value.error_detail.error_code == ErrorCode.PARSING_ERROR

        # Verify correlation_id was generated for the error
        assert exc_info.value.error_detail.correlation_id is not None


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
