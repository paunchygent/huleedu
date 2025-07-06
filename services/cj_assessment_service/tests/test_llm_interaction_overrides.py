"""
Unit tests for LLMInteractionImpl override parameter handling.

These tests verify that the LLM interaction layer correctly propagates
override parameters to providers.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from common_core import LLMProviderType

from services.cj_assessment_service.implementations.llm_interaction_impl import LLMInteractionImpl
from services.cj_assessment_service.models_api import (
    ComparisonResult,
    ComparisonTask,
    EssayForComparison,
)
from services.cj_assessment_service.protocols import LLMProviderProtocol


class TestLLMInteractionImplOverrides:
    """Test LLMInteractionImpl override parameter handling."""

    @pytest.fixture
    def mock_provider(self) -> AsyncMock:
        """Create mock LLM provider."""
        provider = AsyncMock(spec=LLMProviderProtocol)

        # Mock successful response - correct format for LLMAssessmentResponseSchema
        mock_response = {
            "winner": "Essay A",
            "justification": "Essay A demonstrates better structure and clarity.",
            "confidence": 4,  # 1-5 scale
        }
        provider.generate_comparison = AsyncMock(return_value=(mock_response, None))
        return provider

    @pytest.fixture
    def llm_interaction_impl(
        self,
        mock_provider: AsyncMock,
        mock_settings: MagicMock,
    ) -> LLMInteractionImpl:
        """Create LLMInteractionImpl instance for testing."""
        from typing import cast

        from services.cj_assessment_service.protocols import LLMProviderProtocol

        providers = cast(
            dict[LLMProviderType, LLMProviderProtocol], {LLMProviderType.OPENAI: mock_provider}
        )
        return LLMInteractionImpl(
            providers=providers,
            settings=mock_settings,
        )

    @pytest.fixture
    def sample_comparison_task(
        self,
    ) -> ComparisonTask:
        """Create sample comparison task."""
        essay_a = EssayForComparison(
            id="essay_1",
            text_content="This is essay A content.",
            current_bt_score=None,
        )
        essay_b = EssayForComparison(
            id="essay_2", 
            text_content="This is essay B content.",
            current_bt_score=None,
        )

        return ComparisonTask(
            essay_a=essay_a,
            essay_b=essay_b,
            prompt="Compare these essays and determine which is better.",
        )

    @pytest.fixture
    def mock_settings(self) -> MagicMock:
        """Create mock settings."""
        settings = MagicMock()
        settings.DEFAULT_LLM_PROVIDER = LLMProviderType.OPENAI
        settings.DEFAULT_LLM_MODEL = "gpt-4"
        settings.max_concurrent_llm_requests = 3
        return settings

    async def test_perform_comparisons_with_model_override(
        self,
        llm_interaction_impl: LLMInteractionImpl,
        sample_comparison_task: ComparisonTask,
        mock_provider: AsyncMock,
    ) -> None:
        """Test that model override is propagated to provider."""
        model_override = "gpt-4-turbo"

        results = await llm_interaction_impl.perform_comparisons(
            tasks=[sample_comparison_task],
            model_override=model_override,
        )

        # Verify provider was called with override
        mock_provider.generate_comparison.assert_called_once()
        call_kwargs = mock_provider.generate_comparison.call_args.kwargs
        assert call_kwargs["model_override"] == model_override

        # Verify result structure (no cache fields)
        assert len(results) == 1
        result = results[0]
        assert isinstance(result, ComparisonResult)
        assert result.task == sample_comparison_task
        assert result.llm_assessment is not None
        assert result.llm_assessment.confidence == 4  # 1-5 scale preserved
        assert result.error_message is None

    async def test_perform_comparisons_with_temperature_override(
        self,
        llm_interaction_impl: LLMInteractionImpl,
        sample_comparison_task: ComparisonTask,
        mock_provider: AsyncMock,
    ) -> None:
        """Test that temperature override is propagated to provider."""
        temperature_override = 0.8

        results = await llm_interaction_impl.perform_comparisons(
            tasks=[sample_comparison_task],
            temperature_override=temperature_override,
        )

        # Verify provider was called with override
        mock_provider.generate_comparison.assert_called_once()
        call_kwargs = mock_provider.generate_comparison.call_args.kwargs
        assert call_kwargs["temperature_override"] == temperature_override

        # Verify result
        assert len(results) == 1
        assert results[0].llm_assessment is not None

    async def test_perform_comparisons_with_max_tokens_override(
        self,
        llm_interaction_impl: LLMInteractionImpl,
        sample_comparison_task: ComparisonTask,
        mock_provider: AsyncMock,
    ) -> None:
        """Test that max_tokens override is propagated to provider."""
        max_tokens_override = 2000

        results = await llm_interaction_impl.perform_comparisons(
            tasks=[sample_comparison_task],
            max_tokens_override=max_tokens_override,
        )

        # Verify provider was called with override
        mock_provider.generate_comparison.assert_called_once()
        call_kwargs = mock_provider.generate_comparison.call_args.kwargs
        assert call_kwargs["max_tokens_override"] == max_tokens_override

        # Verify result
        assert len(results) == 1
        assert results[0].llm_assessment is not None

    async def test_perform_comparisons_handles_provider_errors(
        self,
        llm_interaction_impl: LLMInteractionImpl,
        sample_comparison_task: ComparisonTask,
        mock_provider: AsyncMock,
    ) -> None:
        """Test error handling when provider fails."""
        # Mock provider error
        mock_provider.generate_comparison = AsyncMock(return_value=(None, "Provider error"))

        results = await llm_interaction_impl.perform_comparisons(
            tasks=[sample_comparison_task],
        )

        # Verify error is handled properly
        assert len(results) == 1
        result = results[0]
        assert result.llm_assessment is None
        assert result.error_message == "Provider error"

    async def test_perform_comparisons_with_multiple_tasks(
        self,
        llm_interaction_impl: LLMInteractionImpl,
        mock_provider: AsyncMock,
    ) -> None:
        """Test processing multiple comparison tasks."""
        # Create multiple tasks
        tasks = []
        for i in range(3):
            essay_a = EssayForComparison(id=f"essay_{i}a", text_content=f"Essay {i}A content")
            essay_b = EssayForComparison(id=f"essay_{i}b", text_content=f"Essay {i}B content")
            task = ComparisonTask(
                essay_a=essay_a,
                essay_b=essay_b,
                prompt=f"Compare essays {i}",
            )
            tasks.append(task)

        results = await llm_interaction_impl.perform_comparisons(tasks=tasks)

        # Verify all tasks processed
        assert len(results) == 3
        assert mock_provider.generate_comparison.call_count == 3
        
        # Verify all results successful
        for result in results:
            assert result.llm_assessment is not None
            assert result.error_message is None
