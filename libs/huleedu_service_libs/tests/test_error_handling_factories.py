"""
Unit tests for error handling factory functions.

Tests comprehensive coverage of all 29 factory functions in the error handling
framework. Validates ErrorDetail creation, HuleEduError raising, parameter handling,
and correlation ID propagation. Follows HuleEdu testing excellence patterns.
"""

from __future__ import annotations

import uuid
from typing import Any
from uuid import UUID

import pytest
from common_core.error_enums import ErrorCode
from huleedu_service_libs.error_handling.factories import (
    raise_ai_feedback_service_error,
    raise_authentication_error,
    raise_authorization_error,
    raise_circuit_breaker_open,
    raise_cj_assessment_service_error,
    raise_configuration_error,
    raise_connection_error,
    raise_content_service_error,
    raise_external_service_error,
    raise_initialization_failed,
    raise_invalid_api_key,
    raise_invalid_configuration,
    raise_invalid_request,
    raise_invalid_response,
    raise_kafka_publish_error,
    raise_missing_required_field,
    raise_nlp_service_error,
    raise_outbox_storage_error,
    raise_parsing_error,
    raise_processing_error,
    raise_quota_exceeded,
    raise_rate_limit_error,
    raise_request_queued,
    raise_resource_not_found,
    raise_service_unavailable,
    raise_spellcheck_service_error,
    raise_timeout_error,
    raise_unknown_error,
    raise_validation_error,
)
from huleedu_service_libs.error_handling.huleedu_error import HuleEduError


# Test fixtures and utilities
@pytest.fixture
def test_service() -> str:
    """Provide consistent service name for testing."""
    return "test_service"


@pytest.fixture
def test_operation() -> str:
    """Provide consistent operation name for testing."""
    return "test_operation"


@pytest.fixture
def test_correlation_id() -> UUID:
    """Provide consistent correlation ID for testing."""
    return uuid.uuid4()


@pytest.fixture
def test_message() -> str:
    """Provide consistent error message for testing."""
    return "Test error message"


