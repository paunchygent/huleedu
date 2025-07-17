"""
Comprehensive tests for LLM Provider Service event models.

Tests validation, serialization, and real-world scenarios for:
- TokenUsage model validation
- LLMComparisonResultV1 success/error scenarios
- Field validation and mutual exclusion
- JSON serialization/deserialization
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from common_core.config_enums import LLMProviderType
from common_core.domain_enums import EssayComparisonWinner
from common_core.error_enums import ErrorCode
from common_core.events.llm_provider_events import (
    LLMComparisonResultV1,
    LLMCostAlertV1,
    LLMCostTrackingV1,
    LLMProviderFailureV1,
    LLMRequestCompletedV1,
    LLMRequestStartedV1,
    LLMUsageAnalyticsV1,
    TokenUsage,
)
from common_core.models.error_models import ErrorDetail
from pydantic import ValidationError


class TestTokenUsage:
    """Test suite for TokenUsage model validation."""

    def test_token_usage_creation_with_defaults(self) -> None:
        """Test creating TokenUsage with default values."""
        usage = TokenUsage()

        assert usage.prompt_tokens == 0
        assert usage.completion_tokens == 0
        assert usage.total_tokens == 0

    def test_token_usage_with_valid_values(self) -> None:
        """Test TokenUsage with valid positive values."""
        usage = TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150)

        assert usage.prompt_tokens == 100
        assert usage.completion_tokens == 50
        assert usage.total_tokens == 150

    def test_token_usage_validation_non_negative(self) -> None:
        """Test that TokenUsage enforces non-negative values."""
        # Test negative prompt tokens
        with pytest.raises(ValidationError) as exc_info:
            TokenUsage(prompt_tokens=-1, completion_tokens=0, total_tokens=0)
        assert "greater than or equal to 0" in str(exc_info.value)

        # Test negative completion tokens
        with pytest.raises(ValidationError) as exc_info:
            TokenUsage(prompt_tokens=0, completion_tokens=-10, total_tokens=0)
        assert "greater than or equal to 0" in str(exc_info.value)

        # Test negative total tokens
        with pytest.raises(ValidationError) as exc_info:
            TokenUsage(prompt_tokens=0, completion_tokens=0, total_tokens=-5)
        assert "greater than or equal to 0" in str(exc_info.value)

    def test_token_usage_serialization(self) -> None:
        """Test TokenUsage JSON serialization/deserialization."""
        usage = TokenUsage(prompt_tokens=250, completion_tokens=150, total_tokens=400)

        # Serialize to JSON
        json_data = usage.model_dump_json()
        assert isinstance(json_data, str)

        # Deserialize back
        data_dict = json.loads(json_data)
        reconstructed = TokenUsage.model_validate(data_dict)

        assert reconstructed.prompt_tokens == usage.prompt_tokens
        assert reconstructed.completion_tokens == usage.completion_tokens
        assert reconstructed.total_tokens == usage.total_tokens


class TestLLMComparisonResultV1:
    """Test suite for LLMComparisonResultV1 model validation."""

    def test_success_case_creation(self) -> None:
        """Test creating a successful comparison result."""
        correlation_id = uuid4()
        requested_at = datetime.now(UTC)
        completed_at = datetime.now(UTC)

        result = LLMComparisonResultV1(
            request_id="req_123",
            correlation_id=correlation_id,
            winner=EssayComparisonWinner.ESSAY_A,
            justification="Essay A demonstrates superior argument structure",
            confidence=4.5,
            error_detail=None,
            provider=LLMProviderType.ANTHROPIC,
            model="claude-3-opus-20240229",
            response_time_ms=1500,
            token_usage=TokenUsage(prompt_tokens=1000, completion_tokens=200, total_tokens=1200),
            cost_estimate=0.025,
            requested_at=requested_at,
            completed_at=completed_at,
            trace_id=None,
        )

        assert result.request_id == "req_123"
        assert result.correlation_id == correlation_id
        assert result.winner == EssayComparisonWinner.ESSAY_A
        assert result.justification == "Essay A demonstrates superior argument structure"
        assert result.confidence == 4.5
        assert result.provider == LLMProviderType.ANTHROPIC
        assert result.model == "claude-3-opus-20240229"
        assert result.response_time_ms == 1500
        assert result.cost_estimate == 0.025
        assert result.is_success is True
        assert result.is_error is False
        assert result.error_detail is None

    def test_error_case_creation(self) -> None:
        """Test creating an error comparison result."""
        correlation_id = uuid4()
        timestamp = datetime.now(UTC)

        error_detail = ErrorDetail(
            error_code=ErrorCode.LLM_PROVIDER_SERVICE_ERROR,
            message="Claude API rate limit exceeded",
            correlation_id=correlation_id,
            timestamp=timestamp,
            service="llm_provider_service",
            operation="compare_essays",
            details={"provider": "anthropic", "error_type": "rate_limit"},
        )

        result = LLMComparisonResultV1(
            request_id="req_error_123",
            correlation_id=correlation_id,
            winner=None,
            justification=None,
            confidence=None,
            error_detail=error_detail,
            provider=LLMProviderType.ANTHROPIC,
            model="claude-3-opus-20240229",
            response_time_ms=300,
            token_usage=TokenUsage(),  # Empty usage for error
            cost_estimate=0.0,
            requested_at=timestamp,
            completed_at=timestamp,
            trace_id=None,
        )

        assert result.request_id == "req_error_123"
        assert result.error_detail == error_detail
        assert result.winner is None
        assert result.justification is None
        assert result.confidence is None
        assert result.is_success is False
        assert result.is_error is True

    def test_mutual_exclusion_validation(self) -> None:
        """Test that success and error fields are mutually exclusive."""
        correlation_id = uuid4()
        timestamp = datetime.now(UTC)

        # Test having both success and error fields
        with pytest.raises(ValidationError) as exc_info:
            LLMComparisonResultV1(
                request_id="req_invalid",
                correlation_id=correlation_id,
                winner=EssayComparisonWinner.ESSAY_A,
                justification="Some justification",
                confidence=3.0,
                error_detail=ErrorDetail(
                    error_code=ErrorCode.LLM_PROVIDER_SERVICE_ERROR,
                    message="Error",
                    correlation_id=correlation_id,
                    timestamp=timestamp,
                    service="llm_provider_service",
                    operation="compare",
                ),
                provider=LLMProviderType.OPENAI,
                model="gpt-4",
                response_time_ms=100,
                token_usage=TokenUsage(),
                cost_estimate=0.01,
                requested_at=timestamp,
                completed_at=timestamp,
                trace_id=None,
            )
        assert "Cannot have both success fields and error_detail" in str(exc_info.value)

    def test_missing_fields_validation(self) -> None:
        """Test that either success or error fields must be provided."""
        correlation_id = uuid4()
        timestamp = datetime.now(UTC)

        # Test having neither success nor error fields
        with pytest.raises(ValidationError) as exc_info:
            LLMComparisonResultV1(
                request_id="req_invalid",
                correlation_id=correlation_id,
                winner=None,
                justification=None,
                confidence=None,
                error_detail=None,
                provider=LLMProviderType.OPENAI,
                model="gpt-4",
                response_time_ms=100,
                token_usage=TokenUsage(),
                cost_estimate=0.0,
                requested_at=timestamp,
                completed_at=timestamp,
                trace_id=None,
            )
        assert "Must have either success fields or error_detail" in str(exc_info.value)

    def test_incomplete_success_fields_validation(self) -> None:
        """Test that all success fields must be provided together."""
        correlation_id = uuid4()
        timestamp = datetime.now(UTC)

        # Test having winner but missing justification
        with pytest.raises(ValidationError) as exc_info:
            LLMComparisonResultV1(
                request_id="req_incomplete",
                correlation_id=correlation_id,
                winner=EssayComparisonWinner.ESSAY_B,
                justification=None,  # Missing - should cause validation error
                confidence=None,  # Missing - should cause validation error
                error_detail=None,
                provider=LLMProviderType.GOOGLE,
                model="gemini-pro",
                response_time_ms=800,
                token_usage=TokenUsage(),
                cost_estimate=0.005,
                requested_at=timestamp,
                completed_at=timestamp,
                trace_id=None,
            )
        assert "All success fields (winner, justification, confidence) must be set together" in str(
            exc_info.value
        )

    def test_confidence_score_range_validation(self) -> None:
        """Test confidence score must be between 1 and 5."""
        correlation_id = uuid4()
        timestamp = datetime.now(UTC)

        # Common parameters for confidence tests
        request_id = "req_confidence"
        winner = EssayComparisonWinner.ESSAY_A
        justification = "Valid justification"
        provider = LLMProviderType.OPENAI
        model = "gpt-4"
        response_time_ms = 1000
        token_usage = TokenUsage()
        cost_estimate = 0.01

        # Test confidence below 1
        with pytest.raises(ValidationError) as exc_info:
            LLMComparisonResultV1(
                request_id=request_id,
                correlation_id=correlation_id,
                winner=winner,
                justification=justification,
                confidence=0.5,
                error_detail=None,
                provider=provider,
                model=model,
                response_time_ms=response_time_ms,
                token_usage=token_usage,
                cost_estimate=cost_estimate,
                requested_at=timestamp,
                completed_at=timestamp,
                trace_id=None,
            )
        assert "greater than or equal to 1" in str(exc_info.value)

        # Test confidence above 5
        with pytest.raises(ValidationError) as exc_info:
            LLMComparisonResultV1(
                request_id=request_id,
                correlation_id=correlation_id,
                winner=winner,
                justification=justification,
                confidence=5.5,
                error_detail=None,
                provider=provider,
                model=model,
                response_time_ms=response_time_ms,
                token_usage=token_usage,
                cost_estimate=cost_estimate,
                requested_at=timestamp,
                completed_at=timestamp,
                trace_id=None,
            )
        assert "less than or equal to 5" in str(exc_info.value)

        # Test valid confidence values
        for confidence in [1.0, 2.5, 3.0, 4.0, 5.0]:
            result = LLMComparisonResultV1(
                request_id=request_id,
                correlation_id=correlation_id,
                winner=winner,
                justification=justification,
                confidence=confidence,
                error_detail=None,
                provider=provider,
                model=model,
                response_time_ms=response_time_ms,
                token_usage=token_usage,
                cost_estimate=cost_estimate,
                requested_at=timestamp,
                completed_at=timestamp,
                trace_id=None,
            )
            assert result.confidence == confidence

    def test_serialization_deserialization_success(self) -> None:
        """Test JSON roundtrip for successful comparison."""
        correlation_id = uuid4()
        requested_at = datetime.now(UTC)
        completed_at = datetime.now(UTC)

        original = LLMComparisonResultV1(
            request_id="req_serialize",
            correlation_id=correlation_id,
            winner=EssayComparisonWinner.ESSAY_B,
            justification="Essay B shows better critical thinking",
            confidence=3.8,
            error_detail=None,
            provider=LLMProviderType.OPENROUTER,
            model="claude-3-sonnet",
            response_time_ms=2000,
            token_usage=TokenUsage(prompt_tokens=1500, completion_tokens=300, total_tokens=1800),
            cost_estimate=0.035,
            requested_at=requested_at,
            completed_at=completed_at,
            trace_id="trace_123",
            request_metadata={"user_id": "teacher_456", "batch_id": "batch_789"},
        )

        # Serialize to JSON
        json_data = original.model_dump_json()

        # Deserialize back
        data_dict = json.loads(json_data)
        reconstructed = LLMComparisonResultV1.model_validate(data_dict)

        assert reconstructed.request_id == original.request_id
        assert reconstructed.correlation_id == original.correlation_id
        assert reconstructed.winner == original.winner
        assert reconstructed.justification == original.justification
        assert reconstructed.confidence == original.confidence
        assert reconstructed.provider == original.provider
        assert reconstructed.model == original.model
        assert reconstructed.trace_id == original.trace_id
        assert reconstructed.request_metadata == original.request_metadata

    def test_serialization_deserialization_error(self) -> None:
        """Test JSON roundtrip for error comparison."""
        correlation_id = uuid4()
        timestamp = datetime.now(UTC)

        error_detail = ErrorDetail(
            error_code=ErrorCode.TIMEOUT,
            message="Request timed out after 30 seconds",
            correlation_id=correlation_id,
            timestamp=timestamp,
            service="llm_provider_service",
            operation="compare_essays",
            details={"timeout_seconds": 30, "provider": "openai"},
        )

        original = LLMComparisonResultV1(
            request_id="req_error_serialize",
            correlation_id=correlation_id,
            winner=None,
            justification=None,
            confidence=None,
            error_detail=error_detail,
            provider=LLMProviderType.OPENAI,
            model="gpt-4-turbo",
            response_time_ms=30000,
            token_usage=TokenUsage(),
            cost_estimate=0.0,
            requested_at=timestamp,
            completed_at=timestamp,
            trace_id=None,
        )

        # Serialize to JSON
        json_data = original.model_dump_json()

        # Deserialize back
        data_dict = json.loads(json_data)
        reconstructed = LLMComparisonResultV1.model_validate(data_dict)

        assert reconstructed.error_detail is not None
        assert reconstructed.error_detail.error_code == ErrorCode.TIMEOUT
        assert reconstructed.error_detail.message == error_detail.message
        assert reconstructed.is_error is True

    def test_real_world_scenario_rate_limit(self) -> None:
        """Test real-world rate limit error scenario."""
        correlation_id = uuid4()
        timestamp = datetime.now(UTC)

        error_detail = ErrorDetail(
            error_code=ErrorCode.RATE_LIMIT,
            message="Rate limit exceeded: 429 Too Many Requests",
            correlation_id=correlation_id,
            timestamp=timestamp,
            service="llm_provider_service",
            operation="compare_essays",
            details={
                "provider": "anthropic",
                "rate_limit_reset": "2024-01-14T12:30:00Z",
                "retry_after": 60,
                "usage": {"requests_per_minute": 100, "limit": 100},
            },
        )

        result = LLMComparisonResultV1(
            request_id="req_rate_limit",
            correlation_id=correlation_id,
            winner=None,
            justification=None,
            confidence=None,
            error_detail=error_detail,
            provider=LLMProviderType.ANTHROPIC,
            model="claude-3-opus-20240229",
            response_time_ms=150,  # Quick fail
            token_usage=TokenUsage(),
            cost_estimate=0.0,
            requested_at=timestamp,
            completed_at=timestamp,
            trace_id=None,
        )

        assert result.is_error is True
        assert result.error_detail is not None
        assert result.error_detail.error_code == ErrorCode.RATE_LIMIT
        assert "retry_after" in result.error_detail.details

    def test_real_world_scenario_successful_comparison(self) -> None:
        """Test real-world successful essay comparison scenario."""
        correlation_id = uuid4()
        requested_at = datetime.now(UTC)
        completed_at = datetime.now(UTC)

        result = LLMComparisonResultV1(
            request_id="cj_batch_123_pair_456",
            correlation_id=correlation_id,
            winner=EssayComparisonWinner.ESSAY_A,
            justification=(
                "Essay A demonstrates stronger analytical thinking with well-supported "
                "arguments and clearer structure"
            ),
            confidence=4.2,
            error_detail=None,
            provider=LLMProviderType.ANTHROPIC,
            model="claude-3-opus-20240229",
            response_time_ms=3500,
            token_usage=TokenUsage(
                prompt_tokens=2500,  # Large prompt with both essays
                completion_tokens=150,  # Concise response
                total_tokens=2650,
            ),
            cost_estimate=0.0465,  # Realistic cost for Claude Opus
            requested_at=requested_at,
            completed_at=completed_at,
            trace_id="batch_123_trace",
            request_metadata={
                "batch_id": "batch_123",
                "pair_id": "pair_456",
                "user_id": "teacher_789",
                "course_code": "ENG7",
            },
        )

        assert result.is_success is True
        assert result.winner == EssayComparisonWinner.ESSAY_A
        assert result.justification is not None
        assert len(result.justification) <= 500  # Max length constraint
        assert result.token_usage.prompt_tokens > result.token_usage.completion_tokens
        assert result.cost_estimate > 0


class TestLLMProviderEventExports:
    """Test that all events are properly exported."""

    def test_all_events_imported(self) -> None:
        """Test that all event classes can be imported."""
        # These should all be importable
        assert LLMRequestStartedV1 is not None
        assert LLMRequestCompletedV1 is not None
        assert LLMProviderFailureV1 is not None
        assert LLMUsageAnalyticsV1 is not None
        assert LLMCostAlertV1 is not None
        assert LLMCostTrackingV1 is not None
        assert LLMComparisonResultV1 is not None
        assert TokenUsage is not None

    def test_event_creation_basic(self) -> None:
        """Test basic creation of various event types."""
        # LLMRequestStartedV1
        start_event = LLMRequestStartedV1(
            provider=LLMProviderType.OPENAI,
            request_type="comparison",
            correlation_id=uuid4(),
            user_id="user_123",
            metadata={"batch_id": "batch_456"},
        )
        assert start_event.provider == LLMProviderType.OPENAI
        assert start_event.request_type == "comparison"

        # LLMProviderFailureV1
        failure_event = LLMProviderFailureV1(
            provider=LLMProviderType.GOOGLE,
            failure_type="timeout",
            correlation_id=uuid4(),
            error_details="Request timed out after 30s",
            circuit_breaker_opened=True,
        )
        assert failure_event.failure_type == "timeout"
        assert failure_event.circuit_breaker_opened is True

        # LLMCostAlertV1
        cost_alert = LLMCostAlertV1(
            alert_type="daily_limit",
            provider=LLMProviderType.ANTHROPIC,
            current_cost=150.0,
            threshold=100.0,
            period="2024-01-14",
        )
        assert cost_alert.current_cost > cost_alert.threshold
        assert cost_alert.alert_type == "daily_limit"

    def test_cost_tracking_event(self) -> None:
        """Test LLMCostTrackingV1 for billing purposes."""
        timestamp = datetime.now(UTC)

        cost_event = LLMCostTrackingV1(
            correlation_id=uuid4(),
            provider=LLMProviderType.OPENAI,
            model="gpt-4-turbo",
            request_type="comparison",
            cost_estimate_usd=0.025,
            token_usage={"prompt_tokens": 1000, "completion_tokens": 200, "total_tokens": 1200},
            user_id="teacher_123",
            organization_id="school_456",
            service_name="cj_assessment_service",
            request_timestamp=timestamp,
            response_time_ms=2500,
            metadata={"batch_id": "batch_789", "pair_count": 50},
        )

        assert cost_event.cost_estimate_usd == 0.025
        assert cost_event.token_usage["total_tokens"] == 1200
        assert cost_event.service_name == "cj_assessment_service"

    def test_usage_analytics_event(self) -> None:
        """Test LLMUsageAnalyticsV1 for periodic analytics."""
        period_start = datetime.now(UTC)
        period_end = datetime.now(UTC)

        analytics = LLMUsageAnalyticsV1(
            period_start=period_start,
            period_end=period_end,
            provider_stats={
                "anthropic": {
                    "requests": 1000,
                    "successful": 950,
                    "failed": 50,
                    "avg_response_time_ms": 2500,
                },
                "openai": {
                    "requests": 500,
                    "successful": 480,
                    "failed": 20,
                    "avg_response_time_ms": 1800,
                },
            },
            total_requests=1500,
            successful_requests=1430,
            failed_requests=70,
            total_tokens={"prompt_tokens": 1500000, "completion_tokens": 300000},
            total_cost=125.50,
            average_response_time_ms=2200.0,
        )

        assert analytics.total_requests == 1500
        assert analytics.successful_requests == 1430
        assert analytics.total_cost == 125.50
        assert len(analytics.provider_stats) == 2

    def test_field_validation_edge_cases(self) -> None:
        """Test edge cases for field validation."""
        correlation_id = uuid4()
        timestamp = datetime.now(UTC)

        # Common parameters for edge case tests
        request_id = "req_edge"
        winner = EssayComparisonWinner.ESSAY_B
        confidence = 3.0
        provider = LLMProviderType.MOCK
        model = "mock-model"
        response_time_ms = 100
        token_usage = TokenUsage()
        cost_estimate = 0.0

        # Test justification at max length (500 chars)
        max_justification = "x" * 500
        result = LLMComparisonResultV1(
            request_id=request_id,
            correlation_id=correlation_id,
            winner=winner,
            justification=max_justification,
            confidence=confidence,
            error_detail=None,
            provider=provider,
            model=model,
            response_time_ms=response_time_ms,
            token_usage=token_usage,
            cost_estimate=cost_estimate,
            requested_at=timestamp,
            completed_at=timestamp,
            trace_id=None,
        )
        assert result.justification is not None
        assert len(result.justification) == 500

        # Test justification over max length
        with pytest.raises(ValidationError) as exc_info:
            LLMComparisonResultV1(
                request_id=request_id,
                correlation_id=correlation_id,
                winner=winner,
                justification="x" * 501,
                confidence=confidence,
                error_detail=None,
                provider=provider,
                model=model,
                response_time_ms=response_time_ms,
                token_usage=token_usage,
                cost_estimate=cost_estimate,
                requested_at=timestamp,
                completed_at=timestamp,
                trace_id=None,
            )
        assert "at most 500 characters" in str(exc_info.value).lower()

        # Test non-negative constraints
        with pytest.raises(ValidationError):
            LLMComparisonResultV1(
                request_id="req_negative_time",
                correlation_id=correlation_id,
                winner=EssayComparisonWinner.ESSAY_B,
                justification="valid",
                confidence=3.0,
                error_detail=None,
                provider=LLMProviderType.MOCK,
                model="mock-model",
                response_time_ms=-1,
                token_usage=TokenUsage(),
                cost_estimate=0.0,
                requested_at=timestamp,
                completed_at=timestamp,
                trace_id=None,
            )

        with pytest.raises(ValidationError):
            LLMComparisonResultV1(
                request_id="req_negative_cost",
                correlation_id=correlation_id,
                winner=EssayComparisonWinner.ESSAY_B,
                justification="valid",
                confidence=3.0,
                error_detail=None,
                provider=LLMProviderType.MOCK,
                model="mock-model",
                response_time_ms=100,
                token_usage=TokenUsage(),
                cost_estimate=-0.01,
                requested_at=timestamp,
                completed_at=timestamp,
                trace_id=None,
            )
