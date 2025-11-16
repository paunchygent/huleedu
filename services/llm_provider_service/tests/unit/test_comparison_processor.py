"""Unit tests for ComparisonProcessorImpl - domain logic testing without infrastructure."""

from __future__ import annotations

import time
from typing import Dict
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from common_core import EssayComparisonWinner, LLMProviderType
from huleedu_service_libs.error_handling import HuleEduError

from services.llm_provider_service.implementations.comparison_processor_impl import (
    ComparisonProcessorImpl,
)
from services.llm_provider_service.internal_models import (
    BatchComparisonItem,
    LLMOrchestratorResponse,
    LLMProviderResponse,
)
from services.llm_provider_service.protocols import LLMProviderProtocol
from services.llm_provider_service.tests.fixtures.fake_event_publisher import FakeEventPublisher
from services.llm_provider_service.tests.fixtures.test_settings import (
    TestSettings,
)


@pytest.fixture
def fake_event_publisher() -> FakeEventPublisher:
    """Fake event publisher for recording events."""
    return FakeEventPublisher()


@pytest.fixture
def mock_provider() -> AsyncMock:
    """Mock LLM provider using AsyncMock with spec."""
    return AsyncMock(spec=LLMProviderProtocol)


@pytest.fixture
def providers_dict(mock_provider: AsyncMock) -> Dict[LLMProviderType, LLMProviderProtocol]:
    """Dictionary of mock providers."""
    return {
        LLMProviderType.MOCK: mock_provider,
        LLMProviderType.OPENAI: mock_provider,
        LLMProviderType.ANTHROPIC: mock_provider,
        LLMProviderType.GOOGLE: mock_provider,
        LLMProviderType.OPENROUTER: mock_provider,
    }


@pytest.fixture
def comparison_processor(
    providers_dict: Dict[LLMProviderType, LLMProviderProtocol],
    fake_event_publisher: FakeEventPublisher,
    unit_test_settings: TestSettings,
) -> ComparisonProcessorImpl:
    """ComparisonProcessorImpl instance with test dependencies."""
    return ComparisonProcessorImpl(
        providers=providers_dict,
        event_publisher=fake_event_publisher,
        settings=unit_test_settings,
    )


@pytest.fixture
def sample_provider_response() -> LLMProviderResponse:
    """Sample provider response for testing."""
    return LLMProviderResponse(
        winner=EssayComparisonWinner.ESSAY_A,
        justification="Essay A demonstrates superior argumentation and clearer structure.",
        confidence=0.85,
        provider=LLMProviderType.MOCK,
        model="mock-model-v1",
        prompt_tokens=150,
        completion_tokens=75,
        total_tokens=225,
        raw_response={},
    )


class TestSuccessfulComparison:
    """Test successful comparison processing."""

    @pytest.mark.asyncio
    async def test_successful_comparison_returns_orchestrator_response(
        self,
        comparison_processor: ComparisonProcessorImpl,
        mock_provider: AsyncMock,
        sample_provider_response: LLMProviderResponse,
        fake_event_publisher: FakeEventPublisher,
    ) -> None:
        """Test successful comparison returns proper orchestrator response."""
        # Arrange
        correlation_id = uuid4()
        mock_provider.generate_comparison.return_value = sample_provider_response

        # Act
        time.time()
        result = await comparison_processor.process_comparison(
            provider=LLMProviderType.MOCK,
            user_prompt="""Compare these essays on climate change

**Essay A (ID: test_a):**
Essay A content with detailed analysis of climate data.

**Essay B (ID: test_b):**
Essay B content discussing environmental policies.""",
            correlation_id=correlation_id,
        )
        time.time()

        # Assert - Orchestrator response structure
        assert result.winner == EssayComparisonWinner.ESSAY_A
        assert (
            result.justification
            == "Essay A demonstrates superior argumentation and clearer structure."
        )
        assert result.confidence == 0.85
        assert result.provider == LLMProviderType.MOCK
        assert result.model == "mock-model-v1"
        assert result.correlation_id == correlation_id
        assert result.trace_id is None  # Set by trace manager in integration layer