class TestGenericErrorFactories:
    """Test generic error factory functions."""

    def test_raise_unknown_error(
        self, test_service: str, test_operation: str, test_correlation_id: UUID, test_message: str
    ) -> None:
        """Test raise_unknown_error creates proper HuleEduError."""
        additional_context: dict[str, Any] = {"extra_info": "test_value", "debug_data": 123}

        with pytest.raises(HuleEduError) as exc_info:
            raise_unknown_error(
                service=test_service,
                operation=test_operation,
                message=test_message,
                correlation_id=test_correlation_id,
                **additional_context,
            )

        error: HuleEduError = exc_info.value
        assert error.error_code == ErrorCode.UNKNOWN_ERROR.value
        assert error.service == test_service
        assert error.operation == test_operation
        assert error.correlation_id == str(test_correlation_id)
        assert str(error) == f"[{ErrorCode.UNKNOWN_ERROR.value}] {test_message}"

        # Verify ErrorDetail properties
        error_detail = error.error_detail
        assert error_detail.error_code == ErrorCode.UNKNOWN_ERROR
        assert error_detail.message == test_message
        assert error_detail.service == test_service
        assert error_detail.operation == test_operation
        assert error_detail.correlation_id == test_correlation_id
        assert error_detail.details == additional_context

    def test_raise_validation_error_with_value(
        self, test_service: str, test_operation: str, test_correlation_id: UUID
    ) -> None:
        """Test raise_validation_error with field value provided."""
        field: str = "email"
        message: str = "Invalid email format"
        value: str = "invalid-email"
        additional_context: dict[str, Any] = {"format_expected": "user@domain.com"}

        with pytest.raises(HuleEduError) as exc_info:
            raise_validation_error(
                service=test_service,
                operation=test_operation,
                field=field,
                message=message,
                correlation_id=test_correlation_id,
                value=value,
                **additional_context,
            )

        error: HuleEduError = exc_info.value
        assert error.error_code == ErrorCode.VALIDATION_ERROR.value
        assert error.error_detail.error_code == ErrorCode.VALIDATION_ERROR

        expected_details: dict[str, Any] = {
            "field": field,
            "value": value,
            **additional_context,
        }
        assert error.error_detail.details == expected_details

    def test_raise_validation_error_without_value(
        self, test_service: str, test_operation: str, test_correlation_id: UUID
    ) -> None:
        """Test raise_validation_error without field value."""
        field: str = "username"
        message: str = "Username is required"

        with pytest.raises(HuleEduError) as exc_info:
            raise_validation_error(
                service=test_service,
                operation=test_operation,
                field=field,
                message=message,
                correlation_id=test_correlation_id,
            )

        error: HuleEduError = exc_info.value
        expected_details: dict[str, Any] = {"field": field}
        assert error.error_detail.details == expected_details

    def test_raise_resource_not_found(
        self, test_service: str, test_operation: str, test_correlation_id: UUID
    ) -> None:
        """Test raise_resource_not_found creates proper error with auto-generated message."""
        resource_type: str = "User"
        resource_id: str = "user_123"
        additional_context: dict[str, Any] = {"search_criteria": "active=true"}

        with pytest.raises(HuleEduError) as exc_info:
            raise_resource_not_found(
                service=test_service,
                operation=test_operation,
                resource_type=resource_type,
                resource_id=resource_id,
                correlation_id=test_correlation_id,
                **additional_context,
            )

        error: HuleEduError = exc_info.value
        assert error.error_code == ErrorCode.RESOURCE_NOT_FOUND.value
        expected_message: str = f"{resource_type} with ID '{resource_id}' not found"
        assert error.error_detail.message == expected_message

        expected_details: dict[str, Any] = {
            "resource_type": resource_type,
            "resource_id": resource_id,
            **additional_context,
        }
        assert error.error_detail.details == expected_details

    def test_raise_configuration_error(
        self, test_service: str, test_operation: str, test_correlation_id: UUID, test_message: str
    ) -> None:
        """Test raise_configuration_error with config key."""
        config_key: str = "DATABASE_URL"
        additional_context: dict[str, Any] = {"environment": "production"}

        with pytest.raises(HuleEduError) as exc_info:
            raise_configuration_error(
                service=test_service,
                operation=test_operation,
                config_key=config_key,
                message=test_message,
                correlation_id=test_correlation_id,
                **additional_context,
            )

        error: HuleEduError = exc_info.value
        assert error.error_code == ErrorCode.CONFIGURATION_ERROR.value
        expected_details: dict[str, Any] = {
            "config_key": config_key,
            **additional_context,
        }
        assert error.error_detail.details == expected_details

    def test_raise_missing_required_field(
        self, test_service: str, test_operation: str, test_correlation_id: UUID
    ) -> None:
        """Test raise_missing_required_field with auto-generated message."""
        field_name: str = "password"
        additional_context: dict[str, Any] = {"form_section": "authentication"}

        with pytest.raises(HuleEduError) as exc_info:
            raise_missing_required_field(
                service=test_service,
                operation=test_operation,
                field_name=field_name,
                correlation_id=test_correlation_id,
                **additional_context,
            )

        error: HuleEduError = exc_info.value
        assert error.error_code == ErrorCode.MISSING_REQUIRED_FIELD.value
        expected_message: str = f"Required field '{field_name}' is missing"
        assert error.error_detail.message == expected_message

        expected_details: dict[str, Any] = {
            "field_name": field_name,
            **additional_context,
        }
        assert error.error_detail.details == expected_details

    def test_raise_invalid_configuration(
        self, test_service: str, test_operation: str, test_correlation_id: UUID, test_message: str
    ) -> None:
        """Test raise_invalid_configuration basic error."""
        additional_context: dict[str, Any] = {"config_file": "settings.yaml"}

        with pytest.raises(HuleEduError) as exc_info:
            raise_invalid_configuration(
                service=test_service,
                operation=test_operation,
                message=test_message,
                correlation_id=test_correlation_id,
                **additional_context,
            )

        error: HuleEduError = exc_info.value
        assert error.error_code == ErrorCode.INVALID_CONFIGURATION.value
        assert error.error_detail.details == additional_context

    def test_raise_processing_error(
        self, test_service: str, test_operation: str, test_correlation_id: UUID, test_message: str
    ) -> None:
        """Test raise_processing_error basic error."""
        additional_context: dict[str, Any] = {"step": "data_validation", "attempt": 3}

        with pytest.raises(HuleEduError) as exc_info:
            raise_processing_error(
                service=test_service,
                operation=test_operation,
                message=test_message,
                correlation_id=test_correlation_id,
                **additional_context,
            )

        error: HuleEduError = exc_info.value
        assert error.error_code == ErrorCode.PROCESSING_ERROR.value
        assert error.error_detail.details == additional_context


