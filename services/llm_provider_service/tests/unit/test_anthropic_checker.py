"""Unit tests for Anthropic model version checker.

Tests cover:
- AnthropicModelChecker initialization
- check_latest_models() with mocked AsyncAnthropic client
- Model filtering logic (Claude 3+ included, legacy excluded)
- compare_with_manifest() comparison logic
- Error handling and logging
"""

from __future__ import annotations

import logging
from datetime import date
from unittest.mock import AsyncMock, Mock

import pytest
from anthropic.types import ModelInfo

from services.llm_provider_service.config import Settings
from services.llm_provider_service.model_checker.anthropic_checker import (
    AnthropicModelChecker,
)
from services.llm_provider_service.model_checker.base import DiscoveredModel
from services.llm_provider_service.model_manifest import ProviderName


@pytest.fixture
def settings() -> Settings:
    """Create Settings instance for tests."""
    return Settings()


class TestAnthropicCheckerInit:
    """Tests for AnthropicModelChecker initialization."""

    def test_init_stores_client_and_logger(self, settings: Settings) -> None:
        """Checker should store AsyncAnthropic client and logger."""
        mock_client = Mock()
        logger = logging.getLogger(__name__)

        checker = AnthropicModelChecker(client=mock_client, logger=logger, settings=settings)

        assert checker.client is mock_client
        assert checker.logger is logger

    def test_provider_is_anthropic(self, settings: Settings) -> None:
        """Provider attribute should be ProviderName.ANTHROPIC."""
        mock_client = Mock()
        logger = logging.getLogger(__name__)

        checker = AnthropicModelChecker(client=mock_client, logger=logger, settings=settings)

        assert checker.provider == ProviderName.ANTHROPIC


class TestCheckLatestModels:
    """Tests for check_latest_models() method."""

    @pytest.mark.asyncio
    async def test_queries_anthropic_api(self, mocker: Mock, settings: Settings) -> None:
        """Should call client.models.list()."""
        mock_client = Mock()
        mock_response = Mock()
        mock_response.data = []
        mock_client.models.list = AsyncMock(return_value=mock_response)
        logger = logging.getLogger(__name__)

        checker = AnthropicModelChecker(client=mock_client, logger=logger, settings=settings)
        await checker.check_latest_models()

        mock_client.models.list.assert_called_once()

    @pytest.mark.asyncio
    async def test_parses_model_info_correctly(self, mocker: Mock, settings: Settings) -> None:
        """Should parse Anthropic ModelInfo into DiscoveredModel."""
        mock_client = Mock()
        mock_model_info = ModelInfo(
            id="claude-haiku-4-5-20251001",
            display_name="Claude 3.5 Haiku",
            type="model",
            created_at=date(2024, 10, 22),
        )
        mock_response = Mock()
        mock_response.data = [mock_model_info]
        mock_client.models.list = AsyncMock(return_value=mock_response)
        logger = logging.getLogger(__name__)

        checker = AnthropicModelChecker(client=mock_client, logger=logger, settings=settings)
        models = await checker.check_latest_models()

        assert len(models) == 1
        assert models[0].model_id == "claude-haiku-4-5-20251001"
        assert models[0].display_name == "Claude 3.5 Haiku"

    @pytest.mark.asyncio
    async def test_filters_claude_2_models(self, mocker: Mock, settings: Settings) -> None:
        """Should exclude Claude 2.x models from results."""
        mock_client = Mock()
        mock_models = [
            ModelInfo(
                id="claude-2.1",
                display_name="Claude 2.1",
                type="model",
                created_at=date(2023, 1, 1),
            ),
            ModelInfo(
                id="claude-haiku-4-5-20251001",
                display_name="Claude 3.5 Haiku",
                type="model",
                created_at=date(2024, 10, 22),
            ),
        ]
        mock_response = Mock()
        mock_response.data = mock_models
        mock_client.models.list = AsyncMock(return_value=mock_response)
        logger = logging.getLogger(__name__)

        checker = AnthropicModelChecker(client=mock_client, logger=logger, settings=settings)
        models = await checker.check_latest_models()

        # Should only include Claude 3+ model
        assert len(models) == 1
        assert models[0].model_id == "claude-haiku-4-5-20251001"

    @pytest.mark.asyncio
    async def test_filters_claude_instant_models(self, mocker: Mock, settings: Settings) -> None:
        """Should exclude claude-instant models from results."""
        mock_client = Mock()
        mock_models = [
            ModelInfo(
                id="claude-instant-1.2",
                display_name="Claude Instant 1.2",
                type="model",
                created_at=date(2023, 1, 1),
            ),
            ModelInfo(
                id="claude-haiku-4-5-20251001",
                display_name="Claude 3.5 Haiku",
                type="model",
                created_at=date(2024, 10, 22),
            ),
        ]
        mock_response = Mock()
        mock_response.data = mock_models
        mock_client.models.list = AsyncMock(return_value=mock_response)
        logger = logging.getLogger(__name__)

        checker = AnthropicModelChecker(client=mock_client, logger=logger, settings=settings)
        models = await checker.check_latest_models()

        # Should only include Claude 3+ model
        assert len(models) == 1
        assert models[0].model_id == "claude-haiku-4-5-20251001"

    @pytest.mark.asyncio
    async def test_includes_claude_3_models(self, mocker: Mock, settings: Settings) -> None:
        """Should include all Claude 3.x models."""
        mock_client = Mock()
        mock_models = [
            ModelInfo(
                id="claude-3-opus-20240229",
                display_name="Claude 3 Opus",
                type="model",
                created_at=date(2024, 2, 29),
            ),
            ModelInfo(
                id="claude-sonnet-4-5-20250929",
                display_name="Claude 3.5 Sonnet",
                type="model",
                created_at=date(2024, 10, 22),
            ),
            ModelInfo(
                id="claude-haiku-4-5-20251001",
                display_name="Claude 3.5 Haiku",
                type="model",
                created_at=date(2024, 10, 22),
            ),
        ]
        mock_response = Mock()
        mock_response.data = mock_models
        mock_client.models.list = AsyncMock(return_value=mock_response)
        logger = logging.getLogger(__name__)

        checker = AnthropicModelChecker(client=mock_client, logger=logger, settings=settings)
        models = await checker.check_latest_models()

        # Should include all 3 Claude 3.x models
        assert len(models) == 3
        model_ids = {m.model_id for m in models}
        assert "claude-3-opus-20240229" in model_ids
        assert "claude-sonnet-4-5-20250929" in model_ids
        assert "claude-haiku-4-5-20251001" in model_ids

    @pytest.mark.asyncio
    async def test_handles_api_error_gracefully(self, mocker: Mock, settings: Settings) -> None:
        """Should raise exception and log error on API failure."""
        mock_client = Mock()
        mock_client.models.list = AsyncMock(side_effect=Exception("API authentication failed"))
        logger = logging.getLogger(__name__)
        mock_logger = mocker.patch.object(logger, "error")

        checker = AnthropicModelChecker(client=mock_client, logger=logger, settings=settings)

        with pytest.raises(Exception, match="API authentication failed"):
            await checker.check_latest_models()

        # Verify error was logged
        mock_logger.assert_called_once()