class TestComparisonBatchInterface:
    """Tests for the default batch comparison adapter."""

    @pytest.mark.asyncio
    async def test_process_comparison_batch_preserves_order(
        self,
        comparison_processor: ComparisonProcessorImpl,
    ) -> None:
        """Ensure batch processing delegates to process_comparison sequentially."""
        responses = [
            LLMOrchestratorResponse(
                winner=EssayComparisonWinner.ESSAY_A,
                justification="Essay A wins",
                confidence=0.8,
                provider=LLMProviderType.OPENAI,
                model="gpt-4o",
                response_time_ms=1200,
                token_usage={"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
                cost_estimate=0.02,
                correlation_id=uuid4(),
            ),
            LLMOrchestratorResponse(
                winner=EssayComparisonWinner.ESSAY_B,
                justification="Essay B wins",
                confidence=0.7,
                provider=LLMProviderType.ANTHROPIC,
                model="claude-3",
                response_time_ms=900,
                token_usage={"prompt_tokens": 90, "completion_tokens": 45, "total_tokens": 135},
                cost_estimate=0.018,
                correlation_id=uuid4(),
            ),
        ]

        comparison_processor.process_comparison = AsyncMock(side_effect=responses)  # type: ignore[method-assign]

        items = [
            BatchComparisonItem(
                provider=LLMProviderType.OPENAI,
                user_prompt="prompt-a",
                correlation_id=responses[0].correlation_id,
                overrides={"model_override": "gpt-4o"},
            ),
            BatchComparisonItem(
                provider=LLMProviderType.ANTHROPIC,
                user_prompt="prompt-b",
                correlation_id=responses[1].correlation_id,
                overrides={"model_override": "claude-3"},
            ),
        ]

        result = await comparison_processor.process_comparison_batch(items)

        assert result == responses
        await_calls = comparison_processor.process_comparison.await_args_list  # type: ignore[attr-defined]
        assert await_calls[0].kwargs == {
            "provider": LLMProviderType.OPENAI,
            "user_prompt": "prompt-a",
            "correlation_id": responses[0].correlation_id,
            "model_override": "gpt-4o",
        }
        assert await_calls[1].kwargs == {
            "provider": LLMProviderType.ANTHROPIC,
            "user_prompt": "prompt-b",
            "correlation_id": responses[1].correlation_id,
            "model_override": "claude-3",
        }

    @pytest.mark.asyncio
    async def test_process_comparison_batch_handles_empty_input(
        self,
        comparison_processor: ComparisonProcessorImpl,
    ) -> None:
        """Ensure empty batches short-circuit."""
        comparison_processor.process_comparison = AsyncMock()  # type: ignore[method-assign]
        result = await comparison_processor.process_comparison_batch([])
        assert result == []
        comparison_processor.process_comparison.assert_not_awaited()  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_successful_comparison_publishes_completion_event(
        self,
        comparison_processor: ComparisonProcessorImpl,
        mock_provider: AsyncMock,
        sample_provider_response: LLMProviderResponse,
        fake_event_publisher: FakeEventPublisher,
    ) -> None:
        """Test successful comparison publishes completion event with correct metadata."""
        # Arrange
        correlation_id = uuid4()
        mock_provider.generate_comparison.return_value = sample_provider_response

        # Act
        await comparison_processor.process_comparison(
            provider=LLMProviderType.MOCK,
            user_prompt="""Compare these essays

**Essay A (ID: test_a):**
Essay A content

**Essay B (ID: test_b):**
Essay B content""",
            correlation_id=correlation_id,
        )

        # Assert - Completion event was published
        completion_event = fake_event_publisher.assert_event_published(
            event_type="llm_request_completed",
            correlation_id=correlation_id,
            provider="mock",
        )

        assert completion_event["success"] is True
        assert completion_event["response_time_ms"] >= 0  # Can be 0 for fast unit tests
        assert completion_event["metadata"]["request_type"] == "comparison"
        assert completion_event["metadata"]["token_usage"] == {
            "prompt_tokens": 150,
            "completion_tokens": 75,
            "total_tokens": 225,
        }
        assert completion_event["metadata"]["cost_estimate"] == 0.0  # Mock provider is free
        assert completion_event["metadata"]["model_used"] == "mock-model-v1"
        assert completion_event["metadata"]["processing_context"] == "domain_processor"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "provider_type,expected_cost",
        [
            (LLMProviderType.ANTHROPIC, 0.001),  # 100 * 0.01 / 1000
            (LLMProviderType.OPENAI, 0.0015),  # 100 * 0.015 / 1000
            (LLMProviderType.GOOGLE, 0.0005),  # 100 * 0.005 / 1000
            (LLMProviderType.OPENROUTER, 0.002),  # 100 * 0.02 / 1000
            (LLMProviderType.MOCK, 0.0),  # Mock is free
        ],
    )
    async def test_cost_estimation_for_different_providers(
        self,
        comparison_processor: ComparisonProcessorImpl,
        mock_provider: AsyncMock,
        fake_event_publisher: FakeEventPublisher,
        provider_type: LLMProviderType,
        expected_cost: float,
    ) -> None:
        """Test cost estimation varies by provider type."""
        # Arrange
        correlation_id = uuid4()
        provider_response = LLMProviderResponse(
            winner=EssayComparisonWinner.ESSAY_B,
            justification="Test justification",
            confidence=0.75,
            provider=provider_type,
            model=f"{provider_type.value}-model",
            prompt_tokens=60,
            completion_tokens=40,
            total_tokens=100,
            raw_response={},
        )
        mock_provider.generate_comparison.return_value = provider_response

        # Act
        result = await comparison_processor.process_comparison(
            provider=provider_type,
            user_prompt="""Compare these essays

**Essay A (ID: test_a):**
Essay A content

**Essay B (ID: test_b):**
Essay B content""",
            correlation_id=correlation_id,
        )

        # Assert
        assert result.cost_estimate == expected_cost


