"""Composable metrics helpers for the queue processor."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Dict

from common_core import LLMProviderType
from huleedu_service_libs.logging_utils import create_service_logger

from services.llm_provider_service.config import QueueProcessingMode
from services.llm_provider_service.implementations.queue_ttl_utils import normalize_ttl_label
from services.llm_provider_service.protocols import QueueManagerProtocol
from services.llm_provider_service.queue_models import QueuedRequest

logger = create_service_logger("llm_provider_service.queue_metrics")


class QueueProcessorMetrics:
    """Encapsulates all metrics emission for queue processing."""

    _QUEUE_METRICS_LOG_INTERVAL_SECONDS = 30.0

    def __init__(
        self,
        *,
        queue_metrics: Dict[str, Any] | None,
        llm_metrics: Dict[str, Any] | None,
        queue_processing_mode: QueueProcessingMode,
    ) -> None:
        self.queue_metrics = queue_metrics
        self.llm_metrics = llm_metrics
        self.queue_processing_mode = queue_processing_mode
        self._last_queue_metrics_log = 0.0

    async def record_queue_stats(self, queue_manager: QueueManagerProtocol) -> None:
        """Update Prometheus gauges and emit periodic queue logs."""

        if not self.queue_metrics:
            return

        depth_gauge = self.queue_metrics.get("llm_queue_depth")
        if depth_gauge is None:
            return

        try:
            stats = await queue_manager.get_queue_stats()
        except Exception:  # pragma: no cover - defensive logging only
            return

        depth_gauge.labels(queue_type="total").set(stats.current_size)
        depth_gauge.labels(queue_type="queued").set(stats.queued_count)

        now = time.time()
        if (
            self.queue_processing_mode is not QueueProcessingMode.PER_REQUEST
            and now - self._last_queue_metrics_log >= self._QUEUE_METRICS_LOG_INTERVAL_SECONDS
        ):
            logger.info(
                "queue_metrics_snapshot",
                extra={
                    "queue_processing_mode": self.queue_processing_mode.value,
                    "queue_current_size": stats.current_size,
                    "queue_queued_count": stats.queued_count,
                    "queue_usage_percent": round(stats.usage_percent, 2),
                    "accepting_requests": stats.is_accepting_requests,
                },
            )
            self._last_queue_metrics_log = now

    def record_expiry_metrics(
        self,
        *,
        request: QueuedRequest,
        provider: LLMProviderType,
        expiry_reason: str,
    ) -> None:
        """Record dedicated metrics for expired queue requests."""

        if not self.queue_metrics:
            return

        expiry_counter = self.queue_metrics.get("llm_queue_expiry_total")
        expiry_age_hist = self.queue_metrics.get("llm_queue_expiry_age_seconds")

        age_seconds = max(
            (datetime.now(timezone.utc) - request.queued_at).total_seconds(),
            0.0,
        )

        if expiry_counter is not None:
            expiry_counter.labels(
                provider=provider.value,
                queue_processing_mode=self.queue_processing_mode.value,
                expiry_reason=expiry_reason,
            ).inc()

        if expiry_age_hist is not None:
            expiry_age_hist.labels(
                provider=provider.value,
                queue_processing_mode=self.queue_processing_mode.value,
            ).observe(age_seconds)

    def record_completion_metrics(
        self,
        *,
        provider: LLMProviderType,
        result: str,
        request: QueuedRequest,
        processing_started: float | None,
    ) -> None:
        """Record per-request timing metrics for queue processing."""

        if not self.queue_metrics:
            return

        wait_hist = self.queue_metrics.get("llm_queue_wait_time_seconds")
        if wait_hist is not None:
            wait_seconds = max(
                (datetime.now(timezone.utc) - request.queued_at).total_seconds(),
                0.0,
            )
            wait_hist.labels(
                queue_processing_mode=self.queue_processing_mode.value,
                result=result,
            ).observe(wait_seconds)

        if processing_started is None or result not in {"success", "failure"}:
            return

        proc_hist = self.queue_metrics.get("llm_queue_processing_time_seconds")
        if proc_hist is not None:
            duration = max(time.perf_counter() - processing_started, 0.0)
            proc_hist.labels(provider=provider.value, status=result).observe(duration)

        callbacks_counter = self.queue_metrics.get("llm_comparison_callbacks_total")
        if callbacks_counter is not None:
            callbacks_counter.labels(
                queue_processing_mode=self.queue_processing_mode.value,
                result=result,
            ).inc()

    def record_prompt_block_metrics(
        self,
        *,
        request: QueuedRequest,
        provider: LLMProviderType,
        model: str,
    ) -> None:
        """Record block-level and token-distribution metrics for observability."""

        if not self.llm_metrics:
            return

        block_counter = self.llm_metrics.get("llm_provider_prompt_blocks_total")
        token_hist = self.llm_metrics.get("llm_provider_prompt_tokens_histogram")

        blocks = request.request_data.prompt_blocks or []
        provider_label = provider.value
        model_label = model or "default"

        if not blocks and block_counter is not None:
            block_counter.labels(
                provider=provider_label,
                model=model_label,
                target="legacy_user_prompt",
                cacheable="false",
                ttl="none",
            ).inc()

        static_tokens = 0
        dynamic_tokens = 0

        for block in blocks:
            target = str(block.get("target") or "user_content")
            cacheable = "true" if block.get("cacheable") else "false"
            ttl_label = normalize_ttl_label(block.get("ttl"))
            if block_counter is not None:
                block_counter.labels(
                    provider=provider_label,
                    model=model_label,
                    target=target,
                    cacheable=cacheable,
                    ttl=ttl_label,
                ).inc()

            content_text = str(block.get("content") or "")
            if block.get("cacheable"):
                static_tokens += self._estimate_tokens(content_text)
            else:
                dynamic_tokens += self._estimate_tokens(content_text)

        if token_hist is not None:
            if blocks:
                token_hist.labels(
                    provider=provider_label, model=model_label, section="static"
                ).observe(static_tokens)
                token_hist.labels(
                    provider=provider_label, model=model_label, section="dynamic"
                ).observe(dynamic_tokens)
            else:
                token_hist.labels(
                    provider=provider_label, model=model_label, section="legacy"
                ).observe(self._estimate_tokens(request.request_data.user_prompt))

    def record_cache_scope_metrics(
        self,
        *,
        request: QueuedRequest,
        result: Any,
    ) -> None:
        """Record cache outcomes by scope (assignment vs ad-hoc)."""

        if not self.llm_metrics:
            return

        scope_counter = self.llm_metrics.get("llm_provider_cache_scope_total")
        if scope_counter is None:
            return

        metadata = request.request_data.metadata or {}
        scope = self._detect_scope(metadata)
        provider_label = getattr(result.provider, "value", "unknown")
        model_label = getattr(result, "model", None) or "unknown"

        usage: Dict[str, Any] = {}
        if isinstance(getattr(result, "metadata", None), dict):
            usage = result.metadata.get("usage") or {}
            if "cache_read_input_tokens" in result.metadata:
                usage.setdefault(
                    "cache_read_input_tokens", result.metadata.get("cache_read_input_tokens")
                )
            if "cache_creation_input_tokens" in result.metadata:
                usage.setdefault(
                    "cache_creation_input_tokens",
                    result.metadata.get("cache_creation_input_tokens"),
                )

        cache_read_tokens = int(usage.get("cache_read_input_tokens") or 0)
        cache_write_tokens = int(usage.get("cache_creation_input_tokens") or 0)

        if cache_read_tokens > 0:
            outcome = "hit"
        elif cache_write_tokens > 0:
            outcome = "miss"
        else:
            outcome = "bypass"

        scope_counter.labels(
            provider=provider_label, model=model_label, scope=scope, result=outcome
        ).inc()

    def record_serial_bundle_metrics(
        self,
        *,
        provider: LLMProviderType,
        model_override: str,
        bundle_size: int,
    ) -> None:
        """Record metrics specific to serial bundle dispatch."""

        if not self.queue_metrics:
            return

        bundle_calls = self.queue_metrics.get("llm_serial_bundle_calls_total")
        bundle_items_hist = self.queue_metrics.get("llm_serial_bundle_items_per_call")

        if bundle_calls is not None:
            bundle_calls.labels(provider=provider.value, model=model_override).inc()
        if bundle_items_hist is not None:
            bundle_items_hist.labels(
                provider=provider.value,
                model=model_override,
            ).observe(bundle_size)

    def record_batch_api_job_scheduled(
        self,
        *,
        provider: LLMProviderType,
        model_override: str,
        bundle_size: int,
    ) -> None:
        """Record metrics when a batch API job is scheduled."""

        if not self.queue_metrics:
            return

        jobs_counter = self.queue_metrics.get("llm_batch_api_jobs_total")
        items_hist = self.queue_metrics.get("llm_batch_api_items_per_job")

        if jobs_counter is not None:
            jobs_counter.labels(
                provider=provider.value,
                model=model_override,
                status="scheduled",
            ).inc()

        if items_hist is not None:
            items_hist.labels(
                provider=provider.value,
                model=model_override,
            ).observe(bundle_size)

    def record_batch_api_job_completed(
        self,
        *,
        provider: LLMProviderType,
        model_override: str,
        job_started: float | None,
        status: str,
    ) -> None:
        """Record metrics when a batch API job completes or fails."""

        if not self.queue_metrics:
            return

        jobs_counter = self.queue_metrics.get("llm_batch_api_jobs_total")
        duration_hist = self.queue_metrics.get("llm_batch_api_job_duration_seconds")

        if jobs_counter is not None:
            jobs_counter.labels(
                provider=provider.value,
                model=model_override,
                status=status,
            ).inc()

        if duration_hist is not None and job_started is not None:
            duration = max(time.perf_counter() - job_started, 0.0)
            duration_hist.labels(
                provider=provider.value,
                model=model_override,
            ).observe(duration)

    @staticmethod
    def _detect_scope(metadata: Dict[str, Any]) -> str:
        """Infer request scope for cache observability."""

        if not metadata:
            return "unknown"

        if metadata.get("assignment_id") or metadata.get("assignmentId"):
            return "assignment"

        if metadata.get("bos_batch_id") or metadata.get("cj_batch_id"):
            return "assignment"

        return "adhoc"

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """Lightweight token estimator (word count heuristic)."""

        if not text:
            return 0
        return max(len(text.split()), 0)
