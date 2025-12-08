"""Strategies for executing queued LLM requests."""

from __future__ import annotations

import abc
import time
from dataclasses import dataclass
from typing import Any, List, Optional

from common_core import LLMProviderType, QueueStatus
from huleedu_service_libs.logging_utils import create_service_logger

from services.llm_provider_service.config import QueueProcessingMode, Settings
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
    BatchComparisonItem,
    LLMOrchestratorResponse,
    LLMQueuedResult,
)
from services.llm_provider_service.protocols import (
    ComparisonProcessorProtocol,
)
from services.llm_provider_service.queue_models import QueuedRequest

logger = create_service_logger("llm_provider_service.queue_strategies")


@dataclass
class ExecutionOutcome:
    request: QueuedRequest
    provider: LLMProviderType
    result: str
    processing_started: float | None


@dataclass
class SerialBundleResult:
    outcomes: List[ExecutionOutcome]
    pending_request: Optional[QueuedRequest] = None


class RequestExecutionStrategy(abc.ABC):
    """Abstract base strategy for executing queued requests."""

    def __init__(
        self,
        *,
        comparison_processor: ComparisonProcessorProtocol,
        result_handler: ExecutionResultHandler,
        trace_context_manager: Any,
        settings: Settings,
        metrics: QueueProcessorMetrics,
        tracing_enricher: QueueTracingEnricher,
    ) -> None:
        self.comparison_processor = comparison_processor
        self.result_handler = result_handler
        self.trace_context_manager = trace_context_manager
        self.settings = settings
        self.metrics = metrics
        self.tracing_enricher = tracing_enricher

    @abc.abstractmethod
    async def execute(self, request: QueuedRequest) -> ExecutionOutcome | SerialBundleResult:
        """Execute the request(s) according to the strategy."""
        pass


class SingleRequestStrategy(RequestExecutionStrategy):
    """Strategy for processing a single queued request."""

    async def execute(self, request: QueuedRequest) -> ExecutionOutcome:
        processing_started = time.perf_counter()
        provider = resolve_provider_from_request(request, self.settings)
        overrides = build_override_kwargs(request)
        model_hint = overrides.get("model_override")

        self.tracing_enricher.enrich_request_metadata(request, provider=provider, model=model_hint)
        self.metrics.record_prompt_block_metrics(
            request=request, provider=provider, model=model_hint or "default"
        )

        await self.result_handler.queue_manager.update_status(
            queue_id=request.queue_id,
            status=QueueStatus.PROCESSING,
        )

        try:
            trace_context = request.trace_context or {}
            with self.trace_context_manager.restore_trace_context_for_queue_processing(
                trace_context, request.queue_id
            ) as span:
                span.add_event(
                    "queue_request_processing_started",
                    {
                        "queue_id": str(request.queue_id),
                        "correlation_id": str(
                            request.request_data.correlation_id or request.queue_id
                        ),
                        "provider": provider.value,
                    },
                )

                result: LLMOrchestratorResponse | LLMQueuedResult
                result = await self.comparison_processor.process_comparison(
                    provider=provider,
                    user_prompt=request.request_data.user_prompt,
                    prompt_blocks=request.request_data.prompt_blocks,
                    correlation_id=request.request_data.correlation_id or request.queue_id,
                    **overrides,
                )

            if isinstance(result, LLMOrchestratorResponse):
                await self.result_handler.handle_request_success(request, result)
                return ExecutionOutcome(
                    request=request,
                    provider=result.provider,
                    result="success",
                    processing_started=processing_started,
                )

            if isinstance(result, LLMQueuedResult):
                raise_processing_error(
                    service="llm_provider_service",
                    operation="queue_request_processing",
                    message="Unexpected queued result during queue processing",
                    correlation_id=request.request_data.correlation_id or request.queue_id,
                    details={
                        "provider": provider.value,
                        "queue_id": str(request.queue_id),
                    },
                )

            raise_processing_error(
                service="llm_provider_service",
                operation="queue_request_processing",
                message="Unexpected processing result type",
                correlation_id=request.request_data.correlation_id or request.queue_id,
                details={"provider": provider.value, "result_type": str(type(result))},
            )

        except HuleEduError as error:
            await self.result_handler.handle_request_hule_error(request, error)
            return ExecutionOutcome(
                request=request,
                provider=provider,
                result="failure",
                processing_started=processing_started,
            )
        except Exception as exc:  # pragma: no cover - defensive logging
            try:
                raise_processing_error(
                    service="llm_provider_service",
                    operation="queue_request_processing",
                    message=f"Processing failed: {str(exc)}",
                    correlation_id=request.request_data.correlation_id or request.queue_id,
                    details={
                        "provider": provider.value,
                        "queue_id": str(request.queue_id),
                    },
                )
            except HuleEduError as processing_error:
                await self.result_handler.handle_request_hule_error(request, processing_error)
            return ExecutionOutcome(
                request=request,
                provider=provider,
                result="failure",
                processing_started=processing_started,
            )