class TestParameterOverrides:
    """Test parameter override functionality."""

    @pytest.mark.asyncio
    async def test_provider_receives_all_overrides(
        self,
        comparison_processor: ComparisonProcessorImpl,
        mock_provider: AsyncMock,
        sample_provider_response: LLMProviderResponse,
    ) -> None:
        """Test provider receives all parameter overrides correctly."""
        # Arrange
        correlation_id = uuid4()
        mock_provider.generate_comparison.return_value = sample_provider_response

        overrides = {
            "system_prompt_override": "Custom system prompt for testing",
            "model_override": "gpt-4-custom",
            "temperature_override": 0.3,
            "max_tokens_override": 500,
        }

        # Act
        await comparison_processor.process_comparison(
            provider=LLMProviderType.OPENAI,
            user_prompt="""Compare these essays

**Essay A (ID: test_a):**
Essay A content

**Essay B (ID: test_b):**
Essay B content""",
            correlation_id=correlation_id,
            **overrides,
        )

        # Assert - Provider was called with all overrides
        mock_provider.generate_comparison.assert_called_once_with(
            user_prompt="""Compare these essays

**Essay A (ID: test_a):**
Essay A content

**Essay B (ID: test_b):**
Essay B content""",
            correlation_id=correlation_id,
            system_prompt_override="Custom system prompt for testing",
            model_override="gpt-4-custom",
            temperature_override=0.3,
            max_tokens_override=500,
        )

    @pytest.mark.asyncio
    async def test_partial_overrides_with_none_values(
        self,
        comparison_processor: ComparisonProcessorImpl,
        mock_provider: AsyncMock,
        sample_provider_response: LLMProviderResponse,
    ) -> None:
        """Test partial overrides pass None for unspecified parameters."""
        # Arrange
        correlation_id = uuid4()
        mock_provider.generate_comparison.return_value = sample_provider_response

        # Act - Only specify temperature override
        await comparison_processor.process_comparison(
            provider=LLMProviderType.ANTHROPIC,
            user_prompt="""Compare these essays

**Essay A (ID: test_a):**
Essay A content

**Essay B (ID: test_b):**
Essay B content""",
            correlation_id=correlation_id,
            temperature_override=0.1,
        )

        # Assert - Unspecified overrides are None
        mock_provider.generate_comparison.assert_called_once_with(
            user_prompt="""Compare these essays

**Essay A (ID: test_a):**
Essay A content

**Essay B (ID: test_b):**
Essay B content""",
            correlation_id=correlation_id,
            system_prompt_override=None,
            model_override=None,
            temperature_override=0.1,
            max_tokens_override=None,
        )


