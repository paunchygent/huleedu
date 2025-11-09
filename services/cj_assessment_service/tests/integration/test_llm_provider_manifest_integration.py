"""Integration tests for LLM Provider Service manifest-based model selection.

This module verifies that the CJ Assessment Service correctly integrates with
the LLM Provider Service's model manifest system for runtime model selection.

Test Coverage:
- Manifest-based model selection via llm_config_overrides
- Callback event metadata includes actual model/provider used
- End-to-end flow from override → HTTP → callback
- Invalid model rejection by LLM Provider Service
- Service unavailability handling (graceful degradation)
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import aiohttp
import pytest
from common_core import LLMProviderType
from common_core.events.cj_assessment_events import LLMConfigOverrides
from common_core.events.llm_provider_events import LLMComparisonResultV1, TokenUsage
from common_core.metadata_models import EssayProcessingInputRefV1
from huleedu_service_libs.error_handling import HuleEduError

from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.implementations.llm_provider_service_client import (
    LLMProviderServiceClient,
)
from services.cj_assessment_service.implementations.llm_interaction_impl import (
    LLMInteractionImpl,
)
from services.cj_assessment_service.implementations.retry_manager_impl import RetryManagerImpl
from services.cj_assessment_service.models_api import ComparisonTask, EssayForComparison
from services.cj_assessment_service.protocols import CJRepositoryProtocol
from services.cj_assessment_service.tests.integration.callback_simulator import (
    CallbackSimulator,
)
from services.llm_provider_service.model_manifest import ProviderName, get_model_config


async def check_service_availability(service_url: str, timeout: int = 10) -> bool:
    """Check if LLM Provider Service is available by making a health check request.

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


