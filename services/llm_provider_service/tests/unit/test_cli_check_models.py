"""Unit tests for CLI model checking tool.

Tests cover:
- CheckerFactory initialization and creation methods
- Provider-specific checker creation with API key validation
- Exit code determination logic
- Async check models orchestration
- CLI command integration
- Error handling and edge cases
"""

from __future__ import annotations

import logging
from unittest.mock import Mock

import pytest
from pydantic import SecretStr

from services.llm_provider_service.cli_check_models import (
    CheckerFactory,
    ExitCode,
    determine_exit_code,
)
from services.llm_provider_service.config import Settings
from services.llm_provider_service.model_checker.base import (
    DiscoveredModel,
    ModelComparisonResult,
)
from services.llm_provider_service.model_manifest import ProviderName


class TestCheckerFactoryInit:
    """Tests for CheckerFactory initialization."""

    def test_init_stores_settings_and_logger(self) -> None:
        """Factory should store settings and logger."""
        mock_settings = Mock(spec=Settings)
        logger = logging.getLogger(__name__)

        factory = CheckerFactory(settings=mock_settings, logger=logger)

        assert factory.settings is mock_settings
        assert factory.logger is logger


class TestCheckerFactoryCreate:
    """Tests for create_checker method."""

    @pytest.mark.asyncio
    async def test_create_anthropic_checker(self, mocker: Mock) -> None:
        """Should create AnthropicModelChecker when API key is present."""
        mock_settings = Mock(spec=Settings)
        mock_settings.ANTHROPIC_API_KEY = SecretStr("test-api-key")
        logger = logging.getLogger(__name__)

        # Mock AsyncAnthropic client creation
        mock_client = Mock()
        mocker.patch(
            "services.llm_provider_service.cli_check_models.AsyncAnthropic",
            return_value=mock_client,
        )

        factory = CheckerFactory(settings=mock_settings, logger=logger)
        checker = await factory.create_checker(ProviderName.ANTHROPIC)

        assert checker is not None
        assert hasattr(checker, "provider")
        assert checker.provider == ProviderName.ANTHROPIC

    @pytest.mark.asyncio
    async def test_create_anthropic_checker_missing_key(self, mocker: Mock) -> None:
        """Should return None when Anthropic API key is missing."""
        mock_settings = Mock(spec=Settings)
        mock_settings.ANTHROPIC_API_KEY = SecretStr("")
        logger = logging.getLogger(__name__)

        # Mock console to suppress warning output
        mock_console = mocker.patch(
            "services.llm_provider_service.cli_check_models.console"
        )

        factory = CheckerFactory(settings=mock_settings, logger=logger)
        checker = await factory.create_checker(ProviderName.ANTHROPIC)

        assert checker is None
        mock_console.print.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_openai_checker(self, mocker: Mock) -> None:
        """Should create OpenAIModelChecker when API key is present."""
        mock_settings = Mock(spec=Settings)
        mock_settings.OPENAI_API_KEY = SecretStr("test-api-key")
        logger = logging.getLogger(__name__)

        # Mock AsyncOpenAI client creation
        mock_client = Mock()
        mocker.patch(
            "services.llm_provider_service.cli_check_models.AsyncOpenAI",
            return_value=mock_client,
        )

        factory = CheckerFactory(settings=mock_settings, logger=logger)
        checker = await factory.create_checker(ProviderName.OPENAI)

        assert checker is not None
        assert hasattr(checker, "provider")
        assert checker.provider == ProviderName.OPENAI

    @pytest.mark.asyncio
    async def test_create_openai_checker_missing_key(self, mocker: Mock) -> None:
        """Should return None when OpenAI API key is missing."""
        mock_settings = Mock(spec=Settings)
        mock_settings.OPENAI_API_KEY = SecretStr("")
        logger = logging.getLogger(__name__)

        # Mock console
        mock_console = mocker.patch(
            "services.llm_provider_service.cli_check_models.console"
        )

        factory = CheckerFactory(settings=mock_settings, logger=logger)
        checker = await factory.create_checker(ProviderName.OPENAI)

        assert checker is None
        mock_console.print.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_google_checker(self, mocker: Mock) -> None:
        """Should create GoogleModelChecker when API key is present."""
        mock_settings = Mock(spec=Settings)
        mock_settings.GOOGLE_API_KEY = SecretStr("test-api-key")
        logger = logging.getLogger(__name__)

        # Mock Google genai client
        mock_genai = Mock()
        mock_genai.Client = Mock(return_value=Mock())
        mocker.patch.dict("sys.modules", {"google.genai": mock_genai})

        factory = CheckerFactory(settings=mock_settings, logger=logger)
        checker = await factory.create_checker(ProviderName.GOOGLE)

        assert checker is not None
        assert hasattr(checker, "provider")
        assert checker.provider == ProviderName.GOOGLE

    @pytest.mark.asyncio
    async def test_create_google_checker_missing_key(self, mocker: Mock) -> None:
        """Should return None when Google API key is missing."""
        mock_settings = Mock(spec=Settings)
        mock_settings.GOOGLE_API_KEY = SecretStr("")
        logger = logging.getLogger(__name__)

        # Mock console
        mock_console = mocker.patch(
            "services.llm_provider_service.cli_check_models.console"
        )

        factory = CheckerFactory(settings=mock_settings, logger=logger)
        checker = await factory.create_checker(ProviderName.GOOGLE)

        assert checker is None
        mock_console.print.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_openrouter_checker(self, mocker: Mock) -> None:
        """Should create OpenRouterModelChecker when API key is present."""
        mock_settings = Mock(spec=Settings)
        mock_settings.OPENROUTER_API_KEY = SecretStr("test-api-key")
        logger = logging.getLogger(__name__)

        # Mock aiohttp ClientSession
        mock_session = Mock()
        mocker.patch(
            "services.llm_provider_service.cli_check_models.aiohttp.ClientSession",
            return_value=mock_session,
        )

        factory = CheckerFactory(settings=mock_settings, logger=logger)
        checker = await factory.create_checker(ProviderName.OPENROUTER)

        assert checker is not None
        assert hasattr(checker, "provider")
        assert checker.provider == ProviderName.OPENROUTER

    @pytest.mark.asyncio
    async def test_create_openrouter_checker_missing_key(self, mocker: Mock) -> None:
        """Should return None when OpenRouter API key is missing."""
        mock_settings = Mock(spec=Settings)
        mock_settings.OPENROUTER_API_KEY = SecretStr("")
        logger = logging.getLogger(__name__)

        # Mock console
        mock_console = mocker.patch(
            "services.llm_provider_service.cli_check_models.console"
        )

        factory = CheckerFactory(settings=mock_settings, logger=logger)
        checker = await factory.create_checker(ProviderName.OPENROUTER)

        assert checker is None
        mock_console.print.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_checker_unsupported_provider(self, mocker: Mock) -> None:
        """Should return None and warn for unsupported providers."""
        mock_settings = Mock(spec=Settings)
        logger = logging.getLogger(__name__)
        mock_logger = mocker.patch.object(logger, "warning")

        factory = CheckerFactory(settings=mock_settings, logger=logger)
        checker = await factory.create_checker(ProviderName.MOCK)

        assert checker is None
        mock_logger.assert_called_once()