class TestServiceSpecificErrorFactories:
    """Test service-specific error factory functions."""

    def test_raise_content_service_error(
        self, test_service: str, test_operation: str, test_correlation_id: UUID, test_message: str
    ) -> None:
        """Test raise_content_service_error."""
        additional_context: dict[str, Any] = {"content_id": "content_123"}

        with pytest.raises(HuleEduError) as exc_info:
            raise_content_service_error(
                service=test_service,
                operation=test_operation,
                message=test_message,
                correlation_id=test_correlation_id,
                **additional_context,
            )

        error: HuleEduError = exc_info.value
        assert error.error_code == ErrorCode.CONTENT_SERVICE_ERROR.value
        assert error.error_detail.details == additional_context

    def test_raise_spellcheck_service_error(
        self, test_service: str, test_operation: str, test_correlation_id: UUID, test_message: str
    ) -> None:
        """Test raise_spellcheck_service_error."""
        additional_context: dict[str, Any] = {"text_length": 1500, "language": "en"}

        with pytest.raises(HuleEduError) as exc_info:
            raise_spellcheck_service_error(
                service=test_service,
                operation=test_operation,
                message=test_message,
                correlation_id=test_correlation_id,
                **additional_context,
            )

        error: HuleEduError = exc_info.value
        assert error.error_code == ErrorCode.SPELLCHECK_SERVICE_ERROR.value
        assert error.error_detail.details == additional_context

    def test_raise_nlp_service_error(
        self, test_service: str, test_operation: str, test_correlation_id: UUID, test_message: str
    ) -> None:
        """Test raise_nlp_service_error."""
        additional_context: dict[str, Any] = {"model": "bert-base", "tokens": 512}

        with pytest.raises(HuleEduError) as exc_info:
            raise_nlp_service_error(
                service=test_service,
                operation=test_operation,
                message=test_message,
                correlation_id=test_correlation_id,
                **additional_context,
            )

        error: HuleEduError = exc_info.value
        assert error.error_code == ErrorCode.NLP_SERVICE_ERROR.value
        assert error.error_detail.details == additional_context

    def test_raise_ai_feedback_service_error(
        self, test_service: str, test_operation: str, test_correlation_id: UUID, test_message: str
    ) -> None:
        """Test raise_ai_feedback_service_error."""
        additional_context: dict[str, Any] = {"essay_id": "essay_456", "model_version": "v2.1"}

        with pytest.raises(HuleEduError) as exc_info:
            raise_ai_feedback_service_error(
                service=test_service,
                operation=test_operation,
                message=test_message,
                correlation_id=test_correlation_id,
                **additional_context,
            )

        error: HuleEduError = exc_info.value
        assert error.error_code == ErrorCode.AI_FEEDBACK_SERVICE_ERROR.value
        assert error.error_detail.details == additional_context

    def test_raise_cj_assessment_service_error(
        self, test_service: str, test_operation: str, test_correlation_id: UUID, test_message: str
    ) -> None:
        """Test raise_cj_assessment_service_error."""
        additional_context: dict[str, Any] = {
            "comparison_id": "cmp_789",
            "algorithm": "bradley_terry",
        }

        with pytest.raises(HuleEduError) as exc_info:
            raise_cj_assessment_service_error(
                service=test_service,
                operation=test_operation,
                message=test_message,
                correlation_id=test_correlation_id,
                **additional_context,
            )

        error: HuleEduError = exc_info.value
        assert error.error_code == ErrorCode.CJ_ASSESSMENT_SERVICE_ERROR.value
        assert error.error_detail.details == additional_context


