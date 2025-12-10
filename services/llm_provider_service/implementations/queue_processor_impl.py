"""Queue processor orchestration for LLM provider service."""

from __future__ import annotations

from typing import Any, Dict

from common_core import LLMProviderType

from services.llm_provider_service.config import QueueProcessingMode, Settings
from services.llm_provider_service.exceptions import HuleEduError
from services.llm_provider_service.implementations.llm_override_utils import (
    build_override_kwargs,
    get_cj_batching_mode_hint,
    requests_are_compatible,
    resolve_provider_from_request,
)
from services.llm_provider_service.implementations.queue_processing_loop import (
    QueueProcessingLoop,
)
from services.llm_provider_service.implementations.queue_processor_metrics import (
    QueueProcessorMetrics,
)
from services.llm_provider_service.implementations.queue_request_executor import (
    ExecutionOutcome,
    QueuedRequestExecutor,
    SerialBundleResult,
)
from services.llm_provider_service.implementations.queue_tracing_enricher import (
    QueueTracingEnricher,
)
from services.llm_provider_service.implementations.queue_ttl_utils import (
    is_request_expired,
)
from services.llm_provider_service.internal_models import LLMOrchestratorResponse
from services.llm_provider_service.metrics import get_llm_metrics, get_queue_metrics
from services.llm_provider_service.protocols import (
    BatchJobManagerProtocol,
    ComparisonProcessorProtocol,
    LLMEventPublisherProtocol,
    QueueManagerProtocol,
)
from services.llm_provider_service.queue_models import QueuedRequest


class QueueProcessorImpl:
    """Facade wiring together queue loop, executor, metrics, and tracing."""

    def __init__(
        self,
        comparison_processor: ComparisonProcessorProtocol,
        queue_manager: QueueManagerProtocol,
        event_publisher: LLMEventPublisherProtocol,
        trace_context_manager: Any,
        settings: Settings,
        queue_processing_mode: QueueProcessingMode | None = None,
        batch_job_manager: BatchJobManagerProtocol | None = None,
    ):
        self.comparison_processor = comparison_processor
        self.queue_manager = queue_manager
        self.event_publisher = event_publisher
        self.trace_context_manager = trace_context_manager
        self.settings = settings
        self.queue_processing_mode = queue_processing_mode or settings.QUEUE_PROCESSING_MODE
        self.batch_job_manager = batch_job_manager

        self.metrics = QueueProcessorMetrics(
            queue_metrics=get_queue_metrics(),
            llm_metrics=get_llm_metrics(),
            queue_processing_mode=self.queue_processing_mode,
        )
        self.queue_metrics = self.metrics.queue_metrics
        self.llm_metrics = self.metrics.llm_metrics

        self.tracing_enricher = QueueTracingEnricher(self.queue_processing_mode)
        self.executor = QueuedRequestExecutor(
            comparison_processor=comparison_processor,
            queue_manager=queue_manager,
            event_publisher=event_publisher,
            trace_context_manager=trace_context_manager,
            settings=settings,
            queue_processing_mode=self.queue_processing_mode,
            metrics=self.metrics,
            tracing_enricher=self.tracing_enricher,
            batch_job_manager=self.batch_job_manager,
        )
        self.processing_loop = QueueProcessingLoop(
            queue_manager=queue_manager,
            executor=self.executor,
            metrics=self.metrics,
            settings=settings,
            queue_processing_mode=self.queue_processing_mode,
        )

    async def start(self) -> None:
        await self.processing_loop.start()

    async def stop(self) -> None:
        await self.processing_loop.stop()

    async def _process_request(self, request: QueuedRequest) -> ExecutionOutcome:
        return await self.executor.execute_request(request)

    async def _process_request_serial_bundle(
        self, first_request: QueuedRequest
    ) -> SerialBundleResult:
        result = await self.executor.execute_serial_bundle(first_request)
        self.processing_loop._pending_request = result.pending_request
        return result

    def _enrich_request_metadata(
        self,
        request: QueuedRequest,
        *,
        provider: LLMProviderType,
        model: str | None,
    ) -> None:
        self.tracing_enricher.enrich_request_metadata(request, provider=provider, model=model)

    def _build_override_kwargs(self, request: QueuedRequest) -> Dict[str, Any]:
        return build_override_kwargs(request)

    def _requests_are_compatible(
        self,
        *,
        base_provider: LLMProviderType,
        candidate_provider: LLMProviderType,
        base_overrides: Dict[str, Any],
        candidate_overrides: Dict[str, Any],
        base_hint: str | None,
        candidate_hint: str | None,
    ) -> bool:
        return requests_are_compatible(
            base_provider=base_provider,
            candidate_provider=candidate_provider,
            base_overrides=base_overrides,
            candidate_overrides=candidate_overrides,
            base_hint=base_hint,
            candidate_hint=candidate_hint,
        )

    def _get_cj_batching_mode_hint(self, request: QueuedRequest) -> str | None:
        return get_cj_batching_mode_hint(request)

    def _resolve_provider_from_request(self, request: QueuedRequest) -> LLMProviderType:
        return resolve_provider_from_request(request, self.settings)

    async def _record_queue_stats(self) -> None:
        await self.metrics.record_queue_stats(self.queue_manager)

    def _record_expiry_metrics(
        self,
        *,
        request: QueuedRequest,
        provider: LLMProviderType,
        expiry_reason: str,
    ) -> None:
        self.metrics.record_expiry_metrics(
            request=request, provider=provider, expiry_reason=expiry_reason
        )

    def _record_completion_metrics(
        self,
        *,
        provider: LLMProviderType,
        result: str,
        request: QueuedRequest,
        processing_started: float | None,
    ) -> None:
        self.metrics.record_completion_metrics(
            provider=provider,
            result=result,
            request=request,
            processing_started=processing_started,
        )

    def _record_prompt_block_metrics(
        self,
        *,
        request: QueuedRequest,
        provider: LLMProviderType,
        model: str,
    ) -> None:
        self.metrics.record_prompt_block_metrics(request=request, provider=provider, model=model)

    def _record_cache_scope_metrics(
        self,
        *,
        request: QueuedRequest,
        result: Any,
    ) -> None:
        self.metrics.record_cache_scope_metrics(request=request, result=result)

    def _is_expired(self, request: QueuedRequest) -> bool:
        return is_request_expired(request)

    async def _handle_expired_request(self, request: QueuedRequest) -> None:
        await self.executor.handle_expired_request(request)

    async def _publish_callback_event(
        self, request: QueuedRequest, result: LLMOrchestratorResponse
    ) -> None:
        await self.executor.callback_publisher.publish_success_event(request, result)

    async def _publish_callback_event_error(
        self, request: QueuedRequest, error: HuleEduError
    ) -> None:
        await self.executor.callback_publisher.publish_error_event(request, error)

    @property
    def queue_metrics(self) -> Dict[str, Any] | None:
        return self.metrics.queue_metrics

    @queue_metrics.setter
    def queue_metrics(self, value: Dict[str, Any] | None) -> None:
        self.metrics.queue_metrics = value

    @property
    def llm_metrics(self) -> Dict[str, Any] | None:
        return self.metrics.llm_metrics

    @llm_metrics.setter
    def llm_metrics(self, value: Dict[str, Any] | None) -> None:
        self.metrics.llm_metrics = value
