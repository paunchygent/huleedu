"""Financial integration tests for model checkers with real API calls.

These tests actually call provider APIs and incur real costs. They are marked
with @pytest.mark.financial and must be explicitly opted-in to run.

Usage:
    # Run financial tests
    pdm run pytest-root \\
        services/llm_provider_service/tests/unit/test_model_checker_financial.py \\
        -m financial

Tests cover:
- Anthropic real API integration (4 tests)
- OpenAI real API integration (4 tests)
- Google real API integration (4 tests)
- OpenRouter real API integration (4 tests)

Each provider test suite covers:
1. Client initialization with real API key
2. Discovering models from real API
3. Parsing real API responses
4. Comparing real data with manifest
"""

from __future__ import annotations

import logging
import os

import aiohttp
import pytest
from anthropic import AsyncAnthropic
from openai import AsyncOpenAI

from services.llm_provider_service.config import Settings
from services.llm_provider_service.model_checker.anthropic_checker import (
    AnthropicModelChecker,
)
from services.llm_provider_service.model_checker.google_checker import GoogleModelChecker
from services.llm_provider_service.model_checker.openai_checker import OpenAIModelChecker
from services.llm_provider_service.model_checker.openrouter_checker import (
    OpenRouterModelChecker,
)
from services.llm_provider_service.model_manifest import ProviderName

logger = logging.getLogger(__name__)


@pytest.fixture
def settings() -> Settings:
    """Create Settings instance for tests."""
    return Settings()


class TestAnthropicFinancial:
    """Financial integration tests for Anthropic model checker."""

    @pytest.mark.asyncio
    @pytest.mark.financial
    async def test_create_client_with_real_key(self, settings: Settings) -> None:
        """Should create AsyncAnthropic client with real API key."""
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            pytest.skip("ANTHROPIC_API_KEY not set")

        client = AsyncAnthropic(api_key=api_key)

        assert client is not None
        assert hasattr(client, "models")

    @pytest.mark.asyncio
    @pytest.mark.financial
    async def test_discover_models_from_real_api(self, settings: Settings) -> None:
        """Should discover models from real Anthropic API."""
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            pytest.skip("ANTHROPIC_API_KEY not set")

        client = AsyncAnthropic(api_key=api_key)
        checker = AnthropicModelChecker(client=client, logger=logger, settings=settings)

        models = await checker.check_latest_models()

        # Verify we got real models
        assert len(models) > 0
        # Should include Claude 3+ models
        model_ids = {m.model_id for m in models}
        assert any("claude-3" in mid for mid in model_ids)

    @pytest.mark.asyncio
    @pytest.mark.financial
    async def test_parse_real_api_response(self, settings: Settings) -> None:
        """Should correctly parse real Anthropic API response."""
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            pytest.skip("ANTHROPIC_API_KEY not set")

        client = AsyncAnthropic(api_key=api_key)
        checker = AnthropicModelChecker(client=client, logger=logger, settings=settings)

        models = await checker.check_latest_models()

        # Verify parsed structure
        for model in models:
            assert model.model_id is not None
            assert model.display_name is not None
            # All Claude models should be filtered to 3+
            assert "claude-2" not in model.model_id.lower()
            assert "claude-instant" not in model.model_id.lower()

    @pytest.mark.asyncio
    @pytest.mark.financial
    async def test_compare_with_manifest_real_data(self, settings: Settings) -> None:
        """Should compare real API data with manifest."""
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            pytest.skip("ANTHROPIC_API_KEY not set")

        client = AsyncAnthropic(api_key=api_key)
        checker = AnthropicModelChecker(client=client, logger=logger, settings=settings)

        result = await checker.compare_with_manifest()

        # Verify result structure
        assert result.provider == ProviderName.ANTHROPIC
        assert isinstance(result.is_up_to_date, bool)
        assert isinstance(result.new_models_in_tracked_families, list)
        assert isinstance(result.new_untracked_families, list)
        assert isinstance(result.deprecated_models, list)
        assert isinstance(result.breaking_changes, list)