class TestExternalServiceErrorFactories:
    """Test external service error factory functions."""

    def test_raise_external_service_error_with_status_code(
        self, test_service: str, test_operation: str, test_correlation_id: UUID, test_message: str
    ) -> None:
        """Test raise_external_service_error with status code."""
        external_service: str = "payment_gateway"
        status_code: int = 503
        additional_context: dict[str, Any] = {"endpoint": "/api/v1/charge", "retry_count": 2}

        with pytest.raises(HuleEduError) as exc_info:
            raise_external_service_error(
                service=test_service,
                operation=test_operation,
                external_service=external_service,
                message=test_message,
                correlation_id=test_correlation_id,
                status_code=status_code,
                **additional_context,
            )

        error: HuleEduError = exc_info.value
        assert error.error_code == ErrorCode.EXTERNAL_SERVICE_ERROR.value

        expected_details: dict[str, Any] = {
            "external_service": external_service,
            "status_code": status_code,
            **additional_context,
        }
        assert error.error_detail.details == expected_details

    def test_raise_external_service_error_without_status_code(
        self, test_service: str, test_operation: str, test_correlation_id: UUID, test_message: str
    ) -> None:
        """Test raise_external_service_error without status code."""
        external_service: str = "analytics_service"

        with pytest.raises(HuleEduError) as exc_info:
            raise_external_service_error(
                service=test_service,
                operation=test_operation,
                external_service=external_service,
                message=test_message,
                correlation_id=test_correlation_id,
            )

        error: HuleEduError = exc_info.value
        expected_details: dict[str, Any] = {"external_service": external_service}
        assert error.error_detail.details == expected_details

    def test_raise_timeout_error(
        self, test_service: str, test_operation: str, test_correlation_id: UUID, test_message: str
    ) -> None:
        """Test raise_timeout_error with timeout duration."""
        timeout_seconds: float = 30.5
        additional_context: dict[str, Any] = {"operation_type": "database_query"}

        with pytest.raises(HuleEduError) as exc_info:
            raise_timeout_error(
                service=test_service,
                operation=test_operation,
                timeout_seconds=timeout_seconds,
                message=test_message,
                correlation_id=test_correlation_id,
                **additional_context,
            )

        error: HuleEduError = exc_info.value
        assert error.error_code == ErrorCode.TIMEOUT.value

        expected_details: dict[str, Any] = {
            "timeout_seconds": timeout_seconds,
            **additional_context,
        }
        assert error.error_detail.details == expected_details

    def test_raise_connection_error(
        self, test_service: str, test_operation: str, test_correlation_id: UUID, test_message: str
    ) -> None:
        """Test raise_connection_error with target information."""
        target: str = "database.example.com:5432"
        additional_context: dict[str, Any] = {"connection_pool": "primary", "ssl_enabled": True}

        with pytest.raises(HuleEduError) as exc_info:
            raise_connection_error(
                service=test_service,
                operation=test_operation,
                target=target,
                message=test_message,
                correlation_id=test_correlation_id,
                **additional_context,
            )

        error: HuleEduError = exc_info.value
        assert error.error_code == ErrorCode.CONNECTION_ERROR.value

        expected_details: dict[str, Any] = {
            "target": target,
            **additional_context,
        }
        assert error.error_detail.details == expected_details

    def test_raise_service_unavailable(
        self, test_service: str, test_operation: str, test_correlation_id: UUID, test_message: str
    ) -> None:
        """Test raise_service_unavailable with unavailable service."""
        unavailable_service: str = "auth_service"
        additional_context: dict[str, Any] = {
            "health_check_failed": True,
            "last_success": "2024-01-01T10:00:00Z",
        }

        with pytest.raises(HuleEduError) as exc_info:
            raise_service_unavailable(
                service=test_service,
                operation=test_operation,
                unavailable_service=unavailable_service,
                message=test_message,
                correlation_id=test_correlation_id,
                **additional_context,
            )

        error: HuleEduError = exc_info.value
        assert error.error_code == ErrorCode.SERVICE_UNAVAILABLE.value

        expected_details: dict[str, Any] = {
            "unavailable_service": unavailable_service,
            **additional_context,
        }
        assert error.error_detail.details == expected_details

    def test_raise_rate_limit_error(
        self, test_service: str, test_operation: str, test_correlation_id: UUID, test_message: str
    ) -> None:
        """Test raise_rate_limit_error with limit parameters."""
        limit: int = 100
        window_seconds: int = 3600
        additional_context: dict[str, Any] = {
            "current_count": 105,
            "reset_time": "2024-01-01T11:00:00Z",
        }

        with pytest.raises(HuleEduError) as exc_info:
            raise_rate_limit_error(
                service=test_service,
                operation=test_operation,
                limit=limit,
                window_seconds=window_seconds,
                message=test_message,
                correlation_id=test_correlation_id,
                **additional_context,
            )

        error: HuleEduError = exc_info.value
        assert error.error_code == ErrorCode.RATE_LIMIT.value

        expected_details: dict[str, Any] = {
            "limit": limit,
            "window_seconds": window_seconds,
            **additional_context,
        }
        assert error.error_detail.details == expected_details

    def test_raise_quota_exceeded(
        self, test_service: str, test_operation: str, test_correlation_id: UUID, test_message: str
    ) -> None:
        """Test raise_quota_exceeded with quota information."""
        quota_type: str = "api_calls"
        limit: int = 10000
        additional_context: dict[str, Any] = {"current_usage": 10001, "billing_period": "monthly"}

        with pytest.raises(HuleEduError) as exc_info:
            raise_quota_exceeded(
                service=test_service,
                operation=test_operation,
                quota_type=quota_type,
                limit=limit,
                message=test_message,
                correlation_id=test_correlation_id,
                **additional_context,
            )

        error: HuleEduError = exc_info.value
        assert error.error_code == ErrorCode.QUOTA_EXCEEDED.value

        expected_details: dict[str, Any] = {
            "quota_type": quota_type,
            "limit": limit,
            **additional_context,
        }
        assert error.error_detail.details == expected_details

    def test_raise_invalid_request(
        self, test_service: str, test_operation: str, test_correlation_id: UUID, test_message: str
    ) -> None:
        """Test raise_invalid_request basic error."""
        additional_context: dict[str, Any] = {
            "request_id": "req_12345",
            "validation_errors": ["missing_header"],
        }

        with pytest.raises(HuleEduError) as exc_info:
            raise_invalid_request(
                service=test_service,
                operation=test_operation,
                message=test_message,
                correlation_id=test_correlation_id,
                **additional_context,
            )

        error: HuleEduError = exc_info.value
        assert error.error_code == ErrorCode.INVALID_REQUEST.value
        assert error.error_detail.details == additional_context

    def test_raise_invalid_response(
        self, test_service: str, test_operation: str, test_correlation_id: UUID, test_message: str
    ) -> None:
        """Test raise_invalid_response basic error."""
        additional_context: dict[str, Any] = {"response_status": 200, "expected_format": "json"}

        with pytest.raises(HuleEduError) as exc_info:
            raise_invalid_response(
                service=test_service,
                operation=test_operation,
                message=test_message,
                correlation_id=test_correlation_id,
                **additional_context,
            )

        error: HuleEduError = exc_info.value
        assert error.error_code == ErrorCode.INVALID_RESPONSE.value
        assert error.error_detail.details == additional_context


