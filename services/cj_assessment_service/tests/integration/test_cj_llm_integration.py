"""End-to-end integration test for CJ Assessment Service with LLM Provider Service.

This test simulates the actual flow of CJ Assessment Service making HTTP calls
to the LLM Provider Service.
"""

from typing import Any
from uuid import uuid4

import aiohttp
import pytest
from common_core import LLMProviderType
from huleedu_service_libs.error_handling import HuleEduError

from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.implementations.llm_provider_service_client import (
    LLMProviderServiceClient,
)
from services.cj_assessment_service.implementations.retry_manager_impl import RetryManagerImpl


async def check_service_availability(service_url: str, timeout: int = 10) -> bool:
    """Check if a service is available by making a health check request.

    Args:
        service_url: Base URL of the service
        timeout: Timeout in seconds

    Returns:
        True if service is available, False otherwise
    """
    try:
        async with aiohttp.ClientSession() as session:
            # Remove /api/v1 suffix if present for health check
            health_url = service_url.replace("/api/v1", "") + "/healthz"
            async with session.get(
                health_url, timeout=aiohttp.ClientTimeout(total=timeout)
            ) as response:
                return response.status == 200
    except Exception:
        return False


async def get_service_mock_mode(service_url: str) -> bool:
    """Check if service is running in mock mode.

    Args:
        service_url: Base URL of the service

    Returns:
        True if service is in mock mode, False otherwise
    """
    try:
        async with aiohttp.ClientSession() as session:
            health_url = service_url.replace("/api/v1", "") + "/healthz"
            async with session.get(health_url, timeout=aiohttp.ClientTimeout(total=5)) as response:
                if response.status == 200:
                    health_data = await response.json()
                    mock_mode = health_data.get("mock_mode", False)
                    return bool(mock_mode)
                return False
    except Exception:
        return False


class TestCJAssessmentLLMIntegration:
    """Test CJ Assessment Service client integration with LLM Provider Service."""

    @pytest.fixture
    def integration_settings(self) -> Settings:
        """Create settings for integration testing."""
        settings = Settings()
        # Override to use local services
        settings.LLM_PROVIDER_SERVICE_URL = "http://localhost:8090/api/v1"
        settings.DEFAULT_LLM_PROVIDER = LLMProviderType.ANTHROPIC
        settings.DEFAULT_LLM_MODEL = "claude-3-haiku-20240307"
        settings.DEFAULT_LLM_TEMPERATURE = 0.1
        return settings

    @pytest.fixture
    async def http_session(self) -> Any:
        """Create HTTP session for testing."""
        async with aiohttp.ClientSession() as session:
            yield session

    @pytest.fixture
    def retry_manager(self, integration_settings: Settings) -> RetryManagerImpl:
        """Create retry manager."""
        return RetryManagerImpl(integration_settings)

    @pytest.fixture
    def llm_client(
        self, http_session: Any, integration_settings: Settings, retry_manager: RetryManagerImpl
    ) -> LLMProviderServiceClient:
        """Create LLM Provider Service client."""
        return LLMProviderServiceClient(
            session=http_session,
            settings=integration_settings,
            retry_manager=retry_manager,
        )

    async def test_cj_assessment_comparison_flow(
        self, llm_client: LLMProviderServiceClient, integration_settings: Settings
    ) -> None:
        """Test the full CJ Assessment comparison flow."""
        # Check if LLM Provider Service is available
        if not await check_service_availability(integration_settings.LLM_PROVIDER_SERVICE_URL):
            pytest.skip("LLM Provider Service not available")

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
        # Use claude-3-5-haiku which is a valid Anthropic model
        correlation_id = uuid4()
        result = await llm_client.generate_comparison(
            user_prompt=prompt,
            model_override="claude-3-5-haiku",
            temperature_override=0.1,
            correlation_id=correlation_id,
        )

        # Verify async-only architecture: result should be None (queued for processing)
        assert result is None, "Expected None result for async-only architecture"

        print("\n✅ Async Integration Test Passed:")
        print("- Request successfully queued for async processing")
        print("- Results will be delivered via Kafka callbacks")
        print(f"- Correlation ID: {correlation_id}")

    async def test_cj_assessment_error_handling(
        self, llm_client: LLMProviderServiceClient, integration_settings: Settings
    ) -> None:
        """Test that requests are accepted and queued even with minimal prompts.

        In the async-only architecture, all requests are accepted (202) and queued
        for async processing. Validation errors are reported via Kafka callbacks,
        not synchronous HTTP exceptions.
        """
        # Check if LLM Provider Service is available
        if not await check_service_availability(integration_settings.LLM_PROVIDER_SERVICE_URL):
            pytest.skip("LLM Provider Service not available")

        # Test with a minimal prompt - should still be accepted and queued
        minimal_prompt = "This is not a valid essay comparison prompt"

        correlation_id = uuid4()

        # In async-only architecture, this should return None (queued), not raise an error
        result = await llm_client.generate_comparison(
            user_prompt=minimal_prompt,
            correlation_id=correlation_id,
        )

        # Verify async-only behavior: request accepted and queued
        assert result is None, "Expected None result for async-only architecture"

        print("\n✅ Async-only architecture verified:")
        print("- Request accepted and queued (202)")
        print("- No synchronous validation errors")
        print(f"- Correlation ID: {correlation_id}")
        print("- Validation errors (if any) will be delivered via Kafka callbacks")

    async def test_cj_assessment_with_mock_provider(
        self, integration_settings: Settings, http_session: Any, retry_manager: RetryManagerImpl
    ) -> None:
        """Test using mock provider configuration."""
        # Check if LLM Provider Service is available
        if not await check_service_availability(integration_settings.LLM_PROVIDER_SERVICE_URL):
            pytest.skip("LLM Provider Service not available")

        # Check if service is running in mock mode
        is_mock_mode = await get_service_mock_mode(integration_settings.LLM_PROVIDER_SERVICE_URL)
        if not is_mock_mode:
            pytest.skip("LLM Provider Service not running in mock mode")

        # Create LLM client
        llm_client = LLMProviderServiceClient(
            session=http_session,
            settings=integration_settings,
            retry_manager=retry_manager,
        )

        # Test with mock provider
        prompt = """Compare these two essays and determine which is better written.
Essay A (ID: mock-essay-1):
This is a mock essay with good structure and clear arguments.

Essay B (ID: mock-essay-2):
This is another mock essay with different qualities.

Please respond with a JSON object containing:
- 'winner': 'Essay A' or 'Essay B'
- 'justification': Brief explanation of your decision
- 'confidence': Rating from 1-5 (5 = very confident)
Based on clarity, structure, argument quality, and writing mechanics.
Always respond with valid JSON."""

        correlation_id = uuid4()
        try:
            result = await llm_client.generate_comparison(
                user_prompt=prompt,
                model_override="mock-model",
                temperature_override=0.1,
                correlation_id=correlation_id,
            )
        except HuleEduError as e:
            pytest.fail(f"Unexpected error: {e}")

        # Verify async-only architecture: result should be None (queued for processing)
        assert result is None, "Expected None result for async-only architecture"

        print("\n✅ Mock Provider Integration Test Passed:")
        print("- Request successfully queued for async processing")
        print("- Results will be delivered via Kafka callbacks")
        print(f"- Correlation ID: {correlation_id}")
        print("- Mock mode confirmed for testing environment")
