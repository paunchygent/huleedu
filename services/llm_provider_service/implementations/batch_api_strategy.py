"""Batch API strategy for queued LLM requests.

This module isolates the BatchApiStrategy implementation so that
request_strategies.py can remain focused on per-request and serial
bundle execution paths. The strategy reuses the same compatibility
and bundling rules as SerialBundleStrategy but delegates execution
to a BatchJobManagerProtocol implementation.
"""

from __future__ import annotations

import time
from typing import Any, List, Optional

from common_core import LLMProviderType, QueueStatus
from huleedu_service_libs.logging_utils import create_service_logger

from services.llm_provider_service.config import Settings
from services.llm_provider_service.exceptions import (
    HuleEduError,
    raise_processing_error,
)
from services.llm_provider_service.implementations.execution_result_handler import (
    ExecutionResultHandler,
)
from services.llm_provider_service.implementations.llm_override_utils import (
    build_override_kwargs,
    get_cj_batching_mode_hint,
    get_preferred_bundle_size_hint,
    requests_are_compatible,
    resolve_provider_from_request,
)
from services.llm_provider_service.implementations.queue_processor_metrics import (
    QueueProcessorMetrics,
)
from services.llm_provider_service.implementations.queue_tracing_enricher import (
    QueueTracingEnricher,
)
from services.llm_provider_service.implementations.queue_ttl_utils import is_request_expired
from services.llm_provider_service.internal_models import (
    BatchJobItem,
    BatchJobItemStatus,
)
from services.llm_provider_service.protocols import (
    BatchJobManagerProtocol,
    ComparisonProcessorProtocol,
)
from services.llm_provider_service.queue_models import QueuedRequest

logger = create_service_logger("llm_provider_service.batch_api_strategy")


class ExecutionOutcome:
    """Lightweight outcome container (mirrors request_strategies.ExecutionOutcome)."""

    def __init__(
        self,
        request: QueuedRequest,
        provider: LLMProviderType,
        result: str,
        processing_started: float | None,
    ) -> None:
        self.request = request
        self.provider = provider
        self.result = result
        self.processing_started = processing_started


class SerialBundleResult:
    """Result container (mirrors request_strategies.SerialBundleResult)."""

    def __init__(
        self,
        outcomes: List[ExecutionOutcome],
        pending_request: Optional[QueuedRequest] = None,
    ) -> None:
        self.outcomes = outcomes
        self.pending_request = pending_request


