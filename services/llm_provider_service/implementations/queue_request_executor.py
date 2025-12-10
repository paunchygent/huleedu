"""Execution pipeline for queued LLM requests."""

from __future__ import annotations

from typing import Any

from huleedu_service_libs.logging_utils import create_service_logger

from services.llm_provider_service.config import QueueProcessingMode, Settings
from services.llm_provider_service.exceptions import HuleEduError
from services.llm_provider_service.implementations.batch_api_strategy import (
    BatchApiStrategy,
)
from services.llm_provider_service.implementations.batch_api_strategy import (
    SerialBundleResult as BatchApiSerialBundleResult,
)
from services.llm_provider_service.implementations.callback_event_publisher import (
    CallbackEventPublisher,
)
from services.llm_provider_service.implementations.execution_result_handler import (
    ExecutionResultHandler,
)
from services.llm_provider_service.implementations.queue_processor_metrics import (
    QueueProcessorMetrics,
)
from services.llm_provider_service.implementations.queue_tracing_enricher import (
    QueueTracingEnricher,
)
from services.llm_provider_service.implementations.request_strategies import (
    ExecutionOutcome,
    SerialBundleResult,
    SerialBundleStrategy,
    SingleRequestStrategy,
)
from services.llm_provider_service.internal_models import LLMOrchestratorResponse
from services.llm_provider_service.protocols import (
    BatchJobManagerProtocol,
    ComparisonProcessorProtocol,
    LLMEventPublisherProtocol,
    QueueManagerProtocol,
)
from services.llm_provider_service.queue_models import QueuedRequest

logger = create_service_logger("llm_provider_service.queue_executor")


class QueuedRequestExecutor:
    """Encapsulates per-request and serial-bundle execution using strategies."""

    def __init__(
        self,
        *,
        comparison_processor: ComparisonProcessorProtocol,
        queue_manager: QueueManagerProtocol,
        event_publisher: LLMEventPublisherProtocol,
        trace_context_manager: Any,
        settings: Settings,
        queue_processing_mode: QueueProcessingMode,
        metrics: QueueProcessorMetrics,
        tracing_enricher: QueueTracingEnricher,
        batch_job_manager: BatchJobManagerProtocol | None = None,
    ) -> None:
        self.settings = settings
        self.queue_processing_mode = queue_processing_mode

        # Initialize event publisher and result handler
        self.callback_publisher = CallbackEventPublisher(
            event_publisher=event_publisher,
            settings=settings,
        )
        self.result_handler = ExecutionResultHandler(
            queue_manager=queue_manager,
            event_publisher=event_publisher,
            callback_publisher=self.callback_publisher,
            metrics=metrics,
            settings=settings,
        )

        # Initialize strategies with result handler
        self.single_strategy = SingleRequestStrategy(
            comparison_processor=comparison_processor,
            result_handler=self.result_handler,
            trace_context_manager=trace_context_manager,
            settings=settings,
            metrics=metrics,
            tracing_enricher=tracing_enricher,
        )
        self.serial_strategy = SerialBundleStrategy(
            comparison_processor=comparison_processor,
            result_handler=self.result_handler,
            trace_context_manager=trace_context_manager,
            settings=settings,
            metrics=metrics,
            tracing_enricher=tracing_enricher,
        )
        self.batch_job_manager = batch_job_manager
        self.batch_api_strategy: BatchApiStrategy | None = None
        if batch_job_manager is not None:
            self.batch_api_strategy = BatchApiStrategy(
                comparison_processor=comparison_processor,
                result_handler=self.result_handler,
                trace_context_manager=trace_context_manager,
                settings=settings,
                metrics=metrics,
                tracing_enricher=tracing_enricher,
                batch_job_manager=batch_job_manager,
            )

    async def execute_request(self, request: QueuedRequest) -> ExecutionOutcome:
        """Process a single queued request."""
        return await self.single_strategy.execute(request)

    async def execute_serial_bundle(self, first_request: QueuedRequest) -> SerialBundleResult:
        """Process multiple queued requests under serial bundle mode."""
        return await self.serial_strategy.execute(first_request)

    async def execute_batch_api(self, first_request: QueuedRequest) -> SerialBundleResult:
        """Process multiple queued requests using the batch job manager."""
        if self.batch_api_strategy is None:
            raise RuntimeError("BatchApiStrategy is not configured for this executor instance")
        result: BatchApiSerialBundleResult = await self.batch_api_strategy.execute(first_request)
        # Cast to the SerialBundleResult type exposed by request_strategies; the
        # structures are intentionally mirrored to keep the executor interface stable.
        return SerialBundleResult(
            outcomes=[
                ExecutionOutcome(
                    request=outcome.request,
                    provider=outcome.provider,
                    result=outcome.result,
                    processing_started=outcome.processing_started,
                )
                for outcome in result.outcomes
            ],
            pending_request=result.pending_request,
        )

    async def handle_expired_request(self, request: QueuedRequest) -> None:
        """Handle an expired queued request."""
        await self.result_handler.handle_expired_request(request)

    # Helper methods exposed for backward compatibility
    async def handle_request_success(
        self, request: QueuedRequest, result: LLMOrchestratorResponse
    ) -> None:
        await self.result_handler.handle_request_success(request, result)

    async def handle_request_hule_error(self, request: QueuedRequest, error: HuleEduError) -> None:
        await self.result_handler.handle_request_hule_error(request, error)

    async def publish_callback_event(
        self, request: QueuedRequest, result: LLMOrchestratorResponse
    ) -> None:
        await self.callback_publisher.publish_success_event(request, result)

    @property
    def requests_processed(self) -> int:
        return self.result_handler.requests_processed