class TestOpenAIFinancial:
    """Financial integration tests for OpenAI model checker."""

    @pytest.mark.asyncio
    @pytest.mark.financial
    async def test_create_client_with_real_key(self, settings: Settings) -> None:
        """Should create AsyncOpenAI client with real API key."""
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            pytest.skip("OPENAI_API_KEY not set")

        client = AsyncOpenAI(api_key=api_key)

        assert client is not None
        assert hasattr(client, "models")

    @pytest.mark.asyncio
    @pytest.mark.financial
    async def test_discover_models_from_real_api(self, settings: Settings) -> None:
        """Should discover models from real OpenAI API."""
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            pytest.skip("OPENAI_API_KEY not set")

        client = AsyncOpenAI(api_key=api_key)
        checker = OpenAIModelChecker(client=client, logger=logger, settings=settings)

        models = await checker.check_latest_models()

        # Verify we got real models
        assert len(models) > 0
        # Should include GPT-4+ or O1/O3 models
        model_ids = {m.model_id for m in models}
        assert any(
            "gpt-4" in mid or "gpt-5" in mid or "o1" in mid or "o3" in mid for mid in model_ids
        )

    @pytest.mark.asyncio
    @pytest.mark.financial
    async def test_parse_real_api_response(self, settings: Settings) -> None:
        """Should correctly parse real OpenAI API response."""
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            pytest.skip("OPENAI_API_KEY not set")

        client = AsyncOpenAI(api_key=api_key)
        checker = OpenAIModelChecker(client=client, logger=logger, settings=settings)

        models = await checker.check_latest_models()

        # Verify parsed structure
        for model in models:
            assert model.model_id is not None
            assert model.display_name is not None
            # Should filter out GPT-3.5 and earlier
            assert "gpt-3.5" not in model.model_id.lower()
            assert "gpt-3" not in model.model_id.lower() or "gpt-3" not in model.model_id.lower()

    @pytest.mark.asyncio
    @pytest.mark.financial
    async def test_compare_with_manifest_real_data(self, settings: Settings) -> None:
        """Should compare real API data with manifest."""
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            pytest.skip("OPENAI_API_KEY not set")

        client = AsyncOpenAI(api_key=api_key)
        checker = OpenAIModelChecker(client=client, logger=logger, settings=settings)

        result = await checker.compare_with_manifest()

        # Verify result structure
        assert result.provider == ProviderName.OPENAI
        assert isinstance(result.is_up_to_date, bool)
        assert isinstance(result.new_models_in_tracked_families, list)
        assert isinstance(result.new_untracked_families, list)
        assert isinstance(result.deprecated_models, list)
        assert isinstance(result.breaking_changes, list)


class TestGoogleFinancial:
    """Financial integration tests for Google model checker."""

    @pytest.mark.asyncio
    @pytest.mark.financial
    async def test_create_client_with_real_key(self, settings: Settings) -> None:
        """Should create genai.Client with real API key."""
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            pytest.skip("GOOGLE_API_KEY not set")

        # Import at runtime to avoid issues with optional dependency
        from google import genai

        client = genai.Client(api_key=api_key)

        assert client is not None
        assert hasattr(client, "aio")

    @pytest.mark.asyncio
    @pytest.mark.financial
    async def test_discover_models_from_real_api(self, settings: Settings) -> None:
        """Should discover models from real Google API."""
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            pytest.skip("GOOGLE_API_KEY not set")

        from google import genai

        client = genai.Client(api_key=api_key)
        checker = GoogleModelChecker(client=client, logger=logger, settings=settings)

        models = await checker.check_latest_models()

        # Verify we got real models
        assert len(models) > 0
        # Should include Gemini 1.5+ or 2.x models
        model_ids = {m.model_id for m in models}
        assert any("gemini-1.5" in mid or "gemini-2" in mid for mid in model_ids)

    @pytest.mark.asyncio
    @pytest.mark.financial
    async def test_parse_real_api_response(self, settings: Settings) -> None:
        """Should correctly parse real Google API response."""
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            pytest.skip("GOOGLE_API_KEY not set")

        from google import genai

        client = genai.Client(api_key=api_key)
        checker = GoogleModelChecker(client=client, logger=logger, settings=settings)

        models = await checker.check_latest_models()

        # Verify parsed structure
        for model in models:
            assert model.model_id is not None
            assert model.display_name is not None
            # Should filter out Gemini 1.0 and pro-vision
            assert "gemini-1.0" not in model.model_id.lower()
            assert "pro-vision" not in model.model_id.lower()

    @pytest.mark.asyncio
    @pytest.mark.financial
    async def test_compare_with_manifest_real_data(self, settings: Settings) -> None:
        """Should compare real API data with manifest."""
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            pytest.skip("GOOGLE_API_KEY not set")

        from google import genai

        client = genai.Client(api_key=api_key)
        checker = GoogleModelChecker(client=client, logger=logger, settings=settings)

        result = await checker.compare_with_manifest()

        # Verify result structure
        assert result.provider == ProviderName.GOOGLE
        assert isinstance(result.is_up_to_date, bool)
        assert isinstance(result.new_models_in_tracked_families, list)
        assert isinstance(result.new_untracked_families, list)
        assert isinstance(result.deprecated_models, list)
        assert isinstance(result.breaking_changes, list)


