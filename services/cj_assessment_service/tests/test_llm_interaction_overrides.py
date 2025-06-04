"""
Unit tests for LLMInteractionImpl override parameter handling.

These tests verify that the LLM interaction layer correctly propagates
override parameters to providers and includes them in cache key generation.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from ..implementations.llm_interaction_impl import LLMInteractionImpl
from ..models_api import (
    ComparisonResult,
    ComparisonTask,
    EssayForComparison,
)
from ..protocols import CacheProtocol, LLMProviderProtocol


class TestLLMInteractionImplOverrides:
    """Test LLMInteractionImpl override parameter handling."""

    @pytest.fixture
    def mock_cache_manager(self) -> AsyncMock:
        """Create mock cache manager."""
        cache = AsyncMock(spec=CacheProtocol)
        cache.generate_hash = MagicMock(return_value="test_cache_key")
        cache.get_from_cache = MagicMock(return_value=None)  # No cache hit
        cache.add_to_cache = MagicMock()
        return cache

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
        self, mock_cache_manager: AsyncMock, mock_provider: AsyncMock, mock_settings: MagicMock
    ) -> LLMInteractionImpl:
        """Create LLMInteractionImpl instance for testing."""
        providers = {"openai": mock_provider}
        return LLMInteractionImpl(
            cache_manager=mock_cache_manager,
            providers=providers,
            settings=mock_settings,
        )

    @pytest.fixture
    def sample_comparison_task(
        self, sample_essay_id: str, sample_essay_text: str
    ) -> ComparisonTask:
        """Create sample comparison task."""
        essay_a = EssayForComparison(
            id=sample_essay_id, text_content=sample_essay_text, current_bt_score=0.0
        )
        essay_b = EssayForComparison(
            id="essay_b_id", text_content="Another essay text for comparison.", current_bt_score=0.0
        )

        return ComparisonTask(
            essay_a=essay_a,
            essay_b=essay_b,
            prompt="Compare these two essays and determine which is better.",
        )

    @pytest.mark.asyncio
    async def test_perform_comparisons_with_all_overrides(
        self,
        llm_interaction_impl: LLMInteractionImpl,
        sample_comparison_task: ComparisonTask,
        mock_provider: AsyncMock,
        mock_cache_manager: AsyncMock,
    ) -> None:
        """Test perform_comparisons with all override parameters."""
        # Act
        results = await llm_interaction_impl.perform_comparisons(
            tasks=[sample_comparison_task],
            model_override="gpt-4o",
            temperature_override=0.3,
            max_tokens_override=2000,
        )

        # Assert
        assert len(results) == 1
        result = results[0]
        assert isinstance(result, ComparisonResult)
        assert result.llm_assessment is not None
        assert result.llm_assessment.winner == "Essay A"
        assert result.from_cache is False

        # Verify provider was called with override parameters
        mock_provider.generate_comparison.assert_called_once_with(
            user_prompt=sample_comparison_task.prompt,
            system_prompt_override=None,
            model_override="gpt-4o",
            temperature_override=0.3,
            max_tokens_override=2000,
        )

        # Verify cache key generation includes override parameters
        expected_cache_key_input = (
            f"{sample_comparison_task.prompt}|model:gpt-4o|temp:0.3|tokens:2000"
        )
        mock_cache_manager.generate_hash.assert_called_with(expected_cache_key_input)

    @pytest.mark.asyncio
    async def test_perform_comparisons_with_partial_overrides(
        self,
        llm_interaction_impl: LLMInteractionImpl,
        sample_comparison_task: ComparisonTask,
        mock_provider: AsyncMock,
        mock_cache_manager: AsyncMock,
    ) -> None:
        """Test perform_comparisons with partial override parameters."""
        # Act
        results = await llm_interaction_impl.perform_comparisons(
            tasks=[sample_comparison_task],
            model_override="claude-3-sonnet-20240229",
            # temperature_override and max_tokens_override not provided
        )

        # Assert
        assert len(results) == 1

        # Verify provider was called with only model override
        mock_provider.generate_comparison.assert_called_once_with(
            user_prompt=sample_comparison_task.prompt,
            system_prompt_override=None,
            model_override="claude-3-sonnet-20240229",
            temperature_override=None,
            max_tokens_override=None,
        )

        # Verify cache key generation includes only provided overrides
        expected_cache_key_input = (
            f"{sample_comparison_task.prompt}|model:claude-3-sonnet-20240229|temp:None|tokens:None"
        )
        mock_cache_manager.generate_hash.assert_called_with(expected_cache_key_input)

    @pytest.mark.asyncio
    async def test_perform_comparisons_no_overrides(
        self,
        llm_interaction_impl: LLMInteractionImpl,
        sample_comparison_task: ComparisonTask,
        mock_provider: AsyncMock,
        mock_cache_manager: AsyncMock,
    ) -> None:
        """Test perform_comparisons without override parameters."""
        # Act
        results = await llm_interaction_impl.perform_comparisons(
            tasks=[sample_comparison_task],
        )

        # Assert
        assert len(results) == 1

        # Verify provider was called without overrides
        mock_provider.generate_comparison.assert_called_once_with(
            user_prompt=sample_comparison_task.prompt,
            system_prompt_override=None,
            model_override=None,
            temperature_override=None,
            max_tokens_override=None,
        )

        # Verify cache key generation includes None values
        expected_cache_key_input = (
            f"{sample_comparison_task.prompt}|model:None|temp:None|tokens:None"
        )
        mock_cache_manager.generate_hash.assert_called_with(expected_cache_key_input)

    @pytest.mark.asyncio
    async def test_perform_comparisons_cache_hit_with_overrides(
        self,
        llm_interaction_impl: LLMInteractionImpl,
        sample_comparison_task: ComparisonTask,
        mock_provider: AsyncMock,
        mock_cache_manager: AsyncMock,
    ) -> None:
        """Test cache hit scenario with override parameters."""
        # Arrange - Set up cache hit
        cached_response = {
            "winner": "Essay B",
            "justification": "Cached response with overrides",
            "confidence": 5,
        }
        mock_cache_manager.get_from_cache = MagicMock(return_value=cached_response)

        # Act
        results = await llm_interaction_impl.perform_comparisons(
            tasks=[sample_comparison_task],
            model_override="gpt-4o",
            temperature_override=0.5,
            max_tokens_override=1500,
        )

        # Assert
        assert len(results) == 1
        result = results[0]
        assert result.from_cache is True
        assert result.llm_assessment is not None
        assert result.llm_assessment.winner == "Essay B"

        # Verify provider was NOT called due to cache hit
        mock_provider.generate_comparison.assert_not_called()

        # Verify cache was checked with correct key including overrides
        expected_cache_key_input = (
            f"{sample_comparison_task.prompt}|model:gpt-4o|temp:0.5|tokens:1500"
        )
        mock_cache_manager.generate_hash.assert_called_with(expected_cache_key_input)

    @pytest.mark.asyncio
    async def test_perform_comparisons_multiple_tasks_with_overrides(
        self,
        llm_interaction_impl: LLMInteractionImpl,
        sample_comparison_task: ComparisonTask,
        mock_provider: AsyncMock,
        mock_cache_manager: AsyncMock,
    ) -> None:
        """Test perform_comparisons with multiple tasks and overrides."""
        # Arrange - Create second task
        essay_c = EssayForComparison(
            id="essay_c_id", text_content="Third essay for comparison.", current_bt_score=0.0
        )
        essay_d = EssayForComparison(
            id="essay_d_id", text_content="Fourth essay for comparison.", current_bt_score=0.0
        )

        second_task = ComparisonTask(
            essay_a=essay_c, essay_b=essay_d, prompt="Compare these other two essays."
        )

        tasks = [sample_comparison_task, second_task]

        # Act
        results = await llm_interaction_impl.perform_comparisons(
            tasks=tasks,
            model_override="claude-3-haiku-20240307",
            temperature_override=0.7,
            max_tokens_override=3000,
        )

        # Assert
        assert len(results) == 2

        # Verify provider was called twice with same overrides
        assert mock_provider.generate_comparison.call_count == 2

        # Check both calls had the same override parameters
        for call in mock_provider.generate_comparison.call_args_list:
            args, kwargs = call
            assert kwargs["model_override"] == "claude-3-haiku-20240307"
            assert kwargs["temperature_override"] == 0.7
            assert kwargs["max_tokens_override"] == 3000

        # Verify cache key generation was called for both tasks
        assert mock_cache_manager.generate_hash.call_count == 2

    @pytest.mark.asyncio
    async def test_perform_comparisons_provider_error_with_overrides(
        self,
        llm_interaction_impl: LLMInteractionImpl,
        sample_comparison_task: ComparisonTask,
        mock_provider: AsyncMock,
        mock_cache_manager: AsyncMock,
    ) -> None:
        """Test error handling when provider fails with overrides."""
        # Arrange - Set up provider error
        mock_provider.generate_comparison = AsyncMock(
            return_value=(None, "API rate limit exceeded")
        )

        # Act
        results = await llm_interaction_impl.perform_comparisons(
            tasks=[sample_comparison_task],
            model_override="gpt-4o",
            temperature_override=0.2,
            max_tokens_override=4000,
        )

        # Assert
        assert len(results) == 1
        result = results[0]
        assert result.llm_assessment is None
        assert result.error_message == "API rate limit exceeded"
        assert result.from_cache is False

        # Verify provider was still called with overrides
        mock_provider.generate_comparison.assert_called_once_with(
            user_prompt=sample_comparison_task.prompt,
            system_prompt_override=None,
            model_override="gpt-4o",
            temperature_override=0.2,
            max_tokens_override=4000,
        )

        # Verify cache was NOT updated due to error
        mock_cache_manager.add_to_cache.assert_not_called()
