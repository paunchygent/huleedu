"""Integration tests for LLM API health/connectivity.

These tests verify that basic API connectivity and authentication are working
for all supported LLM providers. They serve as an early warning system for
potential breaking changes or authentication issues.

Usage:
    # Run only these tests
    python -m pytest tests/integration/test_llm_api_health.py -v

    # Run as part of a specific test group
    python -m pytest -m llm_api -v

Note: These tests require actual API keys to be configured in the environment.
They are designed to be run manually or in a scheduled CI job, not as part
of the regular test suite.
"""

from __future__ import annotations

import aiohttp
import pytest
from loguru import logger

from src.cj_essay_assessment.config import get_settings


def skip_if_no_api_key(provider_name: str, api_key: str | None) -> None:
    """Skip a test if the API key is not available."""
    if not api_key:
        pytest.skip(f"Skipping {provider_name} health check: No API key configured")


@pytest.fixture(scope="module")
async def aiohttp_session_fixture() -> aiohttp.ClientSession:
    """Provide an aiohttp ClientSession for test requests.

    This fixture ensures a single ClientSession is used for all test cases
    and is properly closed when tests are completed.
    """
    # Create a single session per module to avoid multiple connections
    session = aiohttp.ClientSession()
    try:
        yield session
    finally:
        # Ensure session is properly closed after tests, even if they fail
        await session.close()
        logger.debug("aiohttp ClientSession closed successfully")


class TestLLMApiHealth:
    """Integration tests for LLM API health/connectivity."""

    @pytest.mark.llm_api
    @pytest.mark.asyncio
    async def test_openai_health(
        self, aiohttp_session_fixture: aiohttp.ClientSession
    ) -> None:
        """Test OpenAI API connectivity by checking model availability."""
        settings = get_settings()
        api_key = settings.openai_api_key
        skip_if_no_api_key("OpenAI", api_key)

        # Act: Call a simple endpoint that requires auth but minimal processing
        url = "https://api.openai.com/v1/models"
        headers = {"Authorization": f"Bearer {api_key}"}

        async with aiohttp_session_fixture.get(url, headers=headers) as response:
            # Assert
            assert (
                response.status == 200
            ), f"OpenAI API returned status {response.status}: {await response.text()}"
            data = await response.json()
            assert "data" in data, "OpenAI response missing 'data' field"
            assert isinstance(data["data"], list), "OpenAI 'data' field is not a list"
            assert len(data["data"]) > 0, "OpenAI returned empty model list"

            model_count = len(data["data"])
            logger.info(
                f"OpenAI API health check successful. {model_count} models available."
            )

    @pytest.mark.llm_api
    @pytest.mark.asyncio
    async def test_anthropic_health(
        self, aiohttp_session_fixture: aiohttp.ClientSession
    ) -> None:
        """Test Anthropic API connectivity by checking model availability."""
        settings = get_settings()
        api_key = settings.anthropic_api_key
        skip_if_no_api_key("Anthropic", api_key)

        # Act: Call a simple endpoint that requires auth but minimal processing
        url = "https://api.anthropic.com/v1/models"
        headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01"}

        async with aiohttp_session_fixture.get(url, headers=headers) as response:
            # Assert
            assert (
                response.status == 200
            ), f"Anthropic API returned status {response.status}: {await response.text()}"
            data = await response.json()
            assert "data" in data, "Anthropic response missing 'data' field"
            assert isinstance(data["data"], list), "Anthropic 'data' field is not a list"
            assert len(data["data"]) > 0, "Anthropic returned empty model list"

            model_count = len(data["data"])
            logger.info(
                f"Anthropic API health check successful. {model_count} models available."
            )

    @pytest.mark.llm_api
    @pytest.mark.asyncio
    async def test_google_health(
        self, aiohttp_session_fixture: aiohttp.ClientSession
    ) -> None:
        """Test Google Gemini API connectivity by checking model availability."""
        settings = get_settings()
        api_key = settings.google_api_key
        skip_if_no_api_key("Google", api_key)

        # Act: Call a simple endpoint that requires auth but minimal processing
        url = f"https://generativelanguage.googleapis.com/v1/models?key={api_key}"

        async with aiohttp_session_fixture.get(url) as response:
            # Assert
            assert (
                response.status == 200
            ), f"Google API returned status {response.status}: {await response.text()}"
            data = await response.json()
            assert "models" in data, "Google response missing 'models' field"
            assert isinstance(data["models"], list), "Google 'models' field is not a list"
            assert len(data["models"]) > 0, "Google returned empty model list"

            model_count = len(data["models"])
            logger.info(
                f"Google API health check successful. {model_count} models available."
            )

    @pytest.mark.llm_api
    @pytest.mark.asyncio
    async def test_openrouter_health(
        self, aiohttp_session_fixture: aiohttp.ClientSession
    ) -> None:
        """Test OpenRouter API connectivity by checking model availability."""
        settings = get_settings()
        api_key = settings.openrouter_api_key
        skip_if_no_api_key("OpenRouter", api_key)

        # Act: Call a simple endpoint that requires auth but minimal processing
        url = "https://openrouter.ai/api/v1/models"
        headers = {"Authorization": f"Bearer {api_key}"}

        async with aiohttp_session_fixture.get(url, headers=headers) as response:
            # Assert
            assert (
                response.status == 200
            ), f"OpenRouter API returned status {response.status}: {await response.text()}"
            data = await response.json()
            assert "data" in data, "OpenRouter response missing 'data' field"
            assert isinstance(data["data"], list), "OpenRouter 'data' field is not a list"
            assert len(data["data"]) > 0, "OpenRouter returned empty model list"

            model_count = len(data["data"])
            logger.info(
                f"OpenRouter API health check successful. {model_count} models available."
            )