class BatchApiStrategy:
    """Strategy for processing queued requests via provider-native batch jobs."""

    def __init__(
        self,
        *,
        comparison_processor: ComparisonProcessorProtocol,
        result_handler: ExecutionResultHandler,
        trace_context_manager: Any,
        settings: Settings,
        metrics: QueueProcessorMetrics,
        tracing_enricher: QueueTracingEnricher,
        batch_job_manager: BatchJobManagerProtocol,
    ) -> None:
        self.comparison_processor = comparison_processor
        self.result_handler = result_handler
        self.trace_context_manager = trace_context_manager
        self.settings = settings
        self.metrics = metrics
        self.tracing_enricher = tracing_enricher
        self.batch_job_manager = batch_job_manager

    async def execute(self, first_request: QueuedRequest) -> SerialBundleResult:
        """Bundle compatible requests into a batch job and process via job manager."""

        bundle_requests: list[QueuedRequest] = []
        processing_started: dict[str, float] = {}
        outcomes: list[ExecutionOutcome] = []

        primary_provider = resolve_provider_from_request(first_request, self.settings)
        primary_overrides = build_override_kwargs(first_request)
        primary_hint = get_cj_batching_mode_hint(first_request)
        preferred_bundle_size = get_preferred_bundle_size_hint(first_request)

        max_requests = self.settings.SERIAL_BUNDLE_MAX_REQUESTS_PER_CALL
        effective_limit = max_requests
        if preferred_bundle_size is not None and preferred_bundle_size > 0:
            effective_limit = min(preferred_bundle_size, max_requests)
        effective_limit = max(1, effective_limit)

        self.tracing_enricher.enrich_request_metadata(
            first_request,
            provider=primary_provider,
            model=primary_overrides.get("model_override"),
        )
        self.metrics.record_prompt_block_metrics(
            request=first_request,
            provider=primary_provider,
            model=primary_overrides.get("model_override") or "default",
        )

        processing_started[str(first_request.queue_id)] = time.perf_counter()
        await self.result_handler.queue_manager.update_status(
            queue_id=first_request.queue_id,
            status=QueueStatus.PROCESSING,
        )
        bundle_requests.append(first_request)

        pending_request: Optional[QueuedRequest] = None
        while len(bundle_requests) < effective_limit:
            next_request = await self.result_handler.queue_manager.dequeue()
            if not next_request:
                break

            if is_request_expired(next_request):
                await self.result_handler.handle_expired_request(next_request)
                expired_provider = resolve_provider_from_request(next_request, self.settings)
                self.metrics.record_expiry_metrics(
                    request=next_request,
                    provider=expired_provider,
                    expiry_reason="ttl",
                )
                outcomes.append(
                    ExecutionOutcome(
                        request=next_request,
                        provider=expired_provider,
                        result="expired",
                        processing_started=None,
                    )
                )
                continue

            candidate_provider = resolve_provider_from_request(next_request, self.settings)
            candidate_overrides = build_override_kwargs(next_request)
            candidate_hint = get_cj_batching_mode_hint(next_request)

            if not requests_are_compatible(
                base_provider=primary_provider,
                candidate_provider=candidate_provider,
                base_overrides=primary_overrides,
                candidate_overrides=candidate_overrides,
                base_hint=primary_hint,
                candidate_hint=candidate_hint,
            ):
                pending_request = next_request
                break

            self.tracing_enricher.enrich_request_metadata(
                next_request,
                provider=candidate_provider,
                model=candidate_overrides.get("model_override"),
            )
            self.metrics.record_prompt_block_metrics(
                request=next_request,
                provider=candidate_provider,
                model=candidate_overrides.get("model_override") or "default",
            )

            processing_started[str(next_request.queue_id)] = time.perf_counter()
            await self.result_handler.queue_manager.update_status(
                queue_id=next_request.queue_id,
                status=QueueStatus.PROCESSING,
            )
            bundle_requests.append(next_request)

        queue_mode_label = self.settings.QUEUE_PROCESSING_MODE.value
        logger.info(
            "batch_api_job_dispatch",
            extra={
                "bundle_size": len(bundle_requests),
                "queue_processing_mode": queue_mode_label,
                "provider": primary_provider.value,
                "model_override": primary_overrides.get("model_override"),
                "cj_llm_batching_mode": primary_hint,
            },
        )

        model_label = primary_overrides.get("model_override") or "default"
        job_started = time.perf_counter()
        self.metrics.record_batch_api_job_scheduled(
            provider=primary_provider,
            model_override=model_label,
            bundle_size=len(bundle_requests),
        )

        job_items: list[BatchJobItem] = []
        for request in bundle_requests:
            overrides = build_override_kwargs(request)
            job_items.append(
                BatchJobItem(
                    queue_id=request.queue_id,
                    provider=primary_provider,
                    model=model_label,
                    custom_id=str(request.queue_id),
                    user_prompt=request.request_data.user_prompt,
                    prompt_blocks=request.request_data.prompt_blocks,
                    correlation_id=request.request_data.correlation_id or request.queue_id,
                    overrides=overrides,
                    metadata=request.request_data.metadata or {},
                )
            )

        try:
            job_ref = await self.batch_job_manager.schedule_job(
                provider=primary_provider,
                model=model_label,
                items=job_items,
            )
            results = await self.batch_job_manager.collect_results(job_ref)
        except Exception as exc:  # pragma: no cover - defensive guard for job manager
            logger.error(
                "BATCH_API job processing failed",
                exc_info=True,
                extra={
                    "queue_processing_mode": "batch_api",
                    "bundle_size": len(bundle_requests),
                    "provider": primary_provider.value,
                    "error": str(exc),
                },
            )
            self.metrics.record_batch_api_job_completed(
                provider=primary_provider,
                model_override=model_label,
                job_started=job_started,
                status="failed",
            )
            try:
                raise_processing_error(
                    service="llm_provider_service",
                    operation="batch_api_processing",
                    message=str(exc),
                    correlation_id=first_request.request_data.correlation_id
                    or first_request.queue_id,
                    details={
                        "provider": primary_provider.value,
                        "bundle_size": len(bundle_requests),
                    },
                )
            except HuleEduError as processing_error:
                for queued_request in bundle_requests:
                    await self.result_handler.handle_request_hule_error(
                        queued_request, processing_error
                    )
                    outcomes.append(
                        ExecutionOutcome(
                            request=queued_request,
                            provider=primary_provider,
                            result="failure",
                            processing_started=processing_started[str(queued_request.queue_id)],
                        )
                    )
            return SerialBundleResult(outcomes=outcomes, pending_request=pending_request)

        self.metrics.record_batch_api_job_completed(
            provider=primary_provider,
            model_override=model_label,
            job_started=job_started,
            status="completed",
        )

        results_by_queue_id = {result.queue_id: result for result in results}
        for queued_request in bundle_requests:
            result = results_by_queue_id.get(queued_request.queue_id)
            if result is None:
                try:
                    raise_processing_error(
                        service="llm_provider_service",
                        operation="batch_api_processing",
                        message="Missing job result for queued request",
                        correlation_id=queued_request.request_data.correlation_id
                        or queued_request.queue_id,
                        details={"queue_id": str(queued_request.queue_id)},
                    )
                except HuleEduError as processing_error:
                    await self.result_handler.handle_request_hule_error(
                        queued_request, processing_error
                    )
                    outcomes.append(
                        ExecutionOutcome(
                            request=queued_request,
                            provider=primary_provider,
                            result="failure",
                            processing_started=processing_started[str(queued_request.queue_id)],
                        )
                    )
                continue

            if result.status is BatchJobItemStatus.SUCCESS and result.response is not None:
                await self.result_handler.handle_request_success(queued_request, result.response)
                outcomes.append(
                    ExecutionOutcome(
                        request=queued_request,
                        provider=result.response.provider,
                        result="success",
                        processing_started=processing_started[str(queued_request.queue_id)],
                    )
                )
            else:
                message = result.error_message or "Batch API item failed"
                try:
                    raise_processing_error(
                        service="llm_provider_service",
                        operation="batch_api_processing",
                        message=message,
                        correlation_id=queued_request.request_data.correlation_id
                        or queued_request.queue_id,
                        details={
                            "queue_id": str(queued_request.queue_id),
                            "provider": result.provider.value,
                            "model": result.model,
                        },
                    )
                except HuleEduError as processing_error:
                    await self.result_handler.handle_request_hule_error(
                        queued_request, processing_error
                    )
                    outcomes.append(
                        ExecutionOutcome(
                            request=queued_request,
                            provider=primary_provider,
                            result="failure",
                            processing_started=processing_started[str(queued_request.queue_id)],
                        )
                    )

        return SerialBundleResult(outcomes=outcomes, pending_request=pending_request)