class TestDetermineExitCode:
    """Tests for determine_exit_code function."""

    def test_exit_code_up_to_date(self) -> None:
        """Should return UP_TO_DATE when no changes detected."""
        results = [
            ModelComparisonResult(
                provider=ProviderName.ANTHROPIC,
                new_models=[],
                deprecated_models=[],
                updated_models=[],
                breaking_changes=[],
                is_up_to_date=True,
            )
        ]

        exit_code = determine_exit_code(results)

        assert exit_code == ExitCode.UP_TO_DATE

    def test_exit_code_new_models(self) -> None:
        """Should return NEW_MODELS_AVAILABLE when new models present."""
        new_model = DiscoveredModel(
            model_id="new-model",
            display_name="New Model",
        )

        results = [
            ModelComparisonResult(
                provider=ProviderName.ANTHROPIC,
                new_models=[new_model],
                deprecated_models=[],
                updated_models=[],
                breaking_changes=[],
                is_up_to_date=False,
            )
        ]

        exit_code = determine_exit_code(results)

        assert exit_code == ExitCode.NEW_MODELS_AVAILABLE

    def test_exit_code_updated_models(self) -> None:
        """Should return NEW_MODELS_AVAILABLE when models updated."""
        updated_model = DiscoveredModel(
            model_id="updated-model",
            display_name="Updated Model",
        )

        results = [
            ModelComparisonResult(
                provider=ProviderName.ANTHROPIC,
                new_models=[],
                deprecated_models=[],
                updated_models=[("updated-model", updated_model)],
                breaking_changes=[],
                is_up_to_date=False,
            )
        ]

        exit_code = determine_exit_code(results)

        assert exit_code == ExitCode.NEW_MODELS_AVAILABLE

    def test_exit_code_breaking_changes(self) -> None:
        """Should return BREAKING_CHANGES when breaking changes present."""
        results = [
            ModelComparisonResult(
                provider=ProviderName.ANTHROPIC,
                new_models=[],
                deprecated_models=[],
                updated_models=[],
                breaking_changes=["API version changed from v1 to v2"],
                is_up_to_date=False,
            )
        ]

        exit_code = determine_exit_code(results)

        assert exit_code == ExitCode.BREAKING_CHANGES

    def test_exit_code_breaking_changes_priority(self) -> None:
        """Breaking changes should take priority over new models."""
        new_model = DiscoveredModel(
            model_id="new-model",
            display_name="New Model",
        )

        results = [
            ModelComparisonResult(
                provider=ProviderName.ANTHROPIC,
                new_models=[new_model],
                deprecated_models=[],
                updated_models=[],
                breaking_changes=["API version changed"],
                is_up_to_date=False,
            )
        ]

        exit_code = determine_exit_code(results)

        # Breaking changes have highest priority
        assert exit_code == ExitCode.BREAKING_CHANGES

    def test_exit_code_multiple_results(self) -> None:
        """Should aggregate across multiple provider results."""
        results = [
            ModelComparisonResult(
                provider=ProviderName.ANTHROPIC,
                new_models=[],
                deprecated_models=[],
                updated_models=[],
                breaking_changes=[],
                is_up_to_date=True,
            ),
            ModelComparisonResult(
                provider=ProviderName.OPENAI,
                new_models=[
                    DiscoveredModel(model_id="new-model", display_name="New")
                ],
                deprecated_models=[],
                updated_models=[],
                breaking_changes=[],
                is_up_to_date=False,
            ),
        ]

        exit_code = determine_exit_code(results)

        # At least one provider has new models
        assert exit_code == ExitCode.NEW_MODELS_AVAILABLE