class TestInfrastructureErrorFactories:
    """Test infrastructure error factory functions."""

    def test_raise_kafka_publish_error(
        self, test_service: str, test_operation: str, test_correlation_id: UUID, test_message: str
    ) -> None:
        """Test raise_kafka_publish_error with topic information."""
        topic: str = "user.events.v1"
        additional_context: dict[str, Any] = {"partition": 0, "broker": "kafka-01.example.com"}

        with pytest.raises(HuleEduError) as exc_info:
            raise_kafka_publish_error(
                service=test_service,
                operation=test_operation,
                topic=topic,
                message=test_message,
                correlation_id=test_correlation_id,
                **additional_context,
            )

        error: HuleEduError = exc_info.value
        assert error.error_code == ErrorCode.KAFKA_PUBLISH_ERROR.value

        expected_details: dict[str, Any] = {
            "topic": topic,
            **additional_context,
        }
        assert error.error_detail.details == expected_details

    def test_raise_outbox_storage_error(
        self, test_service: str, test_operation: str, test_correlation_id: UUID
    ) -> None:
        """Test raise_outbox_storage_error with auto-generated message."""
        message: str = "Database connection failed"
        aggregate_id: str = "user_123"
        aggregate_type: str = "User"
        event_type: str = "UserCreated"
        additional_context: dict[str, Any] = {
            "table": "outbox_events",
            "sql_error": "connection_timeout",
        }

        with pytest.raises(HuleEduError) as exc_info:
            raise_outbox_storage_error(
                service=test_service,
                operation=test_operation,
                message=message,
                correlation_id=test_correlation_id,
                aggregate_id=aggregate_id,
                aggregate_type=aggregate_type,
                event_type=event_type,
                **additional_context,
            )

        error: HuleEduError = exc_info.value
        assert (
            error.error_code == ErrorCode.KAFKA_PUBLISH_ERROR.value
        )  # Uses same code as Kafka publish
        expected_message: str = f"Outbox storage failed: {message}"
        assert error.error_detail.message == expected_message

        expected_details: dict[str, Any] = {
            "aggregate_id": aggregate_id,
            "aggregate_type": aggregate_type,
            "event_type": event_type,
            "outbox_operation": "store",
            **additional_context,
        }
        assert error.error_detail.details == expected_details

    def test_raise_authentication_error(
        self, test_service: str, test_operation: str, test_correlation_id: UUID, test_message: str
    ) -> None:
        """Test raise_authentication_error."""
        additional_context: dict[str, Any] = {"auth_method": "jwt", "token_expired": True}

        with pytest.raises(HuleEduError) as exc_info:
            raise_authentication_error(
                service=test_service,
                operation=test_operation,
                message=test_message,
                correlation_id=test_correlation_id,
                **additional_context,
            )

        error: HuleEduError = exc_info.value
        assert error.error_code == ErrorCode.AUTHENTICATION_ERROR.value
        assert error.error_detail.details == additional_context

    def test_raise_authorization_error(
        self, test_service: str, test_operation: str, test_correlation_id: UUID, test_message: str
    ) -> None:
        """Test raise_authorization_error."""
        additional_context: dict[str, Any] = {"required_role": "admin", "user_role": "user"}

        with pytest.raises(HuleEduError) as exc_info:
            raise_authorization_error(
                service=test_service,
                operation=test_operation,
                message=test_message,
                correlation_id=test_correlation_id,
                **additional_context,
            )

        error: HuleEduError = exc_info.value
        assert error.error_code == ErrorCode.AUTHORIZATION_ERROR.value
        assert error.error_detail.details == additional_context

    def test_raise_invalid_api_key(
        self, test_service: str, test_operation: str, test_correlation_id: UUID
    ) -> None:
        """Test raise_invalid_api_key with auto-generated message."""
        additional_context: dict[str, Any] = {
            "key_prefix": "sk_test_",
            "validation_step": "signature",
        }

        with pytest.raises(HuleEduError) as exc_info:
            raise_invalid_api_key(
                service=test_service,
                operation=test_operation,
                correlation_id=test_correlation_id,
                **additional_context,
            )

        error: HuleEduError = exc_info.value
        assert error.error_code == ErrorCode.INVALID_API_KEY.value
        expected_message: str = "Invalid or missing API key"
        assert error.error_detail.message == expected_message
        assert error.error_detail.details == additional_context

    def test_raise_parsing_error(
        self, test_service: str, test_operation: str, test_correlation_id: UUID, test_message: str
    ) -> None:
        """Test raise_parsing_error with parse target."""
        parse_target: str = "json_response"
        additional_context: dict[str, Any] = {"line": 42, "column": 15, "expected": "string"}

        with pytest.raises(HuleEduError) as exc_info:
            raise_parsing_error(
                service=test_service,
                operation=test_operation,
                parse_target=parse_target,
                message=test_message,
                correlation_id=test_correlation_id,
                **additional_context,
            )

        error: HuleEduError = exc_info.value
        assert error.error_code == ErrorCode.PARSING_ERROR.value

        expected_details: dict[str, Any] = {
            "parse_target": parse_target,
            **additional_context,
        }
        assert error.error_detail.details == expected_details

    def test_raise_circuit_breaker_open(
        self, test_service: str, test_operation: str, test_correlation_id: UUID, test_message: str
    ) -> None:
        """Test raise_circuit_breaker_open with circuit information."""
        circuit_name: str = "database_circuit"
        additional_context: dict[str, Any] = {
            "failure_count": 5,
            "last_failure": "2024-01-01T10:30:00Z",
        }

        with pytest.raises(HuleEduError) as exc_info:
            raise_circuit_breaker_open(
                service=test_service,
                operation=test_operation,
                circuit_name=circuit_name,
                message=test_message,
                correlation_id=test_correlation_id,
                **additional_context,
            )

        error: HuleEduError = exc_info.value
        assert error.error_code == ErrorCode.CIRCUIT_BREAKER_OPEN.value

        expected_details: dict[str, Any] = {
            "circuit_name": circuit_name,
            **additional_context,
        }
        assert error.error_detail.details == expected_details

    def test_raise_request_queued(
        self, test_service: str, test_operation: str, test_correlation_id: UUID, test_message: str
    ) -> None:
        """Test raise_request_queued with queue information."""
        queue_name: str = "priority_queue"
        additional_context: dict[str, Any] = {"position": 15, "estimated_wait_seconds": 120}

        with pytest.raises(HuleEduError) as exc_info:
            raise_request_queued(
                service=test_service,
                operation=test_operation,
                queue_name=queue_name,
                message=test_message,
                correlation_id=test_correlation_id,
                **additional_context,
            )

        error: HuleEduError = exc_info.value
        assert error.error_code == ErrorCode.REQUEST_QUEUED.value

        expected_details: dict[str, Any] = {
            "queue_name": queue_name,
            **additional_context,
        }
        assert error.error_detail.details == expected_details

    def test_raise_initialization_failed(
        self, test_service: str, test_operation: str, test_correlation_id: UUID, test_message: str
    ) -> None:
        """Test raise_initialization_failed with component information."""
        component: str = "database_pool"
        additional_context: dict[str, Any] = {
            "config_file": "db.yaml",
            "startup_phase": "connection_validation",
        }

        with pytest.raises(HuleEduError) as exc_info:
            raise_initialization_failed(
                service=test_service,
                operation=test_operation,
                component=component,
                message=test_message,
                correlation_id=test_correlation_id,
                **additional_context,
            )

        error: HuleEduError = exc_info.value
        assert error.error_code == ErrorCode.INITIALIZATION_FAILED.value

        expected_details: dict[str, Any] = {
            "component": component,
            **additional_context,
        }
        assert error.error_detail.details == expected_details