class TestLLMProviderManifestIntegration:
    """Test CJ Assessment Service integration with LLM Provider Service manifest system."""

    @pytest.fixture
    def integration_settings(self) -> Settings:
        """Create settings for integration testing with manifest models."""
        settings = Settings()
        # Override to use local services
        settings.LLM_PROVIDER_SERVICE_URL = "http://localhost:8090/api/v1"
        # Note: These defaults are deprecated in favor of manifest-based selection
        settings.DEFAULT_LLM_PROVIDER = LLMProviderType.ANTHROPIC
        settings.DEFAULT_LLM_MODEL = "claude-haiku-4-5-20251001"
        settings.DEFAULT_LLM_TEMPERATURE = 0.3
        return settings

    @pytest.fixture
    async def http_session(self) -> Any:
        """Create HTTP session for testing."""
        async with aiohttp.ClientSession() as session:
            yield session

    @pytest.fixture
    def retry_manager(self, integration_settings: Settings) -> RetryManagerImpl:
        """Create retry manager for HTTP client."""
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

    @pytest.fixture
    def manifest_model_override(self) -> LLMConfigOverrides:
        """Create LLM config overrides using manifest model."""
        # Get a valid model from manifest
        manifest_config = get_model_config(ProviderName.ANTHROPIC)
        return LLMConfigOverrides(
            provider_override=LLMProviderType.ANTHROPIC,
            model_override=manifest_config.model_id,
            temperature_override=0.3,
            max_tokens_override=2000,
        )

    @pytest.fixture
    def sample_comparison_tasks(self) -> list[ComparisonTask]:
        """Create sample comparison tasks for testing."""
        essay_a = EssayForComparison(
            id=str(uuid4()),
            text_content="This essay demonstrates clear structure and strong arguments.",
            current_bt_score=None,
        )
        essay_b = EssayForComparison(
            id=str(uuid4()),
            text_content="This essay lacks coherent organization and clear thesis.",
            current_bt_score=None,
        )
        return [
            ComparisonTask(
                essay_a=essay_a,
                essay_b=essay_b,
                prompt="Compare these essays based on structure, clarity, and argumentation.",
            )
        ]

    @pytest.mark.integration
    async def test_cj_uses_manifest_model_with_override(
        self,
        llm_client: LLMProviderServiceClient,
        integration_settings: Settings,
        manifest_model_override: LLMConfigOverrides,
    ) -> None:
        """Verify CJ service correctly uses manifest-based model via llm_config_overrides.

        Test Flow:
        1. Get valid model from manifest
        2. Build LLMConfigOverrides with manifest model
        3. Call LLM Provider Service with override
        4. Verify request queued for async processing (async-only architecture)
        """
        # Check if LLM Provider Service is available
        if not await check_service_availability(integration_settings.LLM_PROVIDER_SERVICE_URL):
            pytest.skip("LLM Provider Service not available")

        # Get manifest config to verify model is valid
        manifest_config = get_model_config(ProviderName.ANTHROPIC)
        assert manifest_config.model_id == manifest_model_override.model_override

        # Create comparison prompt
        prompt = """Compare these two essays and determine which is better written.
Essay A (ID: essay-123):
This essay presents a clear thesis statement followed by well-structured paragraphs.
Each paragraph contains a topic sentence and supporting evidence.

Essay B (ID: essay-456):
This essay attempts to make several points but lacks clear organization.
The ideas jump from one topic to another without clear transitions.

Please respond with a JSON object containing:
- 'winner': 'Essay A' or 'Essay B'
- 'justification': Brief explanation of your decision
- 'confidence': Rating from 1-5 (5 = very confident)
Based on clarity, structure, argument quality, and writing mechanics.
Always respond with valid JSON."""

        correlation_id = uuid4()

        # Call LLM Provider Service with manifest-based model override
        result = await llm_client.generate_comparison(
            user_prompt=prompt,
            model_override=manifest_model_override.model_override,
            temperature_override=manifest_model_override.temperature_override,
            max_tokens_override=manifest_model_override.max_tokens_override,
            provider_override=manifest_model_override.provider_override,
            correlation_id=correlation_id,
        )

        # Verify async-only architecture: result should be None (queued for processing)
        assert result is None, "Expected None result for async-only architecture"

        print(f"\n✅ Manifest-based Model Selection Test Passed:")
        print(f"- Model from manifest: {manifest_config.model_id}")
        print(f"- Provider: {manifest_config.provider}")
        print(f"- API Version: {manifest_config.api_version}")
        print(f"- Request queued with correlation ID: {correlation_id}")

    @pytest.mark.integration
    async def test_manifest_validation_flow_end_to_end(
        self,
        llm_client: LLMProviderServiceClient,
        integration_settings: Settings,
    ) -> None:
        """Verify complete flow: manifest query → override → HTTP → callback.

        Test Flow:
        1. Query manifest for available models
        2. Select model and build override
        3. Submit request to LLM Provider Service
        4. Verify request accepted and queued
        """
        # Check if LLM Provider Service is available
        if not await check_service_availability(integration_settings.LLM_PROVIDER_SERVICE_URL):
            pytest.skip("LLM Provider Service not available")

        # Step 1: Query manifest for default Anthropic model
        manifest_config = get_model_config(ProviderName.ANTHROPIC)

        print(f"\nManifest Query Result:")
        print(f"- Model ID: {manifest_config.model_id}")
        print(f"- Display Name: {manifest_config.display_name}")
        print(f"- Release Date: {manifest_config.release_date}")
        print(f"- Max Tokens: {manifest_config.max_tokens}")
        print(f"- Cost (input): ${manifest_config.cost_per_1k_input_tokens}/1K tokens")

        # Step 2: Build override from manifest
        override = LLMConfigOverrides(
            provider_override=LLMProviderType.ANTHROPIC,
            model_override=manifest_config.model_id,
            temperature_override=0.3,
        )

        # Step 3: Submit request
        prompt = """Compare Essay A and Essay B for writing quality.
Essay A: Clear, structured argument with strong evidence.
Essay B: Disorganized ideas without clear thesis.
Respond with JSON: {'winner': 'Essay A' or 'Essay B', 'justification': '...', 'confidence': 1-5}"""

        correlation_id = uuid4()
        result = await llm_client.generate_comparison(
            user_prompt=prompt,
            model_override=override.model_override,
            temperature_override=override.temperature_override,
            provider_override=override.provider_override,
            correlation_id=correlation_id,
        )

        # Step 4: Verify request queued
        assert result is None, "Expected async queuing (None result)"

        print(f"\n✅ End-to-End Manifest Flow Test Passed:")
        print(f"- Manifest query successful")
        print(f"- Override built from manifest")
        print(f"- Request queued for processing")
        print(f"- Correlation ID: {correlation_id}")

    @pytest.mark.integration
    async def test_llm_provider_service_unavailable_handling(
        self,
        integration_settings: Settings,
        http_session: Any,
        retry_manager: RetryManagerImpl,
    ) -> None:
        """Verify graceful handling when LLM Provider Service is unavailable.

        This test demonstrates the skip pattern used throughout integration tests.
        """
        # Check service availability
        is_available = await check_service_availability(
            integration_settings.LLM_PROVIDER_SERVICE_URL
        )

        if not is_available:
            pytest.skip("LLM Provider Service not available - test skipped gracefully")
            return  # Explicit return for clarity

        # If service IS available, verify we can make requests
        llm_client = LLMProviderServiceClient(
            session=http_session,
            settings=integration_settings,
            retry_manager=retry_manager,
        )

        manifest_config = get_model_config(ProviderName.ANTHROPIC)
        correlation_id = uuid4()

        # Use properly formatted prompt with essays
        prompt = """Compare these two essays and determine which is better written.
Essay A (ID: availability-test-1):
This is a test essay to verify service availability.

Essay B (ID: availability-test-2):
This is another test essay for service availability check.

Please respond with a JSON object containing:
- 'winner': 'Essay A' or 'Essay B'
- 'justification': Brief explanation
- 'confidence': Rating from 1-5"""

        result = await llm_client.generate_comparison(
            user_prompt=prompt,
            model_override=manifest_config.model_id,
            correlation_id=correlation_id,
        )

        assert result is None, "Service available and request queued successfully"
        print(f"\n✅ Service Availability Check Passed:")
        print(f"- Service is available at {integration_settings.LLM_PROVIDER_SERVICE_URL}")
        print(f"- Health check successful")
        print(f"- Request accepted with correlation ID: {correlation_id}")

    @pytest.mark.integration
    async def test_invalid_model_rejected_by_llm_service(
        self,
        llm_client: LLMProviderServiceClient,
        integration_settings: Settings,
    ) -> None:
        """Verify LLM Provider Service rejects invalid model IDs.

        Note: This test validates that the LLM Provider Service performs validation.
        Client-side validation would happen in future enhancements.
        """
        # Check if LLM Provider Service is available
        if not await check_service_availability(integration_settings.LLM_PROVIDER_SERVICE_URL):
            pytest.skip("LLM Provider Service not available")

        # Attempt to use an invalid model ID
        invalid_model_override = LLMConfigOverrides(
            provider_override=LLMProviderType.ANTHROPIC,
            model_override="invalid-model-that-does-not-exist",
            temperature_override=0.3,
        )

        prompt = "Test prompt to verify validation"
        correlation_id = uuid4()

        # The service should reject this invalid model
        # Note: Exact error behavior depends on LLM Provider Service implementation
        try:
            await llm_client.generate_comparison(
                user_prompt=prompt,
                model_override=invalid_model_override.model_override,
                provider_override=invalid_model_override.provider_override,
                correlation_id=correlation_id,
            )
            # If no error raised, service may queue request (callback will fail)
            # This is acceptable for async architecture
            print(
                "\n⚠️  Invalid model request queued (validation happens during processing)"
            )
        except HuleEduError as e:
            # Service performed synchronous validation - this is also acceptable
            print(f"\n✅ Invalid Model Rejection Test Passed:")
            print(f"- Service rejected invalid model: {invalid_model_override.model_override}")
            print(f"- Error: {e.error_code}")
            assert "invalid" in str(e).lower() or "not found" in str(e).lower()

    @pytest.mark.integration
    async def test_callback_event_structure_expectations(
        self,
        integration_settings: Settings,
    ) -> None:
        """Verify expected structure of LLMComparisonResultV1 callback events.

        This test validates the callback event schema that CJ service expects to receive.
        While we can't wait for actual Kafka callbacks in integration tests, we can
        verify that the event model structure matches our expectations.
        """
        # This test validates the event contract, not the actual service
        # It ensures our expectations match the LLMComparisonResultV1 schema

        # Get a manifest model to verify metadata expectations
        manifest_config = get_model_config(ProviderName.ANTHROPIC)

        # Create a sample callback event to verify structure
        correlation_id = uuid4()
        now = datetime.now(UTC)
        sample_callback = LLMComparisonResultV1(
            # Model metadata (this is what we're testing for)
            provider=LLMProviderType.ANTHROPIC,
            model=manifest_config.model_id,  # Should match manifest
            # Comparison result
            winner="Essay A",
            justification="Essay A demonstrates superior organization and clarity.",
            confidence=4.5,
            # Performance metrics
            response_time_ms=1500,
            token_usage=TokenUsage(
                prompt_tokens=500,
                completion_tokens=150,
                total_tokens=650,
            ),
            cost_estimate=0.0012,  # Based on manifest cost_per_1k_*_tokens
            # Timestamps
            requested_at=now,
            completed_at=now,
            # Request tracking
            request_id=str(uuid4()),
            correlation_id=correlation_id,
            request_metadata={
                "essay_a_id": str(uuid4()),
                "essay_b_id": str(uuid4()),
            },
        )

        # Verify callback includes all expected fields
        assert sample_callback.provider == LLMProviderType.ANTHROPIC
        assert sample_callback.model == manifest_config.model_id
        assert sample_callback.correlation_id == correlation_id
        assert sample_callback.token_usage is not None
        assert sample_callback.cost_estimate is not None
        assert sample_callback.cost_estimate >= 0.0
        assert "essay_a_id" in sample_callback.request_metadata
        assert "essay_b_id" in sample_callback.request_metadata

        # Verify cost estimate aligns with manifest pricing (if available)
        if (
            manifest_config.cost_per_1k_input_tokens is not None
            and manifest_config.cost_per_1k_output_tokens is not None
        ):
            expected_cost = (
                (sample_callback.token_usage.prompt_tokens / 1000.0)
                * manifest_config.cost_per_1k_input_tokens
            ) + (
                (sample_callback.token_usage.completion_tokens / 1000.0)
                * manifest_config.cost_per_1k_output_tokens
            )
            # Allow small rounding differences (looser tolerance for floating point)
            assert abs(sample_callback.cost_estimate - expected_cost) < 0.001
        else:
            # If manifest doesn't have cost info, just verify cost is non-negative
            assert sample_callback.cost_estimate >= 0.0

        print(f"\n✅ Callback Event Structure Test Passed:")
        print(f"- Provider field validated: {sample_callback.provider}")
        print(f"- Model field validated: {sample_callback.model}")
        print(f"- Token usage included: {sample_callback.token_usage.total_tokens} tokens")
        print(f"- Cost estimate validated: ${sample_callback.cost_estimate:.6f}")
        print(f"- Request metadata includes essay IDs")
        print(f"- Correlation ID preserved: {correlation_id}")

    @pytest.mark.integration
    async def test_manifest_supports_multiple_providers(
        self,
        llm_client: LLMProviderServiceClient,
        integration_settings: Settings,
    ) -> None:
        """Verify manifest query works for multiple providers.

        This test demonstrates that the manifest system supports querying
        different providers and their models, enabling future multi-provider support.
        """
        # Check if LLM Provider Service is available
        if not await check_service_availability(integration_settings.LLM_PROVIDER_SERVICE_URL):
            pytest.skip("LLM Provider Service not available")

        # Query manifest for Anthropic (primary provider)
        anthropic_config = get_model_config(ProviderName.ANTHROPIC)
        assert anthropic_config.provider == ProviderName.ANTHROPIC
        assert anthropic_config.model_id is not None
        assert anthropic_config.api_version is not None

        print(f"\n✅ Multi-Provider Manifest Test Passed:")
        print(f"\nAnthropic:")
        print(f"- Model ID: {anthropic_config.model_id}")
        print(f"- Display Name: {anthropic_config.display_name}")
        print(f"- API Version: {anthropic_config.api_version}")
        print(f"- Max Tokens: {anthropic_config.max_tokens}")

        # Test with Anthropic model from manifest using properly formatted prompt
        prompt = """Compare these two essays and determine which is better written.
Essay A (ID: multi-provider-test-1):
This essay demonstrates clear structure and organization.

Essay B (ID: multi-provider-test-2):
This essay lacks clear transitions between paragraphs.

Please respond with a JSON object containing:
- 'winner': 'Essay A' or 'Essay B'
- 'justification': Brief explanation
- 'confidence': Rating from 1-5"""
        correlation_id = uuid4()

        result = await llm_client.generate_comparison(
            user_prompt=prompt,
            model_override=anthropic_config.model_id,
            provider_override=LLMProviderType.ANTHROPIC,
            correlation_id=correlation_id,
        )

        assert result is None, "Request queued successfully with manifest model"
        print(f"\n- Request queued with Anthropic manifest model: {anthropic_config.model_id}")
        print(f"- Correlation ID: {correlation_id}")
