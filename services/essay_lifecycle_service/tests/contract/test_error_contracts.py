"""
Error Contract Testing for Essay Lifecycle Service.

This module provides comprehensive contract tests for HuleEduError and ErrorDetail
to ensure proper serialization, correlation ID propagation, and observability
integration across service boundaries.

Following ULTRATHINK methodology for distributed systems error handling validation.
"""

import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from common_core.error_enums import ErrorCode
from common_core.models.error_models import ErrorDetail
from huleedu_service_libs.error_handling import HuleEduError
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter


class TestErrorDetailContracts:
    """Test contracts for ErrorDetail Pydantic model serialization and structure."""

    def test_error_detail_required_fields_contract(self) -> None:
        """Contract test: ErrorDetail must have all required fields with correct types."""
        correlation_id = uuid4()
        timestamp = datetime.now(UTC)

        # Act - Create ErrorDetail with all required fields
        error_detail = ErrorDetail(
            error_code=ErrorCode.RESOURCE_NOT_FOUND,
            message="Test error message",
            correlation_id=correlation_id,
            timestamp=timestamp,
            service="essay_lifecycle_service",
            operation="test_operation",
        )

        # Assert - All required fields present and correct types
        assert error_detail.error_code == ErrorCode.RESOURCE_NOT_FOUND
        assert error_detail.message == "Test error message"
        assert error_detail.correlation_id == correlation_id
        assert error_detail.timestamp == timestamp
        assert error_detail.service == "essay_lifecycle_service"
        assert error_detail.operation == "test_operation"
        assert error_detail.details == {}  # Default empty dict
        assert error_detail.stack_trace is None  # Default None
        assert error_detail.trace_id is None  # Default None
        assert error_detail.span_id is None  # Default None

    def test_error_detail_serialization_contract(self) -> None:
        """Contract test: ErrorDetail must serialize/deserialize consistently."""
        # Arrange
        correlation_id = uuid4()
        timestamp = datetime.now(UTC)
        error_detail = ErrorDetail(
            error_code=ErrorCode.VALIDATION_ERROR,
            message="Validation failed",
            correlation_id=correlation_id,
            timestamp=timestamp,
            service="essay_lifecycle_service",
            operation="validate_input",
            details={"field": "essay_id", "value": "invalid"},
            stack_trace="Stack trace here",
            trace_id="trace-123",
            span_id="span-456",
        )

        # Act - Serialize to dict and back
        serialized = error_detail.model_dump()
        deserialized = ErrorDetail.model_validate(serialized)

        # Assert - Perfect round-trip preservation
        assert deserialized == error_detail
        assert deserialized.error_code == ErrorCode.VALIDATION_ERROR
        assert deserialized.correlation_id == correlation_id
        assert deserialized.timestamp == timestamp
        assert deserialized.details == {"field": "essay_id", "value": "invalid"}
        assert deserialized.trace_id == "trace-123"
        assert deserialized.span_id == "span-456"

    def test_error_detail_json_serialization_contract(self) -> None:
        """Contract test: ErrorDetail must serialize to/from JSON for service boundaries."""
        # Arrange
        correlation_id = uuid4()
        timestamp = datetime.now(UTC)
        error_detail = ErrorDetail(
            error_code=ErrorCode.PROCESSING_ERROR,
            message="Processing failed",
            correlation_id=correlation_id,
            timestamp=timestamp,
            service="essay_lifecycle_service",
            operation="process_batch",
            details={"batch_id": "batch-123", "retry_count": 3},
        )

        # Act - JSON round-trip
        json_str = error_detail.model_dump_json()
        json_dict = json.loads(json_str)
        deserialized = ErrorDetail.model_validate(json_dict)

        # Assert - JSON structure contracts
        assert "error_code" in json_dict
        assert "correlation_id" in json_dict
        assert "timestamp" in json_dict
        assert json_dict["error_code"] == "PROCESSING_ERROR"
        assert json_dict["service"] == "essay_lifecycle_service"

        # Assert - Perfect deserialization
        assert deserialized.error_code == ErrorCode.PROCESSING_ERROR
        assert deserialized.correlation_id == correlation_id
        assert deserialized.details == {"batch_id": "batch-123", "retry_count": 3}

    def test_error_detail_immutability_contract(self) -> None:
        """Contract test: ErrorDetail must be immutable (frozen=True)."""
        error_detail = ErrorDetail(
            error_code=ErrorCode.EXTERNAL_SERVICE_ERROR,
            message="Service unavailable",
            correlation_id=uuid4(),
            timestamp=datetime.now(UTC),
            service="essay_lifecycle_service",
            operation="call_external_service",
        )

        # Assert - Cannot modify fields (raises ValidationError)
        with pytest.raises(ValueError):  # Pydantic raises ValidationError for frozen models
            error_detail.message = "Modified message"  # type: ignore


