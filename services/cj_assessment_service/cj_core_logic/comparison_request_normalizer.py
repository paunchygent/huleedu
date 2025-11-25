from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from services.cj_assessment_service.cj_core_logic.batch_config import BatchConfigOverrides
from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.models_api import CJAssessmentRequestData


@dataclass
class NormalizedComparisonRequest:
    llm_config_overrides: Any | None
    batch_config_overrides: BatchConfigOverrides | None
    system_prompt_override: str
    model_override: str | None
    temperature_override: float | None
    max_tokens_override: int | None
    provider_override: str | None
    max_pairs_cap: int
    budget_source: str

    def budget_metadata(self) -> dict[str, Any]:
        metadata: dict[str, Any] = {
            "comparison_budget": {
                "max_pairs_requested": self.max_pairs_cap,
                "source": self.budget_source,
            }
        }
        if self.batch_config_overrides:
            metadata["config_overrides"] = self.batch_config_overrides.model_dump(exclude_none=True)
        return metadata


class ComparisonRequestNormalizer:
    """Normalize overrides and comparison budget inputs."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def normalize(self, request_data: CJAssessmentRequestData) -> NormalizedComparisonRequest:
        llm_config_overrides = request_data.llm_config_overrides
        model_override = None
        temperature_override = None
        max_tokens_override = None
        provider_override = None
        system_prompt_override = self.settings.SYSTEM_PROMPT

        if llm_config_overrides:
            model_override = llm_config_overrides.model_override
            temperature_override = llm_config_overrides.temperature_override
            max_tokens_override = llm_config_overrides.max_tokens_override
            provider_override = llm_config_overrides.provider_override
            if llm_config_overrides.system_prompt_override is not None:
                system_prompt_override = llm_config_overrides.system_prompt_override

        batch_config_overrides = None
        if request_data.batch_config_overrides is not None:
            batch_config_overrides = BatchConfigOverrides(**request_data.batch_config_overrides)

        max_pairs_cap = self._resolve_requested_max_pairs(request_data)
        budget_source = (
            "runner_override" if request_data.max_comparisons_override else "service_default"
        )

        return NormalizedComparisonRequest(
            llm_config_overrides=llm_config_overrides,
            batch_config_overrides=batch_config_overrides,
            system_prompt_override=system_prompt_override,
            model_override=model_override,
            temperature_override=temperature_override,
            max_tokens_override=max_tokens_override,
            provider_override=provider_override,
            max_pairs_cap=max_pairs_cap,
            budget_source=budget_source,
        )

    def _resolve_requested_max_pairs(self, request_data: CJAssessmentRequestData) -> int:
        configured_cap = self.settings.MAX_PAIRWISE_COMPARISONS
        override_value = request_data.max_comparisons_override
        try:
            override_int = int(override_value) if override_value is not None else None
        except (TypeError, ValueError):
            override_int = None

        if override_int and override_int > 0:
            return min(configured_cap, override_int) if configured_cap else override_int
        return configured_cap