class TestFactoryFunctionEdgeCases:
    """Test edge cases and boundary conditions for factory functions."""

    def test_empty_additional_context(
        self, test_service: str, test_operation: str, test_correlation_id: UUID, test_message: str
    ) -> None:
        """Test factory functions with empty additional context."""
        with pytest.raises(HuleEduError) as exc_info:
            raise_unknown_error(
                service=test_service,
                operation=test_operation,
                message=test_message,
                correlation_id=test_correlation_id,
            )

        error: HuleEduError = exc_info.value
        assert error.error_detail.details == {}

    def test_complex_additional_context(
        self, test_service: str, test_operation: str, test_correlation_id: UUID, test_message: str
    ) -> None:
        """Test factory functions with complex additional context data."""
        complex_context: dict[str, Any] = {
            "nested_dict": {"key1": "value1", "key2": {"nested": True}},
            "list_data": [1, 2, 3, "string"],
            "boolean_flag": True,
            "numeric_value": 42.5,
            "none_value": None,
        }

        with pytest.raises(HuleEduError) as exc_info:
            raise_processing_error(
                service=test_service,
                operation=test_operation,
                message=test_message,
                correlation_id=test_correlation_id,
                **complex_context,
            )

        error: HuleEduError = exc_info.value
        assert error.error_detail.details == complex_context

    def test_correlation_id_propagation(
        self, test_service: str, test_operation: str, test_message: str
    ) -> None:
        """Test that correlation ID is properly propagated through error creation."""
        correlation_id: UUID = uuid.uuid4()

        with pytest.raises(HuleEduError) as exc_info:
            raise_validation_error(
                service=test_service,
                operation=test_operation,
                field="test_field",
                message=test_message,
                correlation_id=correlation_id,
            )

        error: HuleEduError = exc_info.value
        assert error.error_detail.correlation_id == correlation_id
        assert error.correlation_id == str(correlation_id)

    def test_error_detail_immutability(
        self, test_service: str, test_operation: str, test_correlation_id: UUID, test_message: str
    ) -> None:
        """Test that ErrorDetail instances are immutable as expected."""
        with pytest.raises(HuleEduError) as exc_info:
            raise_unknown_error(
                service=test_service,
                operation=test_operation,
                message=test_message,
                correlation_id=test_correlation_id,
            )

        error: HuleEduError = exc_info.value
        error_detail = error.error_detail

        # Verify ErrorDetail is frozen (immutable)
        with pytest.raises(ValueError, match="Instance is frozen"):
            error_detail.message = "Modified message"  # type: ignore[misc]

    def test_all_factory_functions_return_huleedu_error(
        self, test_service: str, test_operation: str, test_correlation_id: UUID, test_message: str
    ) -> None:
        """Test that all factory functions consistently return HuleEduError instances."""
        factory_functions = [
            lambda: raise_unknown_error(
                test_service, test_operation, test_message, test_correlation_id
            ),
            lambda: raise_validation_error(
                test_service, test_operation, "field", test_message, test_correlation_id
            ),
            lambda: raise_resource_not_found(
                test_service, test_operation, "Resource", "123", test_correlation_id
            ),
            lambda: raise_configuration_error(
                test_service, test_operation, "key", test_message, test_correlation_id
            ),
            lambda: raise_processing_error(
                test_service, test_operation, test_message, test_correlation_id
            ),
        ]

        for factory_function in factory_functions:
            with pytest.raises(HuleEduError) as exc_info:
                factory_function()

            error: HuleEduError = exc_info.value
            assert isinstance(error, HuleEduError)
            assert isinstance(error, Exception)
            assert error.service == test_service
            assert error.operation == test_operation
            assert error.correlation_id == str(test_correlation_id)
