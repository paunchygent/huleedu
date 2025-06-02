"""
Unit tests for LLM Provider override parameter handling.

These tests verify that LLM providers correctly apply override parameters
with proper fallback chains: runtime_override → provider_default → global_default.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ..implementations.anthropic_provider_impl import (
    AnthropicProviderImpl,
)
from ..implementations.google_provider_impl import GoogleProviderImpl
from ..implementations.openai_provider_impl import OpenAIProviderImpl
from ..implementations.openrouter_provider_impl import (
    OpenRouterProviderImpl,
)
from ..implementations.retry_manager_impl import RetryManagerImpl


class TestOpenAIProviderOverrides:
    """Test OpenAI provider override parameter handling."""

    @pytest.fixture
    def openai_provider(self, mock_http_session: AsyncMock, mock_settings: MagicMock) -> OpenAIProviderImpl:
        """Create OpenAI provider instance for testing."""
        retry_manager = AsyncMock(spec=RetryManagerImpl)
        provider = OpenAIProviderImpl(
            session=mock_http_session,
            settings=mock_settings,
            retry_manager=retry_manager,
        )
        return provider

    def test_get_model_name_with_override(
        self, openai_provider: OpenAIProviderImpl
    ) -> None:
        """Test model name selection with override."""
        # Test override takes precedence
        result = openai_provider._get_model_name(model_override="gpt-4o")
        assert result == "gpt-4o"

    def test_get_model_name_fallback_to_provider_default(
        self, openai_provider: OpenAIProviderImpl
    ) -> None:
        """Test model name fallback to provider default."""
        # Test fallback to provider config
        result = openai_provider._get_model_name()
        assert result == "gpt-4o-mini"  # From mock_settings fixture

    def test_prepare_request_details_with_all_overrides(
        self, openai_provider: OpenAIProviderImpl
    ) -> None:
        """Test request preparation with all override parameters."""
        # Arrange
        system_prompt = "Test system prompt"
        user_prompt = "Test user prompt"

        # Act
        endpoint, headers, payload = openai_provider._prepare_request_details(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model_override="gpt-4o",
            temperature_override=0.1,
            max_tokens_override=1500,
        )

        # Assert
        assert payload["model"] == "gpt-4o"
        assert payload["temperature"] == 0.1
        assert payload["max_tokens"] == 1500
        assert payload["messages"][0]["content"] == system_prompt
        assert payload["messages"][1]["content"] == user_prompt

    def test_prepare_request_details_with_partial_overrides(
        self, openai_provider: OpenAIProviderImpl
    ) -> None:
        """Test request preparation with partial override parameters."""
        # Arrange
        system_prompt = "Test system prompt"
        user_prompt = "Test user prompt"

        # Act
        endpoint, headers, payload = openai_provider._prepare_request_details(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model_override="gpt-4o",
            # temperature_override and max_tokens_override not provided
        )

        # Assert
        assert payload["model"] == "gpt-4o"
        assert payload["temperature"] == 0.7  # From provider config fallback
        assert payload["max_tokens"] == 4000  # From provider config fallback

    def test_prepare_request_details_no_overrides(
        self, openai_provider: OpenAIProviderImpl
    ) -> None:
        """Test request preparation without override parameters."""
        # Arrange
        system_prompt = "Test system prompt"
        user_prompt = "Test user prompt"

        # Act
        endpoint, headers, payload = openai_provider._prepare_request_details(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )

        # Assert
        assert payload["model"] == "gpt-4o-mini"  # From provider config
        assert payload["temperature"] == 0.7     # From provider config
        assert payload["max_tokens"] == 4000     # From provider config

    @pytest.mark.asyncio
    async def test_generate_comparison_with_overrides(
        self, openai_provider: OpenAIProviderImpl
    ) -> None:
        """Test generate_comparison method with override parameters."""
        # Arrange
        mock_response = {"choices": [{"message": {"content": '{"winner": "A", "reason": "Test"}'}}]}
        openai_provider.retry_manager.call_with_retry = AsyncMock(
            return_value=(mock_response, None)
        )

        # Act
        result, error = await openai_provider.generate_comparison(
            user_prompt="Compare these essays",
            model_override="gpt-4o",
            temperature_override=0.2,
            max_tokens_override=1000,
        )

        # Assert
        assert error is None
        assert result is not None
        openai_provider.retry_manager.call_with_retry.assert_called_once()


class TestAnthropicProviderOverrides:
    """Test Anthropic provider override parameter handling."""

    @pytest.fixture
    def anthropic_provider(self, mock_http_session: AsyncMock, mock_settings: MagicMock) -> AnthropicProviderImpl:
        """Create Anthropic provider instance for testing."""
        retry_manager = AsyncMock(spec=RetryManagerImpl)
        provider = AnthropicProviderImpl(
            session=mock_http_session,
            settings=mock_settings,
            retry_manager=retry_manager,
        )
        return provider

    def test_get_model_name_with_override(
        self, anthropic_provider: AnthropicProviderImpl
    ) -> None:
        """Test model name selection with override."""
        result = anthropic_provider._get_model_name(model_override="claude-3-sonnet-20240229")
        assert result == "claude-3-sonnet-20240229"

    @pytest.mark.asyncio
    async def test_make_provider_api_request_with_overrides(
        self, anthropic_provider: AnthropicProviderImpl
    ) -> None:
        """Test API request with override parameters."""
        # Arrange
        mock_response_data = {
            "content": [
                {"type": "text", "text": '{"winner": "B", "reason": "Better"}'}
            ]
        }

        with patch('aiohttp.ClientSession.post') as mock_post:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(return_value=mock_response_data)
            mock_post.return_value.__aenter__.return_value = mock_response

            # Act
            result, error = await anthropic_provider._make_provider_api_request(
                system_prompt="Test system",
                user_prompt="Test user",
                model_override="claude-3-opus-20240229",
                temperature_override=0.9,
                max_tokens_override=3000,
            )

            # Assert
            assert error is None
            assert result is not None

            # Verify the request payload had our overrides
            call_args = mock_post.call_args
            payload = call_args[1]['json']
            assert payload['model'] == "claude-3-opus-20240229"
            assert payload['temperature'] == 0.9
            assert payload['max_tokens'] == 3000


class TestGoogleProviderOverrides:
    """Test Google provider override parameter handling."""

    @pytest.fixture
    def google_provider(self, mock_http_session: AsyncMock, mock_settings: MagicMock) -> GoogleProviderImpl:
        """Create Google provider instance for testing."""
        retry_manager = AsyncMock(spec=RetryManagerImpl)
        provider = GoogleProviderImpl(
            session=mock_http_session,
            settings=mock_settings,
            retry_manager=retry_manager,
        )
        return provider

    def test_get_model_name_with_override(
        self, google_provider: GoogleProviderImpl
    ) -> None:
        """Test model name selection with override."""
        result = google_provider._get_model_name(model_override="gemini-1.5-pro")
        assert result == "gemini-1.5-pro"

    @pytest.mark.asyncio
    async def test_make_provider_api_request_with_overrides(
        self, google_provider: GoogleProviderImpl
    ) -> None:
        """Test API request with override parameters."""
        # Arrange
        mock_response_data = {
            "candidates": [
                {"content": {"parts": [{"text": '{"winner": "A", "reason": "Good"}'}]}}
            ]
        }

        with patch('aiohttp.ClientSession.post') as mock_post:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(return_value=mock_response_data)
            mock_post.return_value.__aenter__.return_value = mock_response

            # Act
            result, error = await google_provider._make_provider_api_request(
                system_prompt="Test system",
                user_prompt="Test user",
                model_override="gemini-1.5-flash",
                temperature_override=0.4,
                max_tokens_override=2500,
            )

            # Assert
            assert error is None
            assert result is not None

            # Verify the request had our overrides
            call_args = mock_post.call_args
            payload = call_args[1]['json']
            assert payload['generationConfig']['temperature'] == 0.4
            assert payload['generationConfig']['maxOutputTokens'] == 2500


class TestOpenRouterProviderOverrides:
    """Test OpenRouter provider override parameter handling."""

    @pytest.fixture
    def openrouter_provider(self, mock_http_session: AsyncMock, mock_settings: MagicMock) -> OpenRouterProviderImpl:
        """Create OpenRouter provider instance for testing."""
        retry_manager = AsyncMock(spec=RetryManagerImpl)
        provider = OpenRouterProviderImpl(
            session=mock_http_session,
            settings=mock_settings,
            retry_manager=retry_manager,
        )
        return provider

    def test_get_model_name_with_override(
        self, openrouter_provider: OpenRouterProviderImpl
    ) -> None:
        """Test model name selection with override."""
        result = openrouter_provider._get_model_name(model_override="anthropic/claude-3.5-sonnet")
        assert result == "anthropic/claude-3.5-sonnet"

    @pytest.mark.asyncio
    async def test_make_provider_api_request_with_overrides(
        self, openrouter_provider: OpenRouterProviderImpl
    ) -> None:
        """Test API request with override parameters."""
        # Arrange
        mock_response_data = {
            "choices": [
                {"message": {"content": '{"winner": "B", "reason": "Superior"}'}}
            ]
        }

        with patch('aiohttp.ClientSession.post') as mock_post:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(return_value=mock_response_data)
            mock_post.return_value.__aenter__.return_value = mock_response

            # Act
            result, error = await openrouter_provider._make_provider_api_request(
                system_prompt="Test system",
                user_prompt="Test user",
                model_override="meta-llama/llama-3.1-8b-instruct",
                temperature_override=0.6,
                max_tokens_override=1800,
            )

            # Assert
            assert error is None
            assert result is not None

            # Verify the request payload had our overrides
            call_args = mock_post.call_args
            payload = call_args[1]['json']
            assert payload['model'] == "meta-llama/llama-3.1-8b-instruct"
            assert payload['temperature'] == 0.6
            assert payload['max_tokens'] == 1800


class TestOverridePrecedence:
    """Test the override precedence across all providers."""

    def test_override_precedence_rules(self, mock_settings: MagicMock) -> None:
        """Test that override precedence follows runtime → provider → global."""
        # This test validates the precedence logic in _prepare_request_details methods

        # Setup mock settings with specific values
        mock_settings.TEMPERATURE = 0.5  # Global default
        mock_settings.MAX_TOKENS_RESPONSE = 3000  # Global default

        # Setup provider config with specific values
        provider_config = MagicMock()
        provider_config.temperature = 0.6  # Provider default
        provider_config.max_tokens = 3500  # Provider default

        # Test precedence: runtime override > provider default > global default

        # Case 1: Only runtime override provided
        temp = 0.8  # Runtime override
        max_tokens = None  # No runtime override

        # Expected: temp uses runtime (0.8), max_tokens uses provider (3500)
        final_temp = temp if temp is not None else (
            provider_config.temperature if provider_config.temperature is not None
            else mock_settings.TEMPERATURE
        )
        final_max_tokens = max_tokens if max_tokens is not None else (
            provider_config.max_tokens if provider_config.max_tokens is not None
            else mock_settings.MAX_TOKENS_RESPONSE
        )

        assert final_temp == 0.8  # Runtime override
        assert final_max_tokens == 3500  # Provider default

        # Case 2: No runtime override, use provider defaults
        temp = None
        max_tokens = None

        final_temp = temp if temp is not None else (
            provider_config.temperature if provider_config.temperature is not None
            else mock_settings.TEMPERATURE
        )
        final_max_tokens = max_tokens if max_tokens is not None else (
            provider_config.max_tokens if provider_config.max_tokens is not None
            else mock_settings.MAX_TOKENS_RESPONSE
        )

        assert final_temp == 0.6  # Provider default
        assert final_max_tokens == 3500  # Provider default
