"""Unit tests for shared LLM batching helpers."""

from __future__ import annotations

from unittest.mock import Mock

import pytest
from common_core import LLMBatchingMode, LLMProviderType

from services.cj_assessment_service.cj_core_logic.batch_config import BatchConfigOverrides
from services.cj_assessment_service.cj_core_logic.llm_batching import (
    build_llm_metadata_context,
    resolve_effective_llm_batching_mode,
)
from services.cj_assessment_service.config import Settings


@pytest.fixture
def settings_stub() -> Settings:
    """Provide a mock Settings object for batching tests."""

    settings = Mock(spec=Settings)
    settings.DEFAULT_LLM_PROVIDER = LLMProviderType.OPENAI
    settings.LLM_BATCHING_MODE = LLMBatchingMode.PER_REQUEST
    settings.LLM_BATCH_API_ALLOWED_PROVIDERS = [
        LLMProviderType.OPENAI,
        LLMProviderType.ANTHROPIC,
    ]
    settings.ENABLE_LLM_BATCHING_METADATA_HINTS = True
    return settings


class TestResolveEffectiveLLMBatchingMode:
    """Behavioural tests for batching mode resolution helper."""

    def test_defaults_to_settings_value(self, settings_stub: Settings) -> None:
        """When no override is present the settings value is returned."""

        settings_stub.LLM_BATCHING_MODE = LLMBatchingMode.SERIAL_BUNDLE

        result = resolve_effective_llm_batching_mode(
            settings=settings_stub,
            batch_config_overrides=None,
            provider_override=None,
        )

        assert result is LLMBatchingMode.SERIAL_BUNDLE

    def test_respects_override(self, settings_stub: Settings) -> None:
        """Explicit overrides should win over the default setting."""

        overrides = BatchConfigOverrides(
            llm_batching_mode_override=LLMBatchingMode.PROVIDER_BATCH_API
        )

        result = resolve_effective_llm_batching_mode(
            settings=settings_stub,
            batch_config_overrides=overrides,
            provider_override=LLMProviderType.OPENAI,
        )

        assert result is LLMBatchingMode.PROVIDER_BATCH_API

    def test_guardrails_fallback_when_provider_not_allowed(self, settings_stub: Settings) -> None:
        """Provider_batch_api falls back when provider is outside the allow list."""

        settings_stub.LLM_BATCHING_MODE = LLMBatchingMode.SERIAL_BUNDLE
        settings_stub.LLM_BATCH_API_ALLOWED_PROVIDERS = [LLMProviderType.OPENAI]
        overrides = BatchConfigOverrides(
            llm_batching_mode_override=LLMBatchingMode.PROVIDER_BATCH_API
        )

        result = resolve_effective_llm_batching_mode(
            settings=settings_stub,
            batch_config_overrides=overrides,
            provider_override=LLMProviderType.GOOGLE,
        )

        assert result is LLMBatchingMode.SERIAL_BUNDLE


class TestBuildLLMMetadataContext:
    """Tests for metadata context construction used by batch submission."""

    def test_includes_defaults_and_iteration(
        self,
        settings_stub: Settings,
    ) -> None:
        """Metadata builder should always emit cj identifiers and optional hints."""

        result = build_llm_metadata_context(
            cj_batch_id=123,
            cj_source=None,
            cj_request_type=None,
            settings=settings_stub,
            effective_mode=LLMBatchingMode.SERIAL_BUNDLE,
            iteration_metadata_context={"comparison_iteration": 2},
        )

        assert result["cj_batch_id"] == "123"
        assert result["cj_source"] == "els"
        assert result["cj_request_type"] == "cj_comparison"
        assert result["cj_llm_batching_mode"] == LLMBatchingMode.SERIAL_BUNDLE.value
        assert result["comparison_iteration"] == 2
