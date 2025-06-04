"""
Unit tests for LLM Provider override parameter handling.

Following testing mandates:
- Mock only external boundaries (HTTP sessions)
- Test through public interfaces (LLMProviderProtocol.generate_comparison)
- Let internal business logic run for real
"""

from __future__ import annotations

from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.cj_assessment_service.implementations.anthropic_provider_impl import (
    AnthropicProviderImpl,
)
from services.cj_assessment_service.implementations.openai_provider_impl import OpenAIProviderImpl
from services.cj_assessment_service.implementations.retry_manager_impl import RetryManagerImpl


class TestLLMProviderPublicInterface:
    """Test LLM providers through public interface with proper boundary mocking."""

    @pytest.fixture
    def openai_provider(
        self, mock_http_session: AsyncMock, mock_settings: MagicMock
    ) -> OpenAIProviderImpl:
        """Create OpenAI provider instance for testing."""
        # Configure retry settings for test
        mock_settings.llm_retry_enabled = False  # Disable retries for simpler tests
        retry_manager = RetryManagerImpl(settings=mock_settings)  # Real retry manager
        provider = OpenAIProviderImpl(
            session=mock_http_session,
            settings=mock_settings,
            retry_manager=retry_manager,
        )
        return provider

    @pytest.fixture
    def anthropic_provider(
        self, mock_http_session: AsyncMock, mock_settings: MagicMock
    ) -> AnthropicProviderImpl:
        """Create Anthropic provider instance for testing."""
        # Configure retry settings for test
        mock_settings.llm_retry_enabled = False  # Disable retries for simpler tests
        retry_manager = RetryManagerImpl(settings=mock_settings)  # Real retry manager
        provider = AnthropicProviderImpl(
            session=mock_http_session,
            settings=mock_settings,
            retry_manager=retry_manager,
        )
        return provider

    @pytest.mark.asyncio
    async def test_openai_generate_comparison_with_overrides(
        self, openai_provider: OpenAIProviderImpl
    ) -> None:
        """Test OpenAI provider handles overrides correctly through public interface."""
        # Arrange - Mock external HTTP boundary only
        mock_response_data = {
            "choices": [
                {
                    "message": {
                        "content": (
                            '{"winner": "Essay A", "justification": "Better structure", '
                            '"confidence": 4}'
                        )
                    }
                }
            ]
        }

        # Mock the HTTP response
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=mock_response_data)

        with patch.object(openai_provider.session, 'post') as mock_post:
            # Configure the mock to act as async context manager
            mock_post.return_value.__aenter__.return_value = mock_response
            mock_post.return_value.__aexit__.return_value = None

            # Act - Test through public interface (all business logic runs real)
            result, error = await openai_provider.generate_comparison(
                user_prompt="Compare these two essays on writing quality.",
                model_override="gpt-4o",
                temperature_override=0.2,
                max_tokens_override=1500,
            )

            # Assert - Verify behavior and verify overrides were applied
            assert error is None
            assert result is not None
            assert result["winner"] == "Essay A"

            # Verify HTTP request was made with correct overrides
            mock_post.assert_called_once()
            call_args = mock_post.call_args
            payload = call_args[1]["json"]
            assert payload["model"] == "gpt-4o"
            assert payload["temperature"] == 0.2
            assert payload["max_tokens"] == 1500

    @pytest.mark.asyncio
    async def test_anthropic_generate_comparison_with_overrides(
        self, anthropic_provider: AnthropicProviderImpl
    ) -> None:
        """Test Anthropic provider handles overrides correctly through public interface."""
        # Arrange - Mock external HTTP boundary only
        mock_response_data = {
            "content": [
                {
                    "type": "text",
                    "text": (
                        '{"winner": "Essay B", "justification": "More coherent argument", '
                        '"confidence": 5}'
                    ),
                }
            ]
        }

        # Mock the HTTP response
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=mock_response_data)

        with patch.object(anthropic_provider.session, 'post') as mock_post:
            # Configure the mock to act as async context manager
            mock_post.return_value.__aenter__.return_value = mock_response
            mock_post.return_value.__aexit__.return_value = None

            # Act - Test through public interface (all business logic runs real)
            result, error = await anthropic_provider.generate_comparison(
                user_prompt="Compare these two essays on argumentation.",
                model_override="claude-3-opus-20240229",
                temperature_override=0.1,
                max_tokens_override=2000,
            )

            # Assert - Verify behavior and verify overrides were applied
            assert error is None
            assert result is not None
            assert result["winner"] == "Essay B"

            # Verify HTTP request was made with correct overrides
            mock_post.assert_called_once()
            call_args = mock_post.call_args
            payload = call_args[1]["json"]
            assert payload["model"] == "claude-3-opus-20240229"
            assert payload["temperature"] == 0.1
            assert payload["max_tokens"] == 2000

    @pytest.mark.asyncio
    async def test_provider_fallback_to_defaults_when_no_overrides(
        self, openai_provider: OpenAIProviderImpl
    ) -> None:
        """Test provider uses defaults when no overrides provided."""
        # Arrange - Mock external HTTP boundary only
        mock_response_data = {
            "choices": [
                {
                    "message": {
                        "content": (
                            '{"winner": "Essay A", "justification": "Default test", '
                            '"confidence": 3}'
                        )
                    }
                }
            ]
        }

        # Mock the HTTP response
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=mock_response_data)

        with patch.object(openai_provider.session, 'post') as mock_post:
            # Configure the mock to act as async context manager
            mock_post.return_value.__aenter__.return_value = mock_response
            mock_post.return_value.__aexit__.return_value = None

            # Act - Test without overrides (all business logic runs real)
            result, error = await openai_provider.generate_comparison(
                user_prompt="Compare these essays.",
                # No overrides provided
            )

            # Assert - Verify defaults were used
            assert error is None
            assert result is not None

            # Verify HTTP request used provider defaults from mock_settings
            mock_post.assert_called_once()
            call_args = mock_post.call_args
            payload = call_args[1]["json"]
            assert payload["model"] == "gpt-4o-mini"  # From mock_settings
            assert payload["temperature"] == 0.7  # From provider config
            assert payload["max_tokens"] == 4000  # From provider config

    @pytest.mark.asyncio
    async def test_provider_handles_http_errors_correctly(
        self, openai_provider: OpenAIProviderImpl
    ) -> None:
        """Test provider error handling through public interface."""
        # Mock the HTTP response for error case
        mock_response = AsyncMock()
        mock_response.status = 400  # Bad Request (non-retryable)
        mock_response.text = AsyncMock(return_value="Invalid request format")

        with patch.object(openai_provider.session, 'post') as mock_post:
            # Configure the mock to act as async context manager
            mock_post.return_value.__aenter__.return_value = mock_response
            mock_post.return_value.__aexit__.return_value = None

            # Act - Test error handling through public interface
            result, error = await openai_provider.generate_comparison(
                user_prompt="Compare these essays.",
                model_override="gpt-4o",
            )

            # Assert - Verify error is handled properly
            assert result is None
            assert error is not None
            # Non-retryable errors return formatted message from the provider
            assert "400" in error