class TestOpenRouterFinancial:
    """Financial integration tests for OpenRouter model checker."""

    @pytest.mark.asyncio
    @pytest.mark.financial
    async def test_create_client_with_real_key(self, settings: Settings) -> None:
        """Should create aiohttp session for OpenRouter."""
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            pytest.skip("OPENROUTER_API_KEY not set")

        session = aiohttp.ClientSession()

        try:
            assert session is not None
            assert not session.closed
        finally:
            await session.close()

    @pytest.mark.asyncio
    @pytest.mark.financial
    async def test_discover_models_from_real_api(self, settings: Settings) -> None:
        """Should discover models from real OpenRouter API."""
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            pytest.skip("OPENROUTER_API_KEY not set")

        session = aiohttp.ClientSession()

        try:
            checker = OpenRouterModelChecker(
                session=session, api_key=api_key, logger=logger, settings=settings
            )
            models = await checker.check_latest_models()

            # Verify we got real models (filter only allows Claude 4.5-tier)
            # Note: If OpenRouter has no 4.5-tier models yet, this may be empty
            model_ids = {m.model_id for m in models}
            # All returned models should match the filter pattern
            for mid in model_ids:
                assert "anthropic/claude-" in mid and "-4-5-" in mid
        finally:
            await session.close()

    @pytest.mark.asyncio
    @pytest.mark.financial
    async def test_parse_real_api_response(self, settings: Settings) -> None:
        """Should correctly parse real OpenRouter API response."""
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            pytest.skip("OPENROUTER_API_KEY not set")

        session = aiohttp.ClientSession()

        try:
            checker = OpenRouterModelChecker(
                session=session, api_key=api_key, logger=logger, settings=settings
            )
            models = await checker.check_latest_models()

            # Verify parsed structure
            for model in models:
                assert model.model_id is not None
                assert model.display_name is not None
                # Should only include Anthropic Claude 3+
                assert "anthropic/claude" in model.model_id.lower()
                assert "claude-2" not in model.model_id.lower()
        finally:
            await session.close()

    @pytest.mark.asyncio
    @pytest.mark.financial
    async def test_compare_with_manifest_real_data(self, settings: Settings) -> None:
        """Should compare real API data with manifest."""
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            pytest.skip("OPENROUTER_API_KEY not set")

        session = aiohttp.ClientSession()

        try:
            checker = OpenRouterModelChecker(
                session=session, api_key=api_key, logger=logger, settings=settings
            )
            result = await checker.compare_with_manifest()

            # Verify result structure
            assert result.provider == ProviderName.OPENROUTER
            assert isinstance(result.is_up_to_date, bool)
            assert isinstance(result.new_models_in_tracked_families, list)
            assert isinstance(result.new_untracked_families, list)
            assert isinstance(result.deprecated_models, list)
            assert isinstance(result.breaking_changes, list)
        finally:
            await session.close()