class TestHuleEduErrorContracts:
    """Test contracts for HuleEduError exception integration and behavior."""

    def test_huleedu_error_wrapping_contract(self) -> None:
        """Contract test: HuleEduError must properly wrap ErrorDetail."""
        # Arrange
        correlation_id = uuid4()
        error_detail = ErrorDetail(
            error_code=ErrorCode.RESOURCE_NOT_FOUND,
            message="Essay not found",
            correlation_id=correlation_id,
            timestamp=datetime.now(UTC),
            service="essay_lifecycle_service",
            operation="get_essay_state",
        )

        # Act
        huleedu_error = HuleEduError(error_detail)

        # Assert - Proper wrapping and property access
        assert huleedu_error.error_detail == error_detail
        assert huleedu_error.correlation_id == str(correlation_id)
        assert huleedu_error.error_code == "RESOURCE_NOT_FOUND"
        assert huleedu_error.service == "essay_lifecycle_service"
        assert huleedu_error.operation == "get_essay_state"
        assert str(huleedu_error) == "[RESOURCE_NOT_FOUND] Essay not found"

    def test_huleedu_error_serialization_contract(self) -> None:
        """Contract test: HuleEduError must serialize properly for service boundaries."""
        # Arrange
        correlation_id = uuid4()
        error_detail = ErrorDetail(
            error_code=ErrorCode.KAFKA_PUBLISH_ERROR,
            message="Failed to publish event",
            correlation_id=correlation_id,
            timestamp=datetime.now(UTC),
            service="essay_lifecycle_service",
            operation="publish_status_update",
            details={"topic": "essay.status.events", "retry_attempts": 3},
        )
        huleedu_error = HuleEduError(error_detail)

        # Act - Serialize to dictionary
        error_dict = huleedu_error.to_dict()

        # Assert - Dictionary structure contract
        assert "error" in error_dict
        assert "error_detail" in error_dict
        assert error_dict["error"] == "[KAFKA_PUBLISH_ERROR] Failed to publish event"

        # Assert - Error detail serialization
        error_detail_dict = error_dict["error_detail"]
        assert error_detail_dict["error_code"] == "KAFKA_PUBLISH_ERROR"
        assert error_detail_dict["correlation_id"] == correlation_id  # UUID object, not string
        assert error_detail_dict["service"] == "essay_lifecycle_service"
        assert error_detail_dict["details"]["topic"] == "essay.status.events"

    def test_huleedu_error_immutable_add_detail_contract(self) -> None:
        """Contract test: HuleEduError.add_detail() must create new instances."""
        # Arrange
        original_error = HuleEduError(
            ErrorDetail(
                error_code=ErrorCode.VALIDATION_ERROR,
                message="Validation failed",
                correlation_id=uuid4(),
                timestamp=datetime.now(UTC),
                service="essay_lifecycle_service",
                operation="validate_essay",
                details={"field": "title"},
            )
        )

        # Act - Add detail creates new instance
        enhanced_error = original_error.add_detail("validation_rule", "required")

        # Assert - Immutability contract
        assert enhanced_error is not original_error
        assert original_error.error_detail.details == {"field": "title"}
        assert enhanced_error.error_detail.details == {
            "field": "title",
            "validation_rule": "required",
        }

        # Assert - All other fields preserved
        assert enhanced_error.correlation_id == original_error.correlation_id
        assert enhanced_error.error_code == original_error.error_code
        assert enhanced_error.service == original_error.service


