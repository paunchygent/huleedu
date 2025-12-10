"""Queue orchestration loop for queued LLM requests."""

from __future__ import annotations

import asyncio
import time
from typing import Optional

from huleedu_service_libs.logging_utils import create_service_logger

from services.llm_provider_service.config import QueueProcessingMode, Settings
from services.llm_provider_service.implementations.llm_override_utils import (
    resolve_provider_from_request,
)
from services.llm_provider_service.implementations.queue_processor_metrics import (
    QueueProcessorMetrics,
)
from services.llm_provider_service.implementations.queue_request_executor import (
    QueuedRequestExecutor,
    SerialBundleResult,
)
from services.llm_provider_service.implementations.queue_ttl_utils import is_request_expired
from services.llm_provider_service.protocols import QueueManagerProtocol
from services.llm_provider_service.queue_models import QueuedRequest

logger = create_service_logger("llm_provider_service.queue_loop")


class QueueProcessingLoop:
    """Owns lifecycle of queue processing and cleanup."""

    _CLEANUP_INTERVAL_SECONDS = 300

    def __init__(
        self,
        *,
        queue_manager: QueueManagerProtocol,
        executor: QueuedRequestExecutor,
        metrics: QueueProcessorMetrics,
        settings: Settings,
        queue_processing_mode: QueueProcessingMode,
    ) -> None:
        self.queue_manager = queue_manager
        self.executor = executor
        self.metrics = metrics
        self.settings = settings
        self.queue_processing_mode = queue_processing_mode

        self._pending_request: Optional[QueuedRequest] = None
        self._running = False
        self._processing_task: Optional[asyncio.Task] = None
        self._last_cleanup_time = time.time()

    async def start(self) -> None:
        """Start the queue processing loop."""

        if self._running:
            logger.warning("Queue processor already running")
            return

        self._running = True
        self._processing_task = asyncio.create_task(self._process_queue_loop())
        logger.info("Queue processor started")

    async def stop(self) -> None:
        """Stop the queue processing loop."""

        if not self._running:
            return

        logger.info("Stopping queue processor...")
        self._running = False

        if self._processing_task:
            self._processing_task.cancel()
            try:
                await self._processing_task
            except asyncio.CancelledError:
                pass

        logger.info("Queue processor stopped")

    async def _process_queue_loop(self) -> None:
        while self._running:
            try:
                await self._periodic_cleanup()
                await self.metrics.record_queue_stats(self.queue_manager)

                request: Optional[QueuedRequest]
                if self._pending_request is not None:
                    request = self._pending_request
                    self._pending_request = None
                else:
                    request = await self.queue_manager.dequeue()

                if request is None:
                    await asyncio.sleep(self.settings.QUEUE_POLL_INTERVAL_SECONDS)
                    continue

                if is_request_expired(request):
                    await self.executor.handle_expired_request(request)
                    provider = resolve_provider_from_request(request, self.settings)
                    self.metrics.record_expiry_metrics(
                        request=request,
                        provider=provider,
                        expiry_reason="ttl",
                    )
                    self.metrics.record_completion_metrics(
                        provider=provider,
                        result="expired",
                        request=request,
                        processing_started=None,
                    )
                    continue

                if self.queue_processing_mode is QueueProcessingMode.PER_REQUEST:
                    outcome = await self.executor.execute_request(request)
                    self.metrics.record_completion_metrics(
                        provider=outcome.provider,
                        result=outcome.result,
                        request=outcome.request,
                        processing_started=outcome.processing_started,
                    )
                elif self.queue_processing_mode is QueueProcessingMode.SERIAL_BUNDLE:
                    bundle_result: SerialBundleResult = await self.executor.execute_serial_bundle(
                        request
                    )
                    self._pending_request = bundle_result.pending_request
                    for outcome in bundle_result.outcomes:
                        self.metrics.record_completion_metrics(
                            provider=outcome.provider,
                            result=outcome.result,
                            request=outcome.request,
                            processing_started=outcome.processing_started,
                        )
                    await asyncio.sleep(0)
                elif self.queue_processing_mode is QueueProcessingMode.BATCH_API:
                    bundle_result = await self.executor.execute_batch_api(request)
                    self._pending_request = bundle_result.pending_request
                    for outcome in bundle_result.outcomes:
                        self.metrics.record_completion_metrics(
                            provider=outcome.provider,
                            result=outcome.result,
                            request=outcome.request,
                            processing_started=outcome.processing_started,
                        )
                    await asyncio.sleep(0)

            except asyncio.CancelledError:
                logger.info("Queue processing cancelled")
                break
            except Exception as exc:  # pragma: no cover - defensive loop guard
                logger.error(f"Error in queue processing loop: {exc}", exc_info=True)
                await asyncio.sleep(5)

    async def _periodic_cleanup(self) -> None:
        """Perform periodic cleanup tasks."""

        current_time = time.time()
        if current_time - self._last_cleanup_time < self._CLEANUP_INTERVAL_SECONDS:
            return

        self._last_cleanup_time = current_time

        expired_count = await self.queue_manager.cleanup_expired()
        if expired_count > 0:
            logger.info(f"Cleaned up {expired_count} expired requests")

        logger.info(
            "Queue processor stats",
            extra={"processed": self.executor.requests_processed},
        )
