from __future__ import annotations

from typing import Any

from common_core.config_enums import LLMBatchingMode
from huleedu_service_libs.logging_utils import create_service_logger

from services.cj_assessment_service.cj_core_logic.llm_batching import (
    build_llm_metadata_context,
    resolve_effective_llm_batching_mode,
)
from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.metrics import get_business_metrics

logger = create_service_logger("cj_assessment_service.llm_batching_service")


class BatchingModeService:
    """Handle batching mode selection and metrics emission."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def resolve_effective_mode(
        self, *, batch_config_overrides: Any | None, provider_override: str | None
    ) -> LLMBatchingMode:
        return resolve_effective_llm_batching_mode(
            settings=self.settings,
            batch_config_overrides=batch_config_overrides,
            provider_override=provider_override,
        )

    def build_iteration_metadata_context(
        self, *, current_iteration: int | None
    ) -> dict[str, Any] | None:
        if not (
            self.settings.ENABLE_LLM_BATCHING_METADATA_HINTS and self.is_iterative_batching_online()
        ):
            return None
        iteration_value = current_iteration if current_iteration is not None else 0
        return {"comparison_iteration": iteration_value}

    def is_iterative_batching_online(self) -> bool:
        """Return True when stability-driven, multi-iteration batching is effectively enabled.

        This helper derives its state from core configuration knobs instead of a separate
        feature flag to keep behaviour aligned with documented convergence settings.
        """

        return (
            self.settings.LLM_BATCHING_MODE is not LLMBatchingMode.PER_REQUEST
            and getattr(self.settings, "MAX_ITERATIONS", 1) > 1
            and getattr(self.settings, "MIN_COMPARISONS_FOR_STABILITY_CHECK", 0) > 0
            and getattr(self.settings, "COMPARISONS_PER_STABILITY_CHECK_ITERATION", 0) > 1
        )

    def build_metadata_context(
        self,
        *,
        cj_batch_id: int,
        cj_source: str,
        cj_request_type: str,
        effective_mode: LLMBatchingMode,
        iteration_metadata_context: dict[str, Any] | None,
    ) -> dict[str, Any]:
        return build_llm_metadata_context(
            cj_batch_id=cj_batch_id,
            cj_source=cj_source,
            cj_request_type=cj_request_type,
            settings=self.settings,
            effective_mode=effective_mode,
            iteration_metadata_context=iteration_metadata_context,
        )

    def record_metrics(
        self, *, effective_mode: LLMBatchingMode, request_count: int, request_type: str | None
    ) -> None:
        try:
            business_metrics = get_business_metrics()
        except Exception:  # pragma: no cover - defensive
            logger.debug("Unable to retrieve business metrics for batching counters", exc_info=True)
            return

        requests_metric = business_metrics.get("cj_llm_requests_total")
        batches_metric = business_metrics.get("cj_llm_batches_started_total")

        if requests_metric and request_count > 0:
            try:
                requests_metric.labels(batching_mode=effective_mode.value).inc(request_count)
            except Exception:  # pragma: no cover - defensive
                logger.debug("Unable to increment cj_llm_requests_total metric", exc_info=True)

        if request_type == "cj_comparison" and batches_metric:
            try:
                batches_metric.labels(batching_mode=effective_mode.value).inc()
            except Exception:  # pragma: no cover - defensive
                logger.debug(
                    "Unable to increment cj_llm_batches_started_total metric", exc_info=True
                )