class TestCorrelationIdPropagationContracts:
    """Test contracts for correlation ID propagation across error transformations."""

    def test_correlation_id_preservation_contract(self) -> None:
        """Contract test: Correlation ID must be preserved through all error transformations."""
        # Arrange
        original_correlation_id = uuid4()

        # Act - Create error and perform various transformations
        error_detail = ErrorDetail(
            error_code=ErrorCode.PROCESSING_ERROR,
            message="Processing failed",
            correlation_id=original_correlation_id,
            timestamp=datetime.now(UTC),
            service="essay_lifecycle_service",
            operation="process_request",
        )
        huleedu_error = HuleEduError(error_detail)
        enhanced_error = huleedu_error.add_detail("context", "additional_info")
        serialized = enhanced_error.to_dict()

        # Assert - Correlation ID preserved throughout
        assert error_detail.correlation_id == original_correlation_id
        assert huleedu_error.correlation_id == str(original_correlation_id)
        assert enhanced_error.correlation_id == str(original_correlation_id)
        assert (
            serialized["error_detail"]["correlation_id"] == original_correlation_id
        )  # UUID object in serialized form

    def test_correlation_id_type_consistency_contract(self) -> None:
        """Contract test: Correlation ID type handling must be consistent."""
        # Arrange
        correlation_id = uuid4()
        error_detail = ErrorDetail(
            error_code=ErrorCode.EXTERNAL_SERVICE_ERROR,
            message="Service error",
            correlation_id=correlation_id,
            timestamp=datetime.now(UTC),
            service="essay_lifecycle_service",
            operation="call_service",
        )
        huleedu_error = HuleEduError(error_detail)

        # Assert - Type consistency contract
        assert isinstance(error_detail.correlation_id, UUID)  # ErrorDetail stores UUID
        assert isinstance(huleedu_error.correlation_id, str)  # HuleEduError exposes string
        assert UUID(huleedu_error.correlation_id) == correlation_id  # Round-trip works


class TestOpenTelemetryIntegrationContracts:
    """Test contracts for OpenTelemetry integration and span recording."""

    @pytest.fixture
    def mock_tracer_setup(self) -> tuple[InMemorySpanExporter, trace.Tracer]:
        """Setup mock tracer with in-memory span exporter."""
        # Setup in-memory span exporter
        span_exporter = InMemorySpanExporter()
        span_processor = SimpleSpanProcessor(span_exporter)

        # Create tracer provider and tracer
        tracer_provider = TracerProvider()
        tracer_provider.add_span_processor(span_processor)
        tracer = tracer_provider.get_tracer(__name__)

        # Set as global tracer
        trace.set_tracer_provider(tracer_provider)

        return span_exporter, tracer

    def test_opentelemetry_span_recording_contract(
        self, mock_tracer_setup: tuple[InMemorySpanExporter, trace.Tracer]
    ) -> None:
        """Contract test: HuleEduError must record to OpenTelemetry spans."""
        # Arrange
        span_exporter, tracer = mock_tracer_setup
        correlation_id = uuid4()

        # Act - Create error within span context
        with tracer.start_as_current_span("test_operation"):
            error_detail = ErrorDetail(
                error_code=ErrorCode.RESOURCE_NOT_FOUND,
                message="Resource not found",
                correlation_id=correlation_id,
                timestamp=datetime.now(UTC),
                service="essay_lifecycle_service",
                operation="find_resource",
                details={"resource_id": "essay-123"},
            )
            _ = HuleEduError(error_detail)  # Creating the error triggers span recording

        # Assert - Span recording contract
        spans = span_exporter.get_finished_spans()
        assert len(spans) == 1

        recorded_span = spans[0]
        assert recorded_span.status.status_code == trace.StatusCode.ERROR
        assert recorded_span.status.description == "Resource not found"

        # Assert - Error attributes contract
        attributes = recorded_span.attributes
        assert attributes is not None
        assert attributes["error"] is True
        assert attributes["error.code"] == "RESOURCE_NOT_FOUND"
        assert attributes["error.message"] == "Resource not found"
        assert attributes["error.service"] == "essay_lifecycle_service"
        assert attributes["error.operation"] == "find_resource"
        assert attributes["correlation_id"] == str(correlation_id)
        assert attributes["error.details.resource_id"] == "essay-123"

    def test_opentelemetry_exception_recording_contract(
        self, mock_tracer_setup: tuple[InMemorySpanExporter, trace.Tracer]
    ) -> None:
        """Contract test: HuleEduError must record exception to spans."""
        # Arrange
        span_exporter, tracer = mock_tracer_setup

        # Act - Create error and record exception
        with tracer.start_as_current_span("test_operation"):
            error_detail = ErrorDetail(
                error_code=ErrorCode.VALIDATION_ERROR,
                message="Validation failed",
                correlation_id=uuid4(),
                timestamp=datetime.now(UTC),
                service="essay_lifecycle_service",
                operation="validate_input",
            )
            _ = HuleEduError(error_detail)  # Creating the error triggers span recording

        # Assert - Exception recording contract
        spans = span_exporter.get_finished_spans()
        assert len(spans) == 1

        recorded_span = spans[0]
        # Check that exception was recorded (events contain exception data)
        events = recorded_span.events
        assert len(events) > 0

        # Find exception event
        exception_events = [event for event in events if event.name == "exception"]
        assert len(exception_events) == 1

        exception_event = exception_events[0]
        event_attributes = exception_event.attributes
        assert event_attributes is not None
        assert "exception.type" in event_attributes
        assert "exception.message" in event_attributes
        assert (
            event_attributes["exception.type"]
            == "huleedu_service_libs.error_handling.huleedu_error.HuleEduError"
        )