class SerialBundleStrategy(RequestExecutionStrategy):
    """Strategy for processing multiple queued requests in a serial bundle."""

    async def execute(self, first_request: QueuedRequest) -> SerialBundleResult:
        bundle_requests: list[QueuedRequest] = []
        batch_items: list[BatchComparisonItem] = []
        processing_started: dict[str, float] = {}
        outcomes: list[ExecutionOutcome] = []

        primary_provider = resolve_provider_from_request(first_request, self.settings)
        primary_overrides = build_override_kwargs(first_request)
        primary_hint = get_cj_batching_mode_hint(first_request)
        preferred_bundle_size = get_preferred_bundle_size_hint(first_request)

        # Respect any caller-provided preferred bundle size hint, but never
        # exceed the configured SERIAL_BUNDLE_MAX_REQUESTS_PER_CALL. When no
        # hint is provided, fall back to the configured limit.
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
        batch_items.append(
            BatchComparisonItem(
                provider=primary_provider,
                user_prompt=first_request.request_data.user_prompt,
                prompt_blocks=first_request.request_data.prompt_blocks,
                correlation_id=first_request.request_data.correlation_id or first_request.queue_id,
                overrides=primary_overrides or None,
            )
        )

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
            batch_items.append(
                BatchComparisonItem(
                    provider=candidate_provider,
                    user_prompt=next_request.request_data.user_prompt,
                    prompt_blocks=next_request.request_data.prompt_blocks,
                    correlation_id=next_request.request_data.correlation_id
                    or next_request.queue_id,
                    overrides=candidate_overrides or None,
                )
            )

        logger.info(
            "serial_bundle_dispatch",
            extra={
                "bundle_size": len(bundle_requests),
                "queue_processing_mode": "serial_bundle",
                "provider": primary_provider.value,
                "model_override": primary_overrides.get("model_override"),
                "cj_llm_batching_mode": primary_hint,
            },
        )

        try:
            start_time = time.monotonic()
            batch_results = await self.comparison_processor.process_comparison_batch(batch_items)
            duration_ms = (time.monotonic() - start_time) * 1000

            if self.settings.QUEUE_PROCESSING_MODE is QueueProcessingMode.SERIAL_BUNDLE:
                self.metrics.record_serial_bundle_metrics(
                    provider=primary_provider,
                    model_override=primary_overrides.get("model_override") or "unknown",
                    bundle_size=len(bundle_requests),
                )

            if duration_ms > 30000:
                logger.warning(
                    "Serial bundle processing took >30s",
                    extra={
                        "duration_ms": duration_ms,
                        "bundle_size": len(bundle_requests),
                        "provider": primary_provider.value,
                        "queue_processing_mode": "serial_bundle",
                    },
                )

            if len(batch_results) != len(bundle_requests):
                raise_processing_error(
                    service="llm_provider_service",
                    operation="serial_bundle_processing",
                    message="Batch processor returned mismatched result count",
                    correlation_id=first_request.request_data.correlation_id
                    or first_request.queue_id,
                    details={
                        "expected": len(bundle_requests),
                        "actual": len(batch_results),
                        "queue_processing_mode": "serial_bundle",
                        "duration_ms": duration_ms,
                    },
                )

            for queued_request, result in zip(bundle_requests, batch_results, strict=True):
                if isinstance(result, LLMOrchestratorResponse):
                    await self.result_handler.handle_request_success(queued_request, result)
                    outcomes.append(
                        ExecutionOutcome(
                            request=queued_request,
                            provider=result.provider,
                            result="success",
                            processing_started=processing_started[str(queued_request.queue_id)],
                        )
                    )
                elif isinstance(result, LLMQueuedResult):
                    raise_processing_error(
                        service="llm_provider_service",
                        operation="serial_bundle_processing",
                        message="Unexpected queued result in serial bundle path",
                        correlation_id=queued_request.request_data.correlation_id
                        or queued_request.queue_id,
                        details={
                            "provider": primary_provider.value,
                            "queue_id": str(queued_request.queue_id),
                            "queue_processing_mode": "serial_bundle",
                        },
                    )
                else:
                    raise_processing_error(
                        service="llm_provider_service",
                        operation="serial_bundle_processing",
                        message="Unexpected result type returned from batch processor",
                        correlation_id=queued_request.request_data.correlation_id
                        or queued_request.queue_id,
                        details={
                            "provider": primary_provider.value,
                            "result_type": str(type(result)),
                        },
                    )

        except HuleEduError as error:
            logger.error(
                "Serial bundle processing hit provider error",
                exc_info=True,
                extra={
                    "queue_processing_mode": "serial_bundle",
                    "bundle_size": len(bundle_requests),
                },
            )
            for queued_request in bundle_requests:
                await self.result_handler.handle_request_hule_error(queued_request, error)
                outcomes.append(
                    ExecutionOutcome(
                        request=queued_request,
                        provider=primary_provider,
                        result="failure",
                        processing_started=processing_started[str(queued_request.queue_id)],
                    )
                )
        except Exception as exc:
            logger.error("Unexpected error while processing serial bundle", exc_info=True)
            try:
                raise_processing_error(
                    service="llm_provider_service",
                    operation="serial_bundle_processing",
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
