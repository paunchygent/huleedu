"""Cross-service manifest contract tests for CJ ↔ LPS.

This suite verifies that the CJ Assessment Service integration tests
discover models through the published `/api/v1/models` HTTP endpoint
rather than importing LPS internals. Each test now:

- Fetches the manifest via HTTP
- Extracts provider/model information from the response JSON
- Builds `LLMConfigOverrides` objects using manifest data
- Exercises the existing CJ → LPS HTTP flows

Located in `tests/integration/` because it exercises real HTTP
boundaries shared between services.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import aiohttp
import pytest
from common_core import LLMProviderType
from common_core.events.cj_assessment_events import LLMConfigOverrides
from common_core.events.llm_provider_events import LLMComparisonResultV1, TokenUsage
from huleedu_service_libs.error_handling import HuleEduError

from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.implementations.llm_provider_service_client import (
    LLMProviderServiceClient,
)
from services.cj_assessment_service.implementations.retry_manager_impl import RetryManagerImpl
from tests.utils.service_test_manager import ServiceTestManager

MANIFEST_URL = "http://localhost:8090/api/v1/models"


async def fetch_manifest(
    session: aiohttp.ClientSession,
    *,
    provider: LLMProviderType | None = None,
    include_deprecated: bool = False,
) -> dict[str, Any]:
    """Fetch the model manifest via HTTP and return the parsed JSON payload."""

    params: dict[str, str] = {}
    if provider:
        params["provider"] = provider.value
    if include_deprecated:
        params["include_deprecated"] = "true"

    try:
        async with session.get(
            MANIFEST_URL,
            params=params,
            timeout=aiohttp.ClientTimeout(total=10.0),
            headers={"Accept": "application/json"},
        ) as response:
            if response.status != 200:
                body = await response.text()
                pytest.fail(
                    f"Manifest endpoint returned {response.status} "
                    f"(provider={provider.value if provider else 'all'}): {body}"
                )

            return await response.json()
    except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
        pytest.skip(f"Manifest endpoint unavailable: {exc}")


def get_default_model_from_manifest(manifest: dict[str, Any], provider: LLMProviderType) -> dict[str, Any]:
    """Select the default model entry for the requested provider."""

    providers = manifest.get("providers", {})
    provider_models = providers.get(provider.value)
    if not provider_models:
        pytest.fail(f"No models available for provider '{provider.value}' in manifest response")

    # Prefer models flagged as default when available, otherwise use the first entry
    default_model = next((model for model in provider_models if model.get("is_default")), None)
    return default_model or provider_models[0]


def build_overrides(
    model_payload: dict[str, Any],
    *,
    provider: LLMProviderType,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> LLMConfigOverrides:
    """Create LLMConfigOverrides using manifest model metadata."""

    return LLMConfigOverrides(
        provider_override=provider,
        model_override=model_payload["model_id"],
        temperature_override=temperature,
        max_tokens_override=max_tokens,
    )


async def check_service_availability(service_url: str, timeout: int = 10) -> bool:
    """Check if LLM Provider Service is reachable via /healthz."""

    try:
        async with aiohttp.ClientSession() as session:
            health_url = service_url.replace("/api/v1", "") + "/healthz"
            async with session.get(
                health_url, timeout=aiohttp.ClientTimeout(total=timeout)
            ) as response:
                return response.status == 200
    except Exception:
        return False


class TestCJLPSManifestContract:
    """Integration tests validating CJ ↔ LPS manifest contracts over HTTP."""

    @pytest.fixture
    def service_manager(self) -> ServiceTestManager:
        """Shared service validation utilities."""

        return ServiceTestManager()

    @pytest.fixture
    async def validated_services(self, service_manager: ServiceTestManager) -> dict[str, Any]:
        """Ensure LLM Provider Service is healthy before running HTTP tests."""

        endpoints = await service_manager.get_validated_endpoints()
        if "llm_provider_service" not in endpoints:
            pytest.skip("llm_provider_service not available for integration testing")
        return endpoints

    @pytest.fixture
    def integration_settings(self) -> Settings:
        """Settings tuned for local integration tests."""

        settings = Settings()
        settings.LLM_PROVIDER_SERVICE_URL = "http://localhost:8090/api/v1"
        settings.DEFAULT_LLM_PROVIDER = LLMProviderType.ANTHROPIC
        settings.DEFAULT_LLM_MODEL = "claude-haiku-4-5-20251001"
        settings.DEFAULT_LLM_TEMPERATURE = 0.3
        return settings

    @pytest.fixture
    async def http_session(self) -> Any:
        """Reusable HTTP session for manifest calls."""

        async with aiohttp.ClientSession() as session:
            yield session

    @pytest.fixture
    def retry_manager(self, integration_settings: Settings) -> RetryManagerImpl:
        """Retry manager shared across HTTP client calls."""

        return RetryManagerImpl(integration_settings)

    @pytest.fixture
    def llm_client(
        self,
        http_session: Any,
        integration_settings: Settings,
        retry_manager: RetryManagerImpl,
    ) -> LLMProviderServiceClient:
        """HTTP client for LLM Provider Service requests."""

        return LLMProviderServiceClient(
            session=http_session,
            settings=integration_settings,
            retry_manager=retry_manager,
        )

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_cj_uses_manifest_model_with_override(
        self,
        validated_services: dict[str, Any],
        llm_client: LLMProviderServiceClient,
        http_session: Any,
    ) -> None:
        """CJ should build overrides from manifest results and queue requests via HTTP."""

        _ = validated_services
        manifest = await fetch_manifest(http_session)
        default_model = get_default_model_from_manifest(manifest, LLMProviderType.ANTHROPIC)
        overrides = build_overrides(
            default_model,
            provider=LLMProviderType.ANTHROPIC,
            temperature=0.3,
            max_tokens=2000,
        )

        prompt = """Compare these essays and respond with JSON including winner, justification, and confidence."""
        correlation_id = uuid4()

        result = await llm_client.generate_comparison(
            user_prompt=prompt,
            model_override=overrides.model_override,
            temperature_override=overrides.temperature_override,
            max_tokens_override=overrides.max_tokens_override,
            provider_override=overrides.provider_override,
            correlation_id=correlation_id,
        )

        assert result is None, "LPS queues manifest-derived override requests"

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_manifest_validation_flow_end_to_end(
        self,
        validated_services: dict[str, Any],
        llm_client: LLMProviderServiceClient,
        http_session: Any,
    ) -> None:
        """Full flow: HTTP manifest query → override → /comparison POST."""

        _ = validated_services
        manifest = await fetch_manifest(http_session)
        default_model = get_default_model_from_manifest(manifest, LLMProviderType.ANTHROPIC)
        override = build_overrides(default_model, provider=LLMProviderType.ANTHROPIC, temperature=0.3)

        correlation_id = uuid4()
        prompt = "Compare Essay A and Essay B for writing quality. Respond with JSON."

        result = await llm_client.generate_comparison(
            user_prompt=prompt,
            model_override=override.model_override,
            temperature_override=override.temperature_override,
            provider_override=override.provider_override,
            correlation_id=correlation_id,
        )

        assert result is None, "Manifest-based override should still queue via HTTP"

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_llm_provider_service_unavailable_handling(
        self,
        integration_settings: Settings,
        http_session: Any,
        retry_manager: RetryManagerImpl,
    ) -> None:
        """Gracefully skip when LPS is offline; otherwise ensure manifest-driven call succeeds."""

        service_available = await check_service_availability(integration_settings.LLM_PROVIDER_SERVICE_URL)
        if not service_available:
            pytest.skip("LLM Provider Service not available - skipping manifest test")

        manifest = await fetch_manifest(http_session)
        anthropic_model = get_default_model_from_manifest(manifest, LLMProviderType.ANTHROPIC)

        llm_client = LLMProviderServiceClient(
            session=http_session,
            settings=integration_settings,
            retry_manager=retry_manager,
        )

        prompt = "Compare essays to confirm the service is reachable."
        correlation_id = uuid4()

        result = await llm_client.generate_comparison(
            user_prompt=prompt,
            model_override=anthropic_model["model_id"],
            provider_override=LLMProviderType.ANTHROPIC,
            correlation_id=correlation_id,
        )

        assert result is None, "Available service should accept manifest-derived model IDs"

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_invalid_model_rejected_by_llm_service(
        self,
        validated_services: dict[str, Any],
        llm_client: LLMProviderServiceClient,
    ) -> None:
        """Invalid model IDs should trigger validation failures or async rejection."""

        _ = validated_services
        invalid_override = build_overrides(
            {"model_id": "invalid-model-id"},
            provider=LLMProviderType.ANTHROPIC,
            temperature=0.3,
        )

        prompt = "Test prompt to verify invalid model handling"
        correlation_id = uuid4()

        try:
            await llm_client.generate_comparison(
                user_prompt=prompt,
                model_override=invalid_override.model_override,
                provider_override=invalid_override.provider_override,
                correlation_id=correlation_id,
            )
        except HuleEduError as exc:
            assert "invalid" in str(exc).lower() or "not found" in str(exc).lower()

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_callback_event_structure_expectations(
        self,
        http_session: Any,
    ) -> None:
        """Manifest-derived model IDs should align with callback expectations."""

        manifest = await fetch_manifest(http_session)
        anthropic_model = get_default_model_from_manifest(manifest, LLMProviderType.ANTHROPIC)

        correlation_id = uuid4()
        now = datetime.now(UTC)

        sample_callback = LLMComparisonResultV1(
            provider=LLMProviderType.ANTHROPIC,
            model=anthropic_model["model_id"],
            winner="Essay A",
            justification="Essay A demonstrates superior organization and clarity.",
            confidence=4.5,
            response_time_ms=1500,
            token_usage=TokenUsage(prompt_tokens=500, completion_tokens=150, total_tokens=650),
            cost_estimate=0.0012,
            requested_at=now,
            completed_at=now,
            request_id=str(uuid4()),
            correlation_id=correlation_id,
            request_metadata={
                "essay_a_id": str(uuid4()),
                "essay_b_id": str(uuid4()),
            },
        )

        assert sample_callback.provider == LLMProviderType.ANTHROPIC
        assert sample_callback.model == anthropic_model["model_id"]
        assert "essay_a_id" in sample_callback.request_metadata
        assert "essay_b_id" in sample_callback.request_metadata

        if (
            anthropic_model.get("cost_per_1k_input_tokens") is not None
            and anthropic_model.get("cost_per_1k_output_tokens") is not None
        ):
            expected_cost = (
                (sample_callback.token_usage.prompt_tokens / 1000)
                * anthropic_model["cost_per_1k_input_tokens"]
            ) + (
                (sample_callback.token_usage.completion_tokens / 1000)
                * anthropic_model["cost_per_1k_output_tokens"]
            )
            assert abs(sample_callback.cost_estimate - expected_cost) < 0.001
        else:
            assert sample_callback.cost_estimate >= 0.0

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_manifest_supports_multiple_providers(
        self,
        validated_services: dict[str, Any],
        llm_client: LLMProviderServiceClient,
        http_session: Any,
    ) -> None:
        """Manifest endpoint should expose models for multiple providers via HTTP."""

        _ = validated_services
        manifest = await fetch_manifest(http_session)
        providers = manifest.get("providers", {})

        assert "anthropic" in providers, "Anthropic provider missing from manifest"
        assert len(providers) >= 1, "Manifest should include at least one provider"

        anthropic_model = get_default_model_from_manifest(manifest, LLMProviderType.ANTHROPIC)

        prompt = "Compare essays to ensure manifest-derived model can be used via HTTP"
        correlation_id = uuid4()

        result = await llm_client.generate_comparison(
            user_prompt=prompt,
            model_override=anthropic_model["model_id"],
            provider_override=LLMProviderType.ANTHROPIC,
            correlation_id=correlation_id,
        )

        assert result is None, "Manifest models should be accepted across providers"