class TestErrorContractValidationUtilities:
    """Test utilities for validating error contracts in other test suites."""

    def test_error_contract_validation_utility_comprehensive(self) -> None:
        """Test comprehensive error contract validation utility."""
        # This tests the utility functions created in conftest.py
        from services.essay_lifecycle_service.tests.conftest import (
            assert_correlation_id_propagated,
            assert_error_detail_structure,
            assert_huleedu_error,
        )

        # Arrange
        correlation_id = uuid4()
        error_detail = ErrorDetail(
            error_code=ErrorCode.PROCESSING_ERROR,
            message="Processing failed",
            correlation_id=correlation_id,
            timestamp=datetime.now(UTC),
            service="essay_lifecycle_service",
            operation="process_data",
            details={"context": "test"},
        )
        huleedu_error = HuleEduError(error_detail)

        # Act & Assert - All utility functions work correctly
        assert_error_detail_structure(error_detail.model_dump())
        assert_huleedu_error(huleedu_error, "PROCESSING_ERROR", correlation_id)
        assert_correlation_id_propagated(huleedu_error, correlation_id)

        # Assert - Utilities validate structure properly
        # These should not raise any exceptions if contracts are correct


class TestCrossServiceErrorContracts:
    """Test contracts for error propagation across service boundaries."""

    def test_event_envelope_error_propagation_contract(self) -> None:
        """Contract test: Errors must propagate properly through event envelopes."""

        # Arrange - Create error that would be sent across services
        correlation_id = uuid4()
        error_detail = ErrorDetail(
            error_code=ErrorCode.KAFKA_PUBLISH_ERROR,
            message="Failed to publish event",
            correlation_id=correlation_id,
            timestamp=datetime.now(UTC),
            service="essay_lifecycle_service",
            operation="publish_batch_ready",
            details={"topic": "batch.essays.ready", "batch_id": "batch-123"},
        )
        huleedu_error = HuleEduError(error_detail)

        # Act - Serialize error for cross-service transmission
        error_dict = huleedu_error.to_dict()

        # Assert - Error can be transmitted and reconstructed
        transmitted_error_detail = ErrorDetail.model_validate(error_dict["error_detail"])
        reconstructed_error = HuleEduError(transmitted_error_detail)

        # Assert - Perfect reconstruction contract
        assert reconstructed_error.correlation_id == huleedu_error.correlation_id
        assert reconstructed_error.error_code == huleedu_error.error_code
        assert reconstructed_error.service == huleedu_error.service
        assert str(reconstructed_error) == str(huleedu_error)

    def test_http_api_error_response_contract(self) -> None:
        """Contract test: Errors must serialize properly for HTTP API responses."""
        # Arrange
        correlation_id = uuid4()
        error_detail = ErrorDetail(
            error_code=ErrorCode.RESOURCE_NOT_FOUND,
            message="Essay not found",
            correlation_id=correlation_id,
            timestamp=datetime.now(UTC),
            service="essay_lifecycle_service",
            operation="get_essay_status",
            details={"essay_id": "essay-404"},
        )
        huleedu_error = HuleEduError(error_detail)

        # Act - Convert to HTTP response format
        response_dict = huleedu_error.to_dict()
        response_json = json.dumps(response_dict, default=str)  # Handle UUID/datetime
        parsed_response = json.loads(response_json)

        # Assert - HTTP response contract
        assert "error" in parsed_response
        assert "error_detail" in parsed_response
        assert parsed_response["error_detail"]["error_code"] == "RESOURCE_NOT_FOUND"
        assert parsed_response["error_detail"]["correlation_id"] == str(correlation_id)

        # Assert - API client can reconstruct error
        reconstructed_detail = ErrorDetail.model_validate(parsed_response["error_detail"])
        assert reconstructed_detail.correlation_id == correlation_id
        assert reconstructed_detail.error_code == ErrorCode.RESOURCE_NOT_FOUND
