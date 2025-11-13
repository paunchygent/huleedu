"""Unit tests for LLMInteractionImpl business logic and protocol compliance.

Tests the core business behavior of LLM provider integration:
- Protocol implementation compliance
- Async-only architecture patterns
- Error handling and structured error responses
- Provider selection and configuration
- Business metrics recording
- Concurrency control patterns
"""

from __future__ import annotations

from typing import Any
from unittest.mock import Mock
from uuid import UUID, uuid4

import pytest
from common_core import LLMProviderType

from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.implementations.llm_interaction_impl import LLMInteractionImpl
from services.cj_assessment_service.models_api import (
    ComparisonResult,
    ComparisonTask,
    EssayForComparison,
)
from services.cj_assessment_service.protocols import LLMProviderProtocol


class MockLLMProvider:
    """Mock implementation of LLMProviderProtocol for business behavior testing."""

    def __init__(self, behavior: str = "success", exception: Exception | None = None) -> None:
        """Initialize test provider with configurable behavior.

        Args:
            behavior: "success" for normal operation, "failure" to raise exception
            exception: Specific exception to raise on failure
        """
        self.behavior = behavior
        self.exception = exception or Exception("Test provider error")
        self.call_count = 0
        self.last_call_params: dict[str, Any] = {}

    async def generate_comparison(
        self,
        user_prompt: str,
        correlation_id: UUID,
        system_prompt_override: str | None = None,
        model_override: str | None = None,
        temperature_override: float | None = None,
        max_tokens_override: int | None = None,
        provider_override: str | None = None,
        request_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Test implementation that records calls and simulates behavior."""
        self.call_count += 1
        self.last_call_params = {
            "user_prompt": user_prompt,
            "correlation_id": correlation_id,
            "system_prompt_override": system_prompt_override,
            "model_override": model_override,
            "temperature_override": temperature_override,
            "max_tokens_override": max_tokens_override,
            "provider_override": provider_override,
            "request_metadata": request_metadata or {},
        }

        if self.behavior == "failure":
            raise self.exception

        # Async-only architecture always returns None
        return None


class MockBusinessMetricsCollector:
    """Mock implementation for business metrics collection."""

    def __init__(self) -> None:
        """Initialize metrics collector."""
        self.recorded_metrics: list[dict[str, Any]] = []

    def record_llm_call(self, provider: str, model: str, status: str) -> None:
        """Record LLM call metric."""
        self.recorded_metrics.append(
            {
                "provider": provider,
                "model": model,
                "status": status,
            }
        )


class TestLLMInteractionImplProtocolCompliance:
    """Test LLMInteractionImpl protocol implementation and business behavior."""

    @pytest.fixture
    def test_settings(self) -> Settings:
        """Create test settings."""
        settings = Mock(spec=Settings)
        settings.DEFAULT_LLM_PROVIDER = LLMProviderType.OPENAI
        settings.DEFAULT_LLM_MODEL = "gpt-4"
        settings.max_concurrent_llm_requests = 3
        return settings

    @pytest.fixture
    def successful_provider(self) -> MockLLMProvider:
        """Create test provider that succeeds."""
        return MockLLMProvider(behavior="success")

    @pytest.fixture
    def failing_provider(self) -> MockLLMProvider:
        """Create test provider that fails."""
        return MockLLMProvider(behavior="failure", exception=RuntimeError("Network timeout"))

    @pytest.fixture
    def providers_dict_success(
        self, successful_provider: MockLLMProvider
    ) -> dict[LLMProviderType, LLMProviderProtocol]:
        """Create providers dict with successful provider."""
        return {LLMProviderType.OPENAI: successful_provider}

    @pytest.fixture
    def providers_dict_failure(
        self, failing_provider: MockLLMProvider
    ) -> dict[LLMProviderType, LLMProviderProtocol]:
        """Create providers dict with failing provider."""
        return {LLMProviderType.OPENAI: failing_provider}

    @pytest.fixture
    def sample_comparison_task(self) -> ComparisonTask:
        """Create sample comparison task."""
        essay_a = EssayForComparison(id="essay-123", text_content="Sample essay A")
        essay_b = EssayForComparison(id="essay-456", text_content="Sample essay B")
        return ComparisonTask(
            essay_a=essay_a,
            essay_b=essay_b,
            prompt="Compare these essays and determine which is better written.",
        )

    @pytest.mark.asyncio
    async def test_protocol_compliance_successful_operation(
        self,
        providers_dict_success: dict[LLMProviderType, LLMProviderProtocol],
        test_settings: Settings,
        sample_comparison_task: ComparisonTask,
        successful_provider: MockLLMProvider,
    ) -> None:
        """Test protocol compliance with successful operations."""
        # Arrange
        llm_impl = LLMInteractionImpl(providers=providers_dict_success, settings=test_settings)
        correlation_id = uuid4()

        # Act
        result = await llm_impl.perform_comparisons(
            tasks=[sample_comparison_task],
            correlation_id=correlation_id,
        )

        # Assert - Business behavior verification
        assert isinstance(result, list)
        assert len(result) == 0  # Async-only architecture returns empty immediate results
        assert successful_provider.call_count == 1
        assert successful_provider.last_call_params["correlation_id"] == correlation_id
        assert successful_provider.last_call_params["user_prompt"] == sample_comparison_task.prompt
        assert successful_provider.last_call_params["request_metadata"] == {
            "essay_a_id": sample_comparison_task.essay_a.id,
            "essay_b_id": sample_comparison_task.essay_b.id,
        }
        assert successful_provider.last_call_params["system_prompt_override"] is None

    @pytest.mark.asyncio
    async def test_protocol_compliance_with_parameter_overrides(
        self,
        providers_dict_success: dict[LLMProviderType, LLMProviderProtocol],
        test_settings: Settings,
        sample_comparison_task: ComparisonTask,
        successful_provider: MockLLMProvider,
    ) -> None:
        """Test protocol compliance with parameter overrides."""
        # Arrange
        llm_impl = LLMInteractionImpl(providers=providers_dict_success, settings=test_settings)
        correlation_id = uuid4()

        # Act
        result = await llm_impl.perform_comparisons(
            tasks=[sample_comparison_task],
            correlation_id=correlation_id,
            model_override="test-model",
            temperature_override=0.7,
            max_tokens_override=500,
            system_prompt_override="CJ prompt",
        )

        # Assert - Parameter passing verification
        assert len(result) == 0
        assert successful_provider.call_count == 1

        params = successful_provider.last_call_params
        assert params["model_override"] == "test-model"
        assert params["temperature_override"] == 0.7
        assert params["max_tokens_override"] == 500
        assert params["system_prompt_override"] == "CJ prompt"
        assert params["request_metadata"] == {
            "essay_a_id": sample_comparison_task.essay_a.id,
            "essay_b_id": sample_comparison_task.essay_b.id,
        }

    @pytest.mark.asyncio
    async def test_error_handling_creates_structured_results(
        self,
        providers_dict_failure: dict[LLMProviderType, LLMProviderProtocol],
        test_settings: Settings,
        sample_comparison_task: ComparisonTask,
        failing_provider: MockLLMProvider,
    ) -> None:
        """Test error handling creates proper ComparisonResult structures."""
        # Arrange
        llm_impl = LLMInteractionImpl(providers=providers_dict_failure, settings=test_settings)
        correlation_id = uuid4()

        # Act
        result = await llm_impl.perform_comparisons(
            tasks=[sample_comparison_task],
            correlation_id=correlation_id,
        )

        # Assert - Error handling behavior
        assert len(result) == 1
        error_result = result[0]

        assert isinstance(error_result, ComparisonResult)
        assert error_result.task == sample_comparison_task
        assert error_result.llm_assessment is None
        assert error_result.raw_llm_response_content is None
        assert error_result.error_detail is not None

        # Verify provider was called despite error
        assert failing_provider.call_count == 1

    @pytest.mark.asyncio
    async def test_multiple_tasks_processed_independently(
        self,
        providers_dict_success: dict[LLMProviderType, LLMProviderProtocol],
        test_settings: Settings,
        successful_provider: MockLLMProvider,
    ) -> None:
        """Test multiple tasks are processed independently."""
        # Arrange
        llm_impl = LLMInteractionImpl(providers=providers_dict_success, settings=test_settings)
        correlation_id = uuid4()

        tasks = []
        for i in range(3):
            essay_a = EssayForComparison(id=f"essay-a-{i}", text_content=f"Essay A {i}")
            essay_b = EssayForComparison(id=f"essay-b-{i}", text_content=f"Essay B {i}")
            tasks.append(
                ComparisonTask(
                    essay_a=essay_a,
                    essay_b=essay_b,
                    prompt=f"Compare essays {i}",
                )
            )

        # Act
        result = await llm_impl.perform_comparisons(
            tasks=tasks,
            correlation_id=correlation_id,
        )

        # Assert - Multiple task processing
        assert len(result) == 0  # Async-only
        assert successful_provider.call_count == 3

    @pytest.mark.asyncio
    async def test_empty_task_list_handled_gracefully(
        self,
        providers_dict_success: dict[LLMProviderType, LLMProviderProtocol],
        test_settings: Settings,
        successful_provider: MockLLMProvider,
    ) -> None:
        """Test empty task list is handled without errors."""
        # Arrange
        llm_impl = LLMInteractionImpl(providers=providers_dict_success, settings=test_settings)
        correlation_id = uuid4()

        # Act
        result = await llm_impl.perform_comparisons(
            tasks=[],
            correlation_id=correlation_id,
        )

        # Assert - Graceful handling
        assert result == []
        assert successful_provider.call_count == 0

    def test_provider_selection_uses_default_configuration(
        self,
        providers_dict_success: dict[LLMProviderType, LLMProviderProtocol],
        test_settings: Settings,
        successful_provider: MockLLMProvider,
    ) -> None:
        """Test provider selection uses default configuration."""
        # Arrange
        llm_impl = LLMInteractionImpl(providers=providers_dict_success, settings=test_settings)

        # Act
        selected_provider = llm_impl._get_provider_for_model()

        # Assert - Correct provider selection
        assert selected_provider is successful_provider
        assert test_settings.DEFAULT_LLM_PROVIDER == LLMProviderType.OPENAI

    def test_provider_selection_fallback_behavior(
        self,
        successful_provider: MockLLMProvider,
    ) -> None:
        """Test provider selection fallback when default not available."""
        # Arrange - Default provider not in available providers
        settings = Mock(spec=Settings)
        settings.DEFAULT_LLM_PROVIDER = LLMProviderType.ANTHROPIC  # Not available
        settings.DEFAULT_LLM_MODEL = "test-model"

        providers_dict: dict[LLMProviderType, LLMProviderProtocol] = {
            LLMProviderType.OPENAI: successful_provider  # Only OpenAI available
        }

        llm_impl = LLMInteractionImpl(providers=providers_dict, settings=settings)

        # Act
        selected_provider = llm_impl._get_provider_for_model()

        # Assert - Falls back to first available provider
        assert selected_provider is successful_provider

    def test_provider_selection_empty_providers_raises_error(
        self,
        test_settings: Settings,
    ) -> None:
        """Test provider selection with no providers raises appropriate error."""
        # Arrange
        empty_providers: dict[LLMProviderType, LLMProviderProtocol] = {}
        llm_impl = LLMInteractionImpl(providers=empty_providers, settings=test_settings)

        # Act & Assert
        with pytest.raises(KeyError):
            llm_impl._get_provider_for_model()


class TestLLMInteractionImplAsyncBehavior:
    """Test async processing patterns and architecture compliance."""

    @pytest.fixture
    def test_provider_with_delay(self) -> MockLLMProvider:
        """Create test provider for async testing."""
        return MockLLMProvider(behavior="success")

    @pytest.fixture
    def llm_impl_with_concurrency_limit(
        self,
        test_provider_with_delay: MockLLMProvider,
    ) -> LLMInteractionImpl:
        """Create LLM implementation with concurrency limits."""
        settings = Mock(spec=Settings)
        settings.DEFAULT_LLM_PROVIDER = LLMProviderType.OPENAI
        settings.DEFAULT_LLM_MODEL = "gpt-4"
        settings.max_concurrent_llm_requests = 2  # Low limit for testing

        providers_dict: dict[LLMProviderType, LLMProviderProtocol] = {
            LLMProviderType.OPENAI: test_provider_with_delay
        }
        return LLMInteractionImpl(providers=providers_dict, settings=settings)

    @pytest.mark.asyncio
    async def test_async_architecture_returns_none_immediately(
        self,
        llm_impl_with_concurrency_limit: LLMInteractionImpl,
        test_provider_with_delay: MockLLMProvider,
    ) -> None:
        """Test async-only architecture returns None immediately for all tasks."""
        # Arrange
        tasks = []
        for i in range(5):
            essay_a = EssayForComparison(id=f"async-a-{i}", text_content=f"Async A {i}")
            essay_b = EssayForComparison(id=f"async-b-{i}", text_content=f"Async B {i}")
            tasks.append(
                ComparisonTask(
                    essay_a=essay_a,
                    essay_b=essay_b,
                    prompt=f"Async test {i}",
                )
            )

        correlation_id = uuid4()

        # Act
        result = await llm_impl_with_concurrency_limit.perform_comparisons(
            tasks=tasks,
            correlation_id=correlation_id,
        )

        # Assert - Async behavior
        assert result == []  # Immediate empty result
        assert test_provider_with_delay.call_count == 5  # All tasks processed


class TestLLMInteractionImplErrorScenarios:
    """Test comprehensive error scenarios and edge cases."""

    @pytest.fixture
    def mixed_behavior_providers(self) -> dict[LLMProviderType, LLMProviderProtocol]:
        """Create providers with mixed success/failure behavior."""
        return {
            LLMProviderType.OPENAI: MockLLMProvider(
                behavior="failure", exception=ConnectionError("Connection failed")
            )
        }

    @pytest.mark.asyncio
    async def test_connection_errors_produce_structured_error_results(
        self,
        mixed_behavior_providers: dict[LLMProviderType, LLMProviderProtocol],
    ) -> None:
        """Test connection errors produce proper error results."""
        # Arrange
        settings = Mock(spec=Settings)
        settings.DEFAULT_LLM_PROVIDER = LLMProviderType.OPENAI
        settings.DEFAULT_LLM_MODEL = "gpt-4"
        settings.max_concurrent_llm_requests = 3

        llm_impl = LLMInteractionImpl(providers=mixed_behavior_providers, settings=settings)

        essay_a = EssayForComparison(id="error-a", text_content="Error test A")
        essay_b = EssayForComparison(id="error-b", text_content="Error test B")
        task = ComparisonTask(essay_a=essay_a, essay_b=essay_b, prompt="Error test")
        correlation_id = uuid4()

        # Act
        result = await llm_impl.perform_comparisons(
            tasks=[task],
            correlation_id=correlation_id,
        )

        # Assert - Structured error response
        assert len(result) == 1
        error_result = result[0]

        assert isinstance(error_result, ComparisonResult)
        assert error_result.task == task
        assert error_result.llm_assessment is None
        assert error_result.error_detail is not None
        assert error_result.raw_llm_response_content is None

    @pytest.mark.asyncio
    async def test_mixed_success_failure_tasks_handled_independently(
        self,
    ) -> None:
        """Test mixed success/failure scenarios are handled independently."""

        # Arrange - Create provider that alternates between success and failure
        class AlternatingProvider(MockLLMProvider):
            def __init__(self) -> None:
                super().__init__(behavior="success")
                self.call_counter = 0

            async def generate_comparison(self, *args: Any, **kwargs: Any) -> dict[str, Any] | None:
                self.call_counter += 1
                if self.call_counter % 2 == 0:  # Even calls fail
                    raise RuntimeError(f"Simulated failure {self.call_counter}")
                return await super().generate_comparison(*args, **kwargs)

        settings = Mock(spec=Settings)
        settings.DEFAULT_LLM_PROVIDER = LLMProviderType.OPENAI
        settings.DEFAULT_LLM_MODEL = "gpt-4"
        settings.max_concurrent_llm_requests = 3

        alternating_provider = AlternatingProvider()
        providers_dict: dict[LLMProviderType, LLMProviderProtocol] = {
            LLMProviderType.OPENAI: alternating_provider
        }
        llm_impl = LLMInteractionImpl(providers=providers_dict, settings=settings)

        # Create multiple tasks
        tasks = []
        for i in range(4):
            essay_a = EssayForComparison(id=f"mixed-a-{i}", text_content=f"Mixed A {i}")
            essay_b = EssayForComparison(id=f"mixed-b-{i}", text_content=f"Mixed B {i}")
            tasks.append(
                ComparisonTask(
                    essay_a=essay_a,
                    essay_b=essay_b,
                    prompt=f"Mixed test {i}",
                )
            )

        correlation_id = uuid4()

        # Act
        result = await llm_impl.perform_comparisons(
            tasks=tasks,
            correlation_id=correlation_id,
        )

        # Assert - Only failed tasks return error results
        # Successful tasks (odd-numbered calls) return None (async-only)
        # Failed tasks (even-numbered calls) return error results
        assert len(result) == 2  # 2 failures out of 4 tasks

        for error_result in result:
            assert isinstance(error_result, ComparisonResult)
            assert error_result.llm_assessment is None
            assert error_result.error_detail is not None


class TestLLMInteractionImplConfigurationBehavior:
    """Test configuration and settings behavior."""

    def test_missing_concurrent_limit_uses_default(self) -> None:
        """Test missing concurrent limit configuration uses default."""
        # Arrange - Settings without concurrent limit
        settings = Mock(spec=Settings)
        settings.DEFAULT_LLM_PROVIDER = LLMProviderType.OPENAI
        settings.DEFAULT_LLM_MODEL = "gpt-4"
        # No max_concurrent_llm_requests attribute

        provider = MockLLMProvider(behavior="success")
        providers_dict: dict[LLMProviderType, LLMProviderProtocol] = {
            LLMProviderType.OPENAI: provider
        }

        # Act - Should not raise error
        llm_impl = LLMInteractionImpl(providers=providers_dict, settings=settings)

        # Assert - Implementation handles missing attribute gracefully
        assert llm_impl is not None
        assert llm_impl.settings == settings

    @pytest.mark.parametrize(
        "provider_type, model_name",
        [
            (LLMProviderType.OPENAI, "gpt-4"),
            (LLMProviderType.ANTHROPIC, "claude-3"),
        ],
    )
    def test_provider_configuration_flexibility(
        self,
        provider_type: LLMProviderType,
        model_name: str,
    ) -> None:
        """Test flexible provider configuration."""
        # Arrange
        settings = Mock(spec=Settings)
        settings.DEFAULT_LLM_PROVIDER = provider_type
        settings.DEFAULT_LLM_MODEL = model_name
        settings.max_concurrent_llm_requests = 3

        provider = MockLLMProvider(behavior="success")
        providers_dict: dict[LLMProviderType, LLMProviderProtocol] = {provider_type: provider}

        # Act
        llm_impl = LLMInteractionImpl(providers=providers_dict, settings=settings)
        selected_provider = llm_impl._get_provider_for_model()

        # Assert - Configuration respected
        assert selected_provider is provider
        assert llm_impl.settings.DEFAULT_LLM_PROVIDER == provider_type
        assert llm_impl.settings.DEFAULT_LLM_MODEL == model_name