class TestSwedishCharacterHandling:
    """Test proper handling of Swedish characters in essays."""

    @pytest.mark.asyncio
    async def test_swedish_characters_in_essays(
        self,
        comparison_processor: ComparisonProcessorImpl,
        mock_provider: AsyncMock,
        fake_event_publisher: FakeEventPublisher,
    ) -> None:
        """Test essays with Swedish characters are handled correctly."""
        # Arrange
        correlation_id = uuid4()
        justification = (
            "Essä B visar bättre förståelse av ämnet och använder mer precisa svenska uttryck."
        )
        swedish_response = LLMProviderResponse(
            winner=EssayComparisonWinner.ESSAY_B,
            justification=justification,
            confidence=0.92,
            provider=LLMProviderType.OPENAI,
            model="gpt-4",
            prompt_tokens=200,
            completion_tokens=100,
            total_tokens=300,
            raw_response={},
        )
        mock_provider.generate_comparison.return_value = swedish_response

        # Act
        result = await comparison_processor.process_comparison(
            provider=LLMProviderType.OPENAI,
            user_prompt="""Jämför dessa uppsatser på svenska

**Essay A (ID: test_a):**
Uppsats A handlar om klimatförändringen och dess påverkan på miljön.

**Essay B (ID: test_b):**
Uppsats B diskuterar hållbarhet och återvinning i det svenska samhället.""",
            correlation_id=correlation_id,
        )

        # Assert - Swedish characters preserved in response
        assert result.winner == EssayComparisonWinner.ESSAY_B
        assert "bättre förståelse" in result.justification
        assert "svenska uttryck" in result.justification

        # Assert - Provider was called with Swedish content (essays now in user_prompt)
        call_args = mock_provider.generate_comparison.call_args
        assert "klimatförändringen" in call_args[1]["user_prompt"]
        assert "återvinning" in call_args[1]["user_prompt"]
        assert "Jämför" in call_args[1]["user_prompt"]


class TestProviderErrorHandling:
    """Test provider error handling and event publishing."""

    @pytest.mark.asyncio
    async def test_huleedu_error_propagation(
        self,
        comparison_processor: ComparisonProcessorImpl,
        mock_provider: AsyncMock,
        fake_event_publisher: FakeEventPublisher,
    ) -> None:
        """Test HuleEduError from provider is propagated after publishing failure events."""
        # Arrange
        correlation_id = uuid4()
        from huleedu_service_libs.error_handling import raise_external_service_error

        # Create a proper HuleEduError using the error handling utilities
        try:
            raise_external_service_error(
                service="test_service",
                operation="test_operation",
                external_service="openai_provider",
                message="Provider service unavailable",
                correlation_id=uuid4(),
                details={"provider": "openai"},
            )
        except HuleEduError as e:
            provider_error = e
        mock_provider.generate_comparison.side_effect = provider_error

        # Act & Assert - Error is re-raised
        with pytest.raises(HuleEduError) as exc_info:
            await comparison_processor.process_comparison(
                provider=LLMProviderType.OPENAI,
                user_prompt="""Compare these essays

**Essay A (ID: test_a):**
Essay A content

**Essay B (ID: test_b):**
Essay B content""",
                correlation_id=correlation_id,
            )

        assert exc_info.value == provider_error

        # Assert - Failure events were published
        failure_event = fake_event_publisher.assert_event_published(
            event_type="llm_provider_failure",
            correlation_id=correlation_id,
            provider="openai",
        )
        assert failure_event["failure_type"] == "provider_error"
        assert failure_event["error_details"] == "Provider error occurred during processing"
        assert failure_event["circuit_breaker_opened"] is False

        # Assert - Completion event marked as failed
        completion_event = fake_event_publisher.assert_event_published(
            event_type="llm_request_completed",
            correlation_id=correlation_id,
            provider="openai",
        )
        assert completion_event["success"] is False
        assert completion_event["metadata"]["request_type"] == "comparison"
        assert completion_event["metadata"]["failure_type"] == "provider_error"
        assert completion_event["metadata"]["processing_context"] == "domain_processor"

    @pytest.mark.asyncio
    async def test_unexpected_error_handling(
        self,
        comparison_processor: ComparisonProcessorImpl,
        mock_provider: AsyncMock,
        fake_event_publisher: FakeEventPublisher,
    ) -> None:
        """Test unexpected errors are converted to external service errors."""
        # Arrange
        correlation_id = uuid4()
        unexpected_error = ValueError("Unexpected connection timeout")
        mock_provider.generate_comparison.side_effect = unexpected_error

        # Act & Assert - Error is converted to HuleEduError
        with pytest.raises(HuleEduError) as exc_info:
            await comparison_processor.process_comparison(
                provider=LLMProviderType.GOOGLE,
                user_prompt="""Compare these essays

**Essay A (ID: test_a):**
Essay A content

**Essay B (ID: test_b):**
Essay B content""",
                correlation_id=correlation_id,
            )

        # Assert - Error details include provider information
        assert "Unexpected error calling provider google" in str(exc_info.value)

        # Assert - Failure events published with error details
        failure_event = fake_event_publisher.assert_event_published(
            event_type="llm_provider_failure",
            correlation_id=correlation_id,
            provider="google",
        )
        assert "Unexpected error calling provider google" in failure_event["error_details"]

        completion_event = fake_event_publisher.assert_event_published(
            event_type="llm_request_completed",
            correlation_id=correlation_id,
            provider="google",
        )
        assert completion_event["success"] is False

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "provider_type",
        [
            LLMProviderType.OPENAI,
            LLMProviderType.ANTHROPIC,
            LLMProviderType.GOOGLE,
            LLMProviderType.OPENROUTER,
            LLMProviderType.MOCK,
        ],
    )
    async def test_error_handling_for_all_providers(
        self,
        comparison_processor: ComparisonProcessorImpl,
        mock_provider: AsyncMock,
        fake_event_publisher: FakeEventPublisher,
        provider_type: LLMProviderType,
    ) -> None:
        """Test error handling works consistently across all provider types."""
        # Arrange
        correlation_id = uuid4()
        mock_provider.generate_comparison.side_effect = RuntimeError("Provider failure")

        # Act & Assert
        with pytest.raises(HuleEduError):
            await comparison_processor.process_comparison(
                provider=provider_type,
                user_prompt="""Compare these essays

**Essay A (ID: test_a):**
Essay A content

**Essay B (ID: test_b):**
Essay B content""",
                correlation_id=correlation_id,
            )

        # Assert - Events published for the specific provider
        assert fake_event_publisher.has_failure_event(correlation_id)
        failure_event = fake_event_publisher.get_events_by_correlation_id(correlation_id)[0]
        assert failure_event["provider"] == provider_type.value