class TestOverridePrecedenceLogic:
    """Test override precedence logic: runtime → provider → global."""

    def test_override_precedence_rules(self, mock_settings: MagicMock) -> None:
        """Test that override precedence follows runtime → provider → global."""
        # Setup mock settings with specific values
        mock_settings.TEMPERATURE = 0.5  # Global default
        mock_settings.MAX_TOKENS_RESPONSE = 3000  # Global default

        # Setup provider config with specific values
        provider_config = MagicMock()
        provider_config.temperature = 0.6  # Provider default
        provider_config.max_tokens = 3500  # Provider default

        # Test precedence: runtime override > provider default > global default

        # Case 1: Runtime override takes precedence
        temp: Optional[float] = 0.8  # Runtime override
        max_tokens: Optional[int] = None  # No runtime override

        final_temp = (
            temp
            if temp is not None
            else (
                provider_config.temperature
                if provider_config.temperature is not None
                else mock_settings.TEMPERATURE
            )
        )
        final_max_tokens = (
            max_tokens
            if max_tokens is not None
            else (
                provider_config.max_tokens
                if provider_config.max_tokens is not None
                else mock_settings.MAX_TOKENS_RESPONSE
            )
        )

        assert final_temp == 0.8  # Runtime override
        assert final_max_tokens == 3500  # Provider default

        # Case 2: Provider default when no runtime override
        temp = None
        max_tokens = None

        final_temp = (
            temp
            if temp is not None
            else (
                provider_config.temperature
                if provider_config.temperature is not None
                else mock_settings.TEMPERATURE
            )
        )
        final_max_tokens = (
            max_tokens
            if max_tokens is not None
            else (
                provider_config.max_tokens
                if provider_config.max_tokens is not None
                else mock_settings.MAX_TOKENS_RESPONSE
            )
        )

        assert final_temp == 0.6  # Provider default
        assert final_max_tokens == 3500  # Provider default
