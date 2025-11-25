"""Helper utilities for LLM override handling."""

from __future__ import annotations

from typing import Any, Dict

from common_core import LLMProviderType

from services.llm_provider_service.config import Settings
from services.llm_provider_service.queue_models import QueuedRequest


def build_override_kwargs(request: QueuedRequest) -> Dict[str, Any]:
    """Create overrides dict for comparison processor calls."""

    overrides: Dict[str, Any] = {}
    config = request.request_data.llm_config_overrides
    if not config:
        return overrides

    if config.model_override:
        overrides["model_override"] = config.model_override
    if config.temperature_override is not None:
        overrides["temperature_override"] = config.temperature_override
    if config.system_prompt_override:
        overrides["system_prompt_override"] = config.system_prompt_override
    if config.max_tokens_override is not None:
        overrides["max_tokens_override"] = config.max_tokens_override

    return overrides


def resolve_provider_from_request(request: QueuedRequest, settings: Settings) -> LLMProviderType:
    """Determine which provider should service the request."""

    overrides = request.request_data.llm_config_overrides
    if overrides and overrides.provider_override:
        return overrides.provider_override
    return getattr(settings, "DEFAULT_LLM_PROVIDER", LLMProviderType.OPENAI)


def get_cj_batching_mode_hint(request: QueuedRequest) -> str | None:
    """Return the CJ-provided batching hint if present."""

    metadata = request.request_data.metadata or {}
    hint = metadata.get("cj_llm_batching_mode")
    if isinstance(hint, str):
        return hint
    return None


def requests_are_compatible(
    *,
    base_provider: LLMProviderType,
    candidate_provider: LLMProviderType,
    base_overrides: Dict[str, Any],
    candidate_overrides: Dict[str, Any],
    base_hint: str | None,
    candidate_hint: str | None,
) -> bool:
    """Determine if two requests can be bundled together."""

    if candidate_provider is not base_provider:
        return False

    if base_overrides != candidate_overrides:
        return False

    if base_hint is None and candidate_hint is None:
        return True

    return base_hint == candidate_hint