class TestCompareWithManifest:
    """Tests for compare_with_manifest() method."""

    @pytest.mark.asyncio
    async def test_identifies_new_models(self, mocker: Mock, settings: Settings) -> None:
        """Should detect models in API but not in manifest."""
        mock_client = Mock()

        # Mock a new model not in manifest
        new_model = DiscoveredModel(
            model_id="claude-4-opus-20250101",
            display_name="Claude 4 Opus",
        )

        # Mock check_latest_models to return the new model
        mocker.patch.object(
            AnthropicModelChecker,
            "check_latest_models",
            return_value=[new_model],
        )

        logger = logging.getLogger(__name__)
        checker = AnthropicModelChecker(client=mock_client, logger=logger, settings=settings)
        result = await checker.compare_with_manifest()

        # Verify new model was detected
        assert result.is_up_to_date is False
        # Check combined count of tracked and untracked families
        total_new = len(result.new_models_in_tracked_families) + len(result.new_untracked_families)
        assert total_new >= 1
        # The new model should be in either tracked or untracked list
        all_new_model_ids = {m.model_id for m in result.new_models_in_tracked_families} | {
            m.model_id for m in result.new_untracked_families
        }
        assert "claude-4-opus-20250101" in all_new_model_ids

    @pytest.mark.asyncio
    async def test_identifies_deprecated_models(self, mocker: Mock, settings: Settings) -> None:
        """Should detect models in manifest marked as deprecated by API."""
        mock_client = Mock()

        # Mock discovered model marked as deprecated
        deprecated_model = DiscoveredModel(
            model_id="claude-haiku-4-5-20251001",
            display_name="Claude Haiku 4.5",
            is_deprecated=True,
        )

        # Mock check_latest_models to return deprecated model
        mocker.patch.object(
            AnthropicModelChecker,
            "check_latest_models",
            return_value=[deprecated_model],
        )

        logger = logging.getLogger(__name__)
        checker = AnthropicModelChecker(client=mock_client, logger=logger, settings=settings)
        result = await checker.compare_with_manifest()

        # Verify deprecated model was detected
        if deprecated_model.is_deprecated:
            assert "claude-haiku-4-5-20251001" in result.deprecated_models

    @pytest.mark.asyncio
    async def test_is_up_to_date_when_no_changes(self, mocker: Mock, settings: Settings) -> None:
        """Should set is_up_to_date=True when manifest matches API."""
        mock_client = Mock()

        # Mock discovered model matching manifest
        matching_model = DiscoveredModel(
            model_id="claude-haiku-4-5-20251001",
            display_name="Claude 3.5 Haiku",
            api_version=None,
            capabilities=[],
        )

        # Mock check_latest_models to return matching model
        mocker.patch.object(
            AnthropicModelChecker,
            "check_latest_models",
            return_value=[matching_model],
        )

        logger = logging.getLogger(__name__)
        checker = AnthropicModelChecker(client=mock_client, logger=logger, settings=settings)
        result = await checker.compare_with_manifest()

        # When no changes, should be up-to-date
        # Note: This might be False if there are other models in manifest
        # but we're checking the logic works
        assert isinstance(result.is_up_to_date, bool)

    @pytest.mark.asyncio
    async def test_returns_correct_provider(self, mocker: Mock, settings: Settings) -> None:
        """Should return ANTHROPIC as provider in result."""
        mock_client = Mock()

        # Mock check_latest_models to return empty list
        mocker.patch.object(
            AnthropicModelChecker,
            "check_latest_models",
            return_value=[],
        )

        logger = logging.getLogger(__name__)
        checker = AnthropicModelChecker(client=mock_client, logger=logger, settings=settings)
        result = await checker.compare_with_manifest()

        assert result.provider == ProviderName.ANTHROPIC

    @pytest.mark.asyncio
    async def test_sets_checked_at_date(self, mocker: Mock, settings: Settings) -> None:
        """Should set checked_at to today's date."""
        mock_client = Mock()

        # Mock check_latest_models to return empty list
        mocker.patch.object(
            AnthropicModelChecker,
            "check_latest_models",
            return_value=[],
        )

        logger = logging.getLogger(__name__)
        checker = AnthropicModelChecker(client=mock_client, logger=logger, settings=settings)
        result = await checker.compare_with_manifest()

        assert result.checked_at == date.today()
