"""Unit tests for LLM Provider Service client."""

import json
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import aiohttp
import pytest

from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.implementations.llm_provider_service_client import (
    LLMProviderServiceClient,
)


@pytest.fixture
def mock_settings() -> Settings:
    """Create mock settings for testing."""
    settings = MagicMock(spec=Settings)
    settings.LLM_PROVIDER_SERVICE_URL = "http://test-llm-service:8090/api/v1"
    settings.DEFAULT_LLM_PROVIDER = "anthropic"
    settings.DEFAULT_LLM_MODEL = "claude-3-haiku"
    settings.DEFAULT_LLM_TEMPERATURE = 0.1
    return settings


@pytest.fixture
def mock_session() -> AsyncMock:
    """Create mock HTTP session."""
    return AsyncMock(spec=aiohttp.ClientSession)


@pytest.fixture
def mock_retry_manager() -> AsyncMock:
    """Create mock retry manager."""
    retry_manager = AsyncMock()
    # Make retry manager pass through the function call
    async def passthrough(func, *args, **kwargs):
        return await func()
    retry_manager.with_retry.side_effect = passthrough
    return retry_manager


@pytest.fixture
def client(mock_session: AsyncMock, mock_settings: Settings, mock_retry_manager: AsyncMock) -> LLMProviderServiceClient:
    """Create LLM Provider Service client for testing."""
    return LLMProviderServiceClient(mock_session, mock_settings, mock_retry_manager)


class TestLLMProviderServiceClient:
    """Test cases for LLM Provider Service client."""

    async def test_extract_essays_from_prompt_success(self, client: LLMProviderServiceClient) -> None:
        """Test successful extraction of essays from formatted prompt."""
        prompt = """Compare these two essays and determine which is better written.
Essay A (ID: 123):
This is the content of essay A.
It has multiple lines.

Essay B (ID: 456):
This is the content of essay B.
It also has multiple lines.

Please respond with a JSON object containing:
- 'winner': 'Essay A' or 'Essay B'
- 'justification': Brief explanation of your decision
- 'confidence': Rating from 1-5 (5 = very confident)"""

        result = client._extract_essays_from_prompt(prompt)
        
        assert result is not None
        base_prompt, essay_a, essay_b = result
        
        assert "Compare these two essays" in base_prompt
        assert "This is the content of essay A" in essay_a
        assert "multiple lines" in essay_a
        assert "This is the content of essay B" in essay_b
        assert "multiple lines" in essay_b

    async def test_extract_essays_from_prompt_failure(self, client: LLMProviderServiceClient) -> None:
        """Test extraction failure with malformed prompt."""
        prompt = "This prompt doesn't contain the expected essay format"
        
        result = client._extract_essays_from_prompt(prompt)
        assert result is None

    async def test_generate_comparison_success(self, client: LLMProviderServiceClient, mock_session: AsyncMock) -> None:
        """Test successful comparison generation."""
        # Mock successful response
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value=json.dumps({
            "winner": "Essay A",
            "justification": "Essay A has better structure",
            "confidence": 4.5,
            "provider": "anthropic",
            "model": "claude-3-haiku",
            "cached": False,
            "response_time_ms": 1500,
            "correlation_id": str(uuid4()),
        }))
        
        mock_session.post.return_value.__aenter__.return_value = mock_response
        
        # Create test prompt
        prompt = """Compare these two essays.
Essay A (ID: 123):
Essay A content.

Essay B (ID: 456):
Essay B content.

Please respond with a JSON object."""

        # Call generate_comparison
        result, error = await client.generate_comparison(
            user_prompt=prompt,
            model_override="claude-3-haiku",
            temperature_override=0.1,
        )
        
        # Verify result
        assert error is None
        assert result is not None
        assert result["winner"] == "Essay A"
        assert result["justification"] == "Essay A has better structure"
        assert result["confidence"] == 4.5
        
        # Verify API call
        mock_session.post.assert_called_once()
        call_args = mock_session.post.call_args
        assert call_args[0][0] == "http://test-llm-service:8090/api/v1/comparison"
        
        # Verify request body
        request_body = call_args[1]["json"]
        assert request_body["user_prompt"] == "Compare these two essays."
        assert request_body["essay_a"] == "Essay A content."
        assert request_body["essay_b"] == "Essay B content."
        assert request_body["llm_config_overrides"]["provider_override"] == "anthropic"
        assert request_body["llm_config_overrides"]["model_override"] == "claude-3-haiku"
        assert request_body["llm_config_overrides"]["temperature_override"] == 0.1

    async def test_generate_comparison_http_error(self, client: LLMProviderServiceClient, mock_session: AsyncMock) -> None:
        """Test handling of HTTP error responses."""
        # Mock error response
        mock_response = AsyncMock()
        mock_response.status = 500
        mock_response.text = AsyncMock(return_value=json.dumps({
            "error": "Internal server error",
            "details": "Provider unavailable"
        }))
        
        mock_session.post.return_value.__aenter__.return_value = mock_response
        
        prompt = """Compare these two essays.
Essay A (ID: 123):
Essay A content.

Essay B (ID: 456):
Essay B content."""

        result, error = await client.generate_comparison(user_prompt=prompt)
        
        assert result is None
        assert error == "Internal server error: Provider unavailable"

    async def test_generate_comparison_network_error(self, client: LLMProviderServiceClient, mock_session: AsyncMock) -> None:
        """Test handling of network errors."""
        # Mock network error
        mock_session.post.side_effect = aiohttp.ClientError("Connection failed")
        
        prompt = """Compare these two essays.
Essay A (ID: 123):
Essay A content.

Essay B (ID: 456):
Essay B content."""

        result, error = await client.generate_comparison(user_prompt=prompt)
        
        assert result is None
        assert "HTTP request failed: Connection failed" in error

    async def test_generate_comparison_invalid_prompt(self, client: LLMProviderServiceClient) -> None:
        """Test handling of invalid prompt format."""
        prompt = "This is not a valid comparison prompt"
        
        result, error = await client.generate_comparison(user_prompt=prompt)
        
        assert result is None
        assert error == "Invalid prompt format: Could not extract essays"

    async def test_generate_comparison_json_parse_error(self, client: LLMProviderServiceClient, mock_session: AsyncMock) -> None:
        """Test handling of invalid JSON response."""
        # Mock response with invalid JSON
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value="Invalid JSON response")
        
        mock_session.post.return_value.__aenter__.return_value = mock_response
        
        prompt = """Compare these two essays.
Essay A (ID: 123):
Essay A content.

Essay B (ID: 456):
Essay B content."""

        result, error = await client.generate_comparison(user_prompt=prompt)
        
        assert result is None
        assert "Failed to parse response JSON" in error