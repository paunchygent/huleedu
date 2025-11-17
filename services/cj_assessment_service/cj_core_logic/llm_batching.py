"""Shared helpers for CJ LLM batching configuration and metadata."""

from __future__ import annotations

from typing import Any

from common_core.config_enums import LLMBatchingMode, LLMProviderType
from huleedu_service_libs.logging_utils import create_service_logger

from services.cj_assessment_service.cj_core_logic.batch_config import BatchConfigOverrides
from services.cj_assessment_service.config import Settings

logger = create_service_logger("cj_assessment_service.llm_batching")


def _normalize_provider_type(
    provider_value: str | LLMProviderType | None,
) -> LLMProviderType | None:
    """Coerce provider override values to standardized enum form."""

    if provider_value is None:
        return None
    if isinstance(provider_value, LLMProviderType):
        return provider_value
    if isinstance(provider_value, str):
        candidate = provider_value
        try:
            return LLMProviderType(candidate)
        except ValueError:
            try:
                return LLMProviderType(candidate.lower())
            except ValueError:
                logger.debug(
                    "Ignoring unsupported provider override for batching guard",
                    extra={"provider_override": provider_value},
                )
                return None
    return None


def resolve_effective_llm_batching_mode(
    *,
    settings: Settings,
    batch_config_overrides: BatchConfigOverrides | None,
    provider_override: str | LLMProviderType | None = None,
) -> LLMBatchingMode:
    """Determine the batching mode after applying overrides and guardrails."""

    requested_mode = (
        batch_config_overrides.llm_batching_mode_override
        if batch_config_overrides and batch_config_overrides.llm_batching_mode_override
        else settings.LLM_BATCHING_MODE
    )

    if requested_mode is not LLMBatchingMode.PROVIDER_BATCH_API:
        return requested_mode

    resolved_provider = _normalize_provider_type(provider_override) or settings.DEFAULT_LLM_PROVIDER
    allowed = getattr(settings, "LLM_BATCH_API_ALLOWED_PROVIDERS", []) or []

    if allowed and resolved_provider not in allowed:
        fallback_mode = settings.LLM_BATCHING_MODE
        if fallback_mode is LLMBatchingMode.PROVIDER_BATCH_API:
            fallback_mode = LLMBatchingMode.SERIAL_BUNDLE
        if fallback_mode is LLMBatchingMode.PROVIDER_BATCH_API:
            fallback_mode = LLMBatchingMode.PER_REQUEST
        logger.warning(
            "provider_batch_api mode skipped because provider is not allowed",
            extra={
                "resolved_provider": resolved_provider.value,
                "allowed_providers": [provider.value for provider in allowed],
                "selected_fallback_mode": fallback_mode.value,
            },
        )
        return fallback_mode

    return requested_mode


def build_llm_metadata_context(
    *,
    cj_batch_id: int,
    cj_source: str | None,
    cj_request_type: str | None,
    settings: Settings,
    effective_mode: LLMBatchingMode,
    iteration_metadata_context: dict[str, Any] | None,
) -> dict[str, Any]:
    """Build metadata passed to LLM requests, ensuring checklist coverage."""

    metadata: dict[str, Any] = {
        "cj_batch_id": str(cj_batch_id),
        "cj_source": cj_source or "els",
        "cj_request_type": cj_request_type or "cj_comparison",
    }

    if settings.ENABLE_LLM_BATCHING_METADATA_HINTS:
        metadata["cj_llm_batching_mode"] = effective_mode.value

    if iteration_metadata_context:
        metadata.update(iteration_metadata_context)

    return metadata
