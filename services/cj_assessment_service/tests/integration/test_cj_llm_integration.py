"""End-to-end integration test for CJ Assessment Service with LLM Provider Service.

This test simulates the actual flow of CJ Assessment Service making HTTP calls
to the LLM Provider Service.
"""


import aiohttp
import pytest

from common_core import LLMProviderType
from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.implementations.llm_provider_service_client import (
    LLMProviderServiceClient,
)
from services.cj_assessment_service.implementations.retry_manager_impl import RetryManagerImpl


class TestCJAssessmentLLMIntegration:
    """Test CJ Assessment Service client integration with LLM Provider Service."""

    @pytest.fixture
    def integration_settings(self):
        """Create settings for integration testing."""
        settings = Settings()
        # Override to use local services
        settings.LLM_PROVIDER_SERVICE_URL = "http://localhost:8090/api/v1"
        settings.DEFAULT_LLM_PROVIDER = LLMProviderType.ANTHROPIC
        settings.DEFAULT_LLM_MODEL = "claude-3-haiku-20240307"
        settings.DEFAULT_LLM_TEMPERATURE = 0.1
        return settings

    @pytest.fixture
    async def http_session(self):
        """Create HTTP session for testing."""
        async with aiohttp.ClientSession() as session:
            yield session

    @pytest.fixture
    def retry_manager(self, integration_settings):
        """Create retry manager."""
        return RetryManagerImpl(integration_settings)

    @pytest.fixture
    def llm_client(self, http_session, integration_settings, retry_manager):
        """Create LLM Provider Service client."""
        return LLMProviderServiceClient(
            session=http_session,
            settings=integration_settings,
            retry_manager=retry_manager,
        )

    async def test_cj_assessment_comparison_flow(self, llm_client):
        """Test the full CJ Assessment comparison flow."""
        # Create a prompt in the format CJ Assessment Service uses
        prompt = """Compare these two essays and determine which is better written.
Essay A (ID: essay-123):
This essay presents a clear thesis statement followed by well-structured paragraphs. 
Each paragraph contains a topic sentence and supporting evidence. The conclusion 
effectively summarizes the main points and reinforces the thesis.

Essay B (ID: essay-456):
This essay attempts to make several points but lacks clear organization. 
The ideas jump from one topic to another without clear transitions. 
The conclusion does not effectively tie back to the introduction.

Please respond with a JSON object containing:
- 'winner': 'Essay A' or 'Essay B'
- 'justification': Brief explanation of your decision
- 'confidence': Rating from 1-5 (5 = very confident)
Based on clarity, structure, argument quality, and writing mechanics.
Always respond with valid JSON."""

        # Call the LLM Provider Service through the client
        # Use claude-3-haiku-20240307 which is a valid Anthropic model
        result, error = await llm_client.generate_comparison(
            user_prompt=prompt,
            model_override="claude-3-haiku-20240307",
            temperature_override=0.1,
        )

        # Verify the response
        assert error is None, f"Unexpected error: {error}"
        assert result is not None, "Expected a result"

        print("\nComparison Result:")
        print(f"Winner: {result['winner']}")
        print(f"Justification: {result['justification']}")
        print(f"Confidence: {result['confidence']}")

        # Validate response format
        assert result["winner"] in ["Essay A", "Essay B"]
        assert isinstance(result["justification"], str)
        assert len(result["justification"]) > 10  # Not empty
        assert isinstance(result["confidence"], (int, float))
        assert 1 <= result["confidence"] <= 5

    async def test_cj_assessment_error_handling(self, llm_client):
        """Test error handling for invalid prompts."""
        # Test with a prompt that doesn't contain the expected essay format
        invalid_prompt = "This is not a valid essay comparison prompt"

        result, error = await llm_client.generate_comparison(
            user_prompt=invalid_prompt,
        )

        assert result is None
        assert error == "Invalid prompt format: Could not extract essays"
        print(f"\nError handling test passed: {error}")

    async def test_cj_assessment_with_mock_provider(
        self, integration_settings, http_session, retry_manager
    ):
        """Test using mock provider configuration."""
        # Check if LLM Provider Service is configured with USE_MOCK_LLM
        async with http_session.get("http://localhost:8090/healthz") as response:
            health_data = await response.json()

        # This test would require the LLM Provider Service to be started
        # with USE_MOCK_LLM=true environment variable
        pytest.skip("Mock provider test requires service reconfiguration")

