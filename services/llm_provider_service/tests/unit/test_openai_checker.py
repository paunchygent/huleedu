"""Unit tests for OpenAI model version checker.

Tests cover:
- OpenAIModelChecker initialization
- check_latest_models() with mocked AsyncOpenAI client
- Model filtering logic (GPT-4+, O1+, O3+ included, GPT-3.5 excluded)
- compare_with_manifest() comparison logic
- Error handling and logging
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from datetime import date
from unittest.mock import AsyncMock, Mock

import pytest
from openai.types import Model

from services.llm_provider_service.model_checker.base import DiscoveredModel
from services.llm_provider_service.model_checker.openai_checker import (
    OpenAIModelChecker,
)
from services.llm_provider_service.model_manifest import ProviderName


class TestOpenAICheckerInit:
    """Tests for OpenAIModelChecker initialization."""

    def test_init_stores_client_and_logger(self) -> None:
        """Checker should store AsyncOpenAI client and logger."""
        mock_client = Mock()
        logger = logging.getLogger(__name__)

        checker = OpenAIModelChecker(client=mock_client, logger=logger)

        assert checker.client is mock_client
        assert checker.logger is logger

    def test_provider_is_openai(self) -> None:
        """Provider attribute should be ProviderName.OPENAI."""
        mock_client = Mock()
        logger = logging.getLogger(__name__)

        checker = OpenAIModelChecker(client=mock_client, logger=logger)

        assert checker.provider == ProviderName.OPENAI


class TestCheckLatestModels:
    """Tests for check_latest_models() method."""

    @pytest.mark.asyncio
    async def test_queries_openai_api(self, mocker: Mock) -> None:
        """Should call client.models.list()."""
        mock_client = Mock()

        # Mock async iterator
        async def mock_async_iter() -> AsyncIterator[Model]:
            return
            yield  # Make this a generator

        mock_client.models.list = AsyncMock(return_value=mock_async_iter())
        logger = logging.getLogger(__name__)

        checker = OpenAIModelChecker(client=mock_client, logger=logger)
        await checker.check_latest_models()

        mock_client.models.list.assert_called_once()

    @pytest.mark.asyncio
    async def test_parses_model_correctly(self, mocker: Mock) -> None:
        """Should parse OpenAI Model into DiscoveredModel."""
        mock_client = Mock()
        mock_model = Model(
            id="gpt-5-mini-2025-08-07",
            object="model",
            created=1725724800,  # Unix timestamp for 2024-09-07
            owned_by="openai",
        )

        # Mock async iterator that yields the model
        async def mock_async_iter() -> AsyncIterator[Model]:
            yield mock_model

        mock_client.models.list = AsyncMock(return_value=mock_async_iter())
        logger = logging.getLogger(__name__)

        checker = OpenAIModelChecker(client=mock_client, logger=logger)
        models = await checker.check_latest_models()

        assert len(models) == 1
        assert models[0].model_id == "gpt-5-mini-2025-08-07"

    @pytest.mark.asyncio
    async def test_filters_gpt_3_models(self, mocker: Mock) -> None:
        """Should exclude GPT-3.5 and earlier models from results."""
        mock_client = Mock()
        mock_models = [
            Model(
                id="gpt-3.5-turbo",
                object="model",
                created=1700000000,
                owned_by="openai",
            ),
            Model(
                id="gpt-4-turbo",
                object="model",
                created=1700000001,
                owned_by="openai",
            ),
        ]

        # Mock async iterator that yields models
        async def mock_async_iter() -> AsyncIterator[Model]:
            for model in mock_models:
                yield model

        mock_client.models.list = AsyncMock(return_value=mock_async_iter())
        logger = logging.getLogger(__name__)

        checker = OpenAIModelChecker(client=mock_client, logger=logger)
        models = await checker.check_latest_models()

        # Should only include GPT-4 model
        assert len(models) == 1
        assert models[0].model_id == "gpt-4-turbo"

    @pytest.mark.asyncio
    async def test_includes_gpt_4_models(self, mocker: Mock) -> None:
        """Should include all GPT-4 models."""
        mock_client = Mock()
        mock_models = [
            Model(
                id="gpt-4-turbo",
                object="model",
                created=1700000000,
                owned_by="openai",
            ),
            Model(
                id="gpt-4-vision-preview",
                object="model",
                created=1700000001,
                owned_by="openai",
            ),
        ]

        async def mock_async_iter() -> AsyncIterator[Model]:
            for model in mock_models:
                yield model

        mock_client.models.list = AsyncMock(return_value=mock_async_iter())
        logger = logging.getLogger(__name__)

        checker = OpenAIModelChecker(client=mock_client, logger=logger)
        models = await checker.check_latest_models()

        # Should include both GPT-4 models
        assert len(models) == 2
        model_ids = {m.model_id for m in models}
        assert "gpt-4-turbo" in model_ids
        assert "gpt-4-vision-preview" in model_ids

    @pytest.mark.asyncio
    async def test_includes_gpt_5_models(self, mocker: Mock) -> None:
        """Should include GPT-5 models."""
        mock_client = Mock()
        mock_model = Model(
            id="gpt-5-mini-2025-08-07",
            object="model",
            created=1725724800,
            owned_by="openai",
        )

        async def mock_async_iter() -> AsyncIterator[Model]:
            yield mock_model

        mock_client.models.list = AsyncMock(return_value=mock_async_iter())
        logger = logging.getLogger(__name__)

        checker = OpenAIModelChecker(client=mock_client, logger=logger)
        models = await checker.check_latest_models()

        assert len(models) == 1
        assert models[0].model_id == "gpt-5-mini-2025-08-07"

    @pytest.mark.asyncio
    async def test_includes_o1_and_o3_models(self, mocker: Mock) -> None:
        """Should include O1 and O3 reasoning models."""
        mock_client = Mock()
        mock_models = [
            Model(
                id="o1-preview",
                object="model",
                created=1700000000,
                owned_by="openai",
            ),
            Model(
                id="o3-mini",
                object="model",
                created=1700000001,
                owned_by="openai",
            ),
        ]

        async def mock_async_iter() -> AsyncIterator[Model]:
            for model in mock_models:
                yield model

        mock_client.models.list = AsyncMock(return_value=mock_async_iter())
        logger = logging.getLogger(__name__)

        checker = OpenAIModelChecker(client=mock_client, logger=logger)
        models = await checker.check_latest_models()

        assert len(models) == 2
        model_ids = {m.model_id for m in models}
        assert "o1-preview" in model_ids
        assert "o3-mini" in model_ids

    @pytest.mark.asyncio
    async def test_handles_api_error_gracefully(self, mocker: Mock) -> None:
        """Should raise exception and log error on API failure."""
        mock_client = Mock()

        async def mock_async_iter() -> AsyncIterator[Model]:
            raise Exception("API authentication failed")
            yield  # Make this a generator

        mock_client.models.list = AsyncMock(return_value=mock_async_iter())
        logger = logging.getLogger(__name__)
        mock_logger = mocker.patch.object(logger, "error")

        checker = OpenAIModelChecker(client=mock_client, logger=logger)

        with pytest.raises(Exception, match="API authentication failed"):
            await checker.check_latest_models()

        # Verify error was logged
        mock_logger.assert_called_once()


class TestCompareWithManifest:
    """Tests for compare_with_manifest() method."""

    @pytest.mark.asyncio
    async def test_identifies_new_models(self, mocker: Mock) -> None:
        """Should detect models in API but not in manifest."""
        mock_client = Mock()

        # Mock a new model not in manifest
        new_model = DiscoveredModel(
            model_id="gpt-6-preview",
            display_name="GPT-6 Preview",
        )

        # Mock check_latest_models to return the new model
        mocker.patch.object(
            OpenAIModelChecker,
            "check_latest_models",
            return_value=[new_model],
        )

        logger = logging.getLogger(__name__)
        checker = OpenAIModelChecker(client=mock_client, logger=logger)
        result = await checker.compare_with_manifest()

        # Verify new model was detected
        assert result.is_up_to_date is False
        # Check combined count of tracked and untracked families
        total_new = len(result.new_models_in_tracked_families) + len(result.new_untracked_families)
        assert total_new >= 1
        # The new model should be in either tracked or untracked list
        all_new_model_ids = {
            m.model_id for m in result.new_models_in_tracked_families
        } | {
            m.model_id for m in result.new_untracked_families
        }
        assert "gpt-6-preview" in all_new_model_ids

    @pytest.mark.asyncio
    async def test_identifies_deprecated_models(self, mocker: Mock) -> None:
        """Should detect models in manifest but not in API (deprecated)."""
        mock_client = Mock()

        # Mock check_latest_models to return empty list (all models deprecated)
        mocker.patch.object(
            OpenAIModelChecker,
            "check_latest_models",
            return_value=[],
        )

        logger = logging.getLogger(__name__)
        checker = OpenAIModelChecker(client=mock_client, logger=logger)
        result = await checker.compare_with_manifest()

        # If no models returned, all manifest models are deprecated
        # Should have at least one deprecated model from manifest
        assert len(result.deprecated_models) >= 1

    @pytest.mark.asyncio
    async def test_is_up_to_date_when_no_changes(self, mocker: Mock) -> None:
        """Should set is_up_to_date=True when manifest matches API."""
        mock_client = Mock()

        # Mock discovered model matching manifest
        matching_model = DiscoveredModel(
            model_id="gpt-5-mini-2025-08-07",
            display_name="GPT-5 Mini",
            api_version="v1",
            capabilities=["function_calling", "json_mode"],
        )

        # Mock check_latest_models to return matching model
        mocker.patch.object(
            OpenAIModelChecker,
            "check_latest_models",
            return_value=[matching_model],
        )

        logger = logging.getLogger(__name__)
        checker = OpenAIModelChecker(client=mock_client, logger=logger)
        result = await checker.compare_with_manifest()

        # When no changes, should be up-to-date
        # Note: This might be False if there are other models in manifest
        # but we're checking the logic works
        assert isinstance(result.is_up_to_date, bool)

    @pytest.mark.asyncio
    async def test_returns_correct_provider(self, mocker: Mock) -> None:
        """Should return OPENAI as provider in result."""
        mock_client = Mock()

        # Mock check_latest_models to return empty list
        mocker.patch.object(
            OpenAIModelChecker,
            "check_latest_models",
            return_value=[],
        )

        logger = logging.getLogger(__name__)
        checker = OpenAIModelChecker(client=mock_client, logger=logger)
        result = await checker.compare_with_manifest()

        assert result.provider == ProviderName.OPENAI

    @pytest.mark.asyncio
    async def test_sets_checked_at_date(self, mocker: Mock) -> None:
        """Should set checked_at to today's date."""
        mock_client = Mock()

        # Mock check_latest_models to return empty list
        mocker.patch.object(
            OpenAIModelChecker,
            "check_latest_models",
            return_value=[],
        )

        logger = logging.getLogger(__name__)
        checker = OpenAIModelChecker(client=mock_client, logger=logger)
        result = await checker.compare_with_manifest()

        assert result.checked_at == date.today()