class TestEventPublishing:
    """Test event publishing verification."""

    @pytest.mark.asyncio
    async def test_success_event_metadata_completeness(
        self,
        comparison_processor: ComparisonProcessorImpl,
        mock_provider: AsyncMock,
        sample_provider_response: LLMProviderResponse,
        fake_event_publisher: FakeEventPublisher,
    ) -> None:
        """Test success event contains all required metadata fields."""
        # Arrange
        correlation_id = uuid4()
        mock_provider.generate_comparison.return_value = sample_provider_response

        # Act
        await comparison_processor.process_comparison(
            provider=LLMProviderType.MOCK,
            user_prompt="""Compare these essays

**Essay A (ID: test_a):**
Essay A content

**Essay B (ID: test_b):**
Essay B content""",
            correlation_id=correlation_id,
        )

        # Assert - Check all metadata fields
        completion_event = fake_event_publisher.get_events_by_type("llm_request_completed")[0]
        metadata = completion_event["metadata"]

        required_fields = [
            "request_type",
            "token_usage",
            "cost_estimate",
            "model_used",
            "processing_context",
        ]

        for field in required_fields:
            assert field in metadata, f"Missing required metadata field: {field}"

        assert metadata["request_type"] == "comparison"
        assert isinstance(metadata["token_usage"], dict)
        assert isinstance(metadata["cost_estimate"], (int, float))
        assert isinstance(metadata["model_used"], str)
        assert metadata["processing_context"] == "domain_processor"

    @pytest.mark.asyncio
    async def test_no_duplicate_events_on_success(
        self,
        comparison_processor: ComparisonProcessorImpl,
        mock_provider: AsyncMock,
        sample_provider_response: LLMProviderResponse,
        fake_event_publisher: FakeEventPublisher,
    ) -> None:
        """Test successful processing publishes exactly one completion event."""
        # Arrange
        correlation_id = uuid4()
        mock_provider.generate_comparison.return_value = sample_provider_response

        # Act
        await comparison_processor.process_comparison(
            provider=LLMProviderType.MOCK,
            user_prompt="""Compare these essays

**Essay A (ID: test_a):**
Essay A content

**Essay B (ID: test_b):**
Essay B content""",
            correlation_id=correlation_id,
        )

        # Assert - Exactly one completion event
        completion_events = fake_event_publisher.get_events_by_type("llm_request_completed")
        assert len(completion_events) == 1

        # Assert - No failure events on success
        failure_events = fake_event_publisher.get_events_by_type("llm_provider_failure")
        assert len(failure_events) == 0

    @pytest.mark.asyncio
    async def test_failure_events_include_circuit_breaker_info(
        self,
        comparison_processor: ComparisonProcessorImpl,
        mock_provider: AsyncMock,
        fake_event_publisher: FakeEventPublisher,
    ) -> None:
        """Test failure events include circuit breaker status (handled at infrastructure layer)."""
        # Arrange
        correlation_id = uuid4()
        mock_provider.generate_comparison.side_effect = RuntimeError("Provider error")

        # Act
        with pytest.raises(HuleEduError):
            await comparison_processor.process_comparison(
                provider=LLMProviderType.OPENAI,
                user_prompt="""Compare these essays

**Essay A (ID: test_a):**
Essay A content

**Essay B (ID: test_b):**
Essay B content""",
                correlation_id=correlation_id,
            )

        # Assert - Circuit breaker status in failure event
        failure_event = fake_event_publisher.assert_event_published(
            event_type="llm_provider_failure",
            correlation_id=correlation_id,
        )
        assert "circuit_breaker_opened" in failure_event
        assert (
            failure_event["circuit_breaker_opened"] is False
        )  # Domain processor doesn't handle circuit breaker


class TestCostEstimation:
    """Test cost estimation logic."""

    @pytest.mark.asyncio
    async def test_cost_estimation_with_zero_tokens(
        self,
        comparison_processor: ComparisonProcessorImpl,
        mock_provider: AsyncMock,
        fake_event_publisher: FakeEventPublisher,
    ) -> None:
        """Test cost estimation handles zero tokens correctly."""
        # Arrange
        correlation_id = uuid4()
        zero_token_response = LLMProviderResponse(
            winner=EssayComparisonWinner.ESSAY_A,
            justification="Brief response",
            confidence=0.5,
            provider=LLMProviderType.OPENAI,
            model="gpt-3.5-turbo",
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
            raw_response={},
        )
        mock_provider.generate_comparison.return_value = zero_token_response

        # Act
        result = await comparison_processor.process_comparison(
            provider=LLMProviderType.OPENAI,
            user_prompt="""Compare these essays

**Essay A (ID: test_a):**
Essay A content

**Essay B (ID: test_b):**
Essay B content""",
            correlation_id=correlation_id,
        )

        # Assert - Zero cost for zero tokens
        assert result.cost_estimate == 0.0
        assert result.token_usage["total_tokens"] == 0

    @pytest.mark.asyncio
    async def test_cost_estimation_for_unknown_provider(
        self,
        comparison_processor: ComparisonProcessorImpl,
    ) -> None:
        """Test cost estimation defaults to 0.01 rate for unknown providers."""
        # Arrange - Test the private method directly
        unknown_provider = "unknown_provider"
        token_usage = {"total_tokens": 1000}

        # Act
        cost = comparison_processor._estimate_cost(unknown_provider, token_usage)

        # Assert - Uses default rate of 0.01
        assert cost == 0.01  # 1000 * 0.01 / 1000

    def test_cost_estimation_direct_calculation(
        self,
        comparison_processor: ComparisonProcessorImpl,
    ) -> None:
        """Test cost estimation calculation logic directly."""
        # Test data for each provider
        test_cases = [
            ("anthropic", {"total_tokens": 2000}, 0.02),  # 2000 * 0.01 / 1000
            ("openai", {"total_tokens": 1500}, 0.0225),  # 1500 * 0.015 / 1000
            ("google", {"total_tokens": 3000}, 0.015),  # 3000 * 0.005 / 1000
            ("openrouter", {"total_tokens": 500}, 0.01),  # 500 * 0.02 / 1000
            ("mock", {"total_tokens": 10000}, 0.0),  # Mock is always free
        ]

        for provider, token_usage, expected_cost in test_cases:
            # Act
            actual_cost = comparison_processor._estimate_cost(provider, token_usage)

            # Assert
            assert actual_cost == expected_cost, (
                f"Cost mismatch for {provider}: expected {expected_cost}, got {actual_cost}"
            )
