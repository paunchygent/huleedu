"""
Queue processor for handling queued LLM requests.

Continuously processes queued requests when providers become available,
manages request lifecycle, and handles result storage.
"""

import asyncio
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from common_core import LLMProviderType, QueueStatus
from common_core.events.envelope import EventEnvelope
from common_core.events.llm_provider_events import LLMComparisonResultV1, TokenUsage
from huleedu_service_libs.logging_utils import create_service_logger

from services.llm_provider_service.config import QueueProcessingMode, Settings
from services.llm_provider_service.exceptions import (
    HuleEduError,
    raise_processing_error,
)
from services.llm_provider_service.implementations.trace_context_manager_impl import (
    TraceContextManagerImpl,
)
from services.llm_provider_service.internal_models import (
    BatchComparisonItem,
    LLMOrchestratorResponse,
    LLMQueuedResult,
)
from services.llm_provider_service.metrics import get_queue_metrics
from services.llm_provider_service.prompt_utils import compute_prompt_sha256
from services.llm_provider_service.protocols import (
    ComparisonProcessorProtocol,
    LLMEventPublisherProtocol,
    QueueManagerProtocol,
)
from services.llm_provider_service.queue_models import QueuedRequest

logger = create_service_logger("llm_provider_service.queue_processor")


class QueueProcessorImpl:
    """Processes queued LLM requests in the background."""

    _QUEUE_METRICS_LOG_INTERVAL_SECONDS = 30.0

    def __init__(
        self,
        comparison_processor: ComparisonProcessorProtocol,
        queue_manager: QueueManagerProtocol,
        event_publisher: LLMEventPublisherProtocol,
        trace_context_manager: TraceContextManagerImpl,
        settings: Settings,
        queue_processing_mode: QueueProcessingMode | None = None,
    ):
        """Initialize queue processor.

        Args:
            comparison_processor: Processor for domain logic (comparison processing)
            queue_manager: Queue manager for request handling
            event_publisher: Event publisher for notifications
            trace_context_manager: Trace context manager for distributed tracing
            settings: Service settings
        """
        self.comparison_processor = comparison_processor
        self.queue_manager = queue_manager
        self.event_publisher = event_publisher
        self.trace_context_manager = trace_context_manager
        self.settings = settings
        self.queue_processing_mode = queue_processing_mode or settings.QUEUE_PROCESSING_MODE

        # Processing state
        self._running = False
        self._processing_task: Optional[asyncio.Task] = None

        # Performance tracking
        self._requests_processed = 0
        self._last_cleanup_time = time.time()
        self._cleanup_interval = 300  # 5 minutes
        self.queue_metrics = get_queue_metrics()
        self._last_queue_metrics_log = 0.0
        self._pending_request: Optional[QueuedRequest] = None

    async def start(self) -> None:
        """Start the queue processor."""
        if self._running:
            logger.warning("Queue processor already running")
            return

        self._running = True
        self._processing_task = asyncio.create_task(self._process_queue_loop())
        logger.info("Queue processor started")

    async def stop(self) -> None:
        """Stop the queue processor gracefully."""
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
        """Main processing loop."""
        while self._running:
            try:
                # Cleanup expired requests periodically
                await self._periodic_cleanup()
                await self._record_queue_stats()

                # Get next request from queue (respecting any deferred item)
                request: Optional[QueuedRequest]
                if self._pending_request is not None:
                    request = self._pending_request
                    self._pending_request = None
                else:
                    request = await self.queue_manager.dequeue()
                if request is None:
                    # No requests, wait a bit
                    await asyncio.sleep(self.settings.QUEUE_POLL_INTERVAL_SECONDS)
                    continue

                # Check if request has expired
                if self._is_expired(request):
                    await self._handle_expired_request(request)
                    provider = self._resolve_provider_from_request(request)
                    self._record_expiry_metrics(
                        request=request,
                        provider=provider,
                        expiry_reason="ttl",
                    )
                    self._record_completion_metrics(
                        provider=provider,
                        result="expired",
                        request=request,
                        processing_started=None,
                    )
                    continue

                # Process the request
                if self.queue_processing_mode is QueueProcessingMode.PER_REQUEST:
                    await self._process_request(request)
                else:
                    await self._process_request_serial_bundle(request)
                    # Yield control so other tasks/providers can run between bundles
                    await asyncio.sleep(0)

            except asyncio.CancelledError:
                logger.info("Queue processing cancelled")
                break
            except Exception as e:
                logger.error(f"Error in queue processing loop: {e}", exc_info=True)
                await asyncio.sleep(5)  # Wait before retry

    async def _process_request(self, request: QueuedRequest) -> None:
        """Process a single queued request.

        Args:
            request: The request to process
        """
        processing_started = time.perf_counter()
        logger.info(
            f"Processing queued request {request.queue_id}, "
            f"correlation_id: {request.request_data.correlation_id}",
            extra={"queue_processing_mode": self.queue_processing_mode.value},
        )

        # Update status to processing
        await self.queue_manager.update_status(
            queue_id=request.queue_id,
            status=QueueStatus.PROCESSING,
        )

        try:
            # Extract request data
            req_data = request.request_data

            # Extract provider and overrides
            provider = self._resolve_provider_from_request(request)
            overrides = self._build_override_kwargs(request)

            # Restore trace context for queue processing to maintain unbroken spans
            trace_context = request.trace_context or {}

            # Call orchestrator within restored trace context
            with self.trace_context_manager.restore_trace_context_for_queue_processing(
                trace_context, request.queue_id
            ) as span:
                span.add_event(
                    "queue_request_processing_started",
                    {
                        "queue_id": str(request.queue_id),
                        "correlation_id": str(req_data.correlation_id or request.queue_id),
                        "provider": provider.value,
                    },
                )

                result: LLMOrchestratorResponse | LLMQueuedResult
                if self.queue_processing_mode is QueueProcessingMode.PER_REQUEST:
                    result = await self.comparison_processor.process_comparison(
                        provider=provider,
                        user_prompt=req_data.user_prompt,
                        correlation_id=req_data.correlation_id or request.queue_id,
                        **overrides,
                    )
                else:
                    batch_item = BatchComparisonItem(
                        provider=provider,
                        user_prompt=req_data.user_prompt,
                        correlation_id=req_data.correlation_id or request.queue_id,
                        overrides=overrides or None,
                    )
                    batch_results = await self.comparison_processor.process_comparison_batch(
                        [batch_item]
                    )
                    if not batch_results:
                        raise_processing_error(
                            service="llm_provider_service",
                            operation="queue_request_processing",
                            message="Batch processor returned no results",
                            correlation_id=req_data.correlation_id or request.queue_id,
                            details={
                                "provider": provider.value,
                                "queue_id": str(request.queue_id),
                                "queue_processing_mode": self.queue_processing_mode.value,
                            },
                        )
                    result = batch_results[0]

            if isinstance(result, LLMOrchestratorResponse):
                await self._handle_request_success(request, result)
                self._record_completion_metrics(
                    provider=provider,
                    result="success",
                    request=request,
                    processing_started=processing_started,
                )
            elif isinstance(result, LLMQueuedResult):
                # Shouldn't happen - queued request shouldn't return another queued result
                logger.error(
                    f"Unexpected queued result for request {request.queue_id}: {type(result)}"
                )
                raise_processing_error(
                    service="llm_provider_service",
                    operation="queue_request_processing",
                    message="Unexpected queued result during queue processing",
                    correlation_id=req_data.correlation_id or request.queue_id,
                    details={"provider": provider.value, "queue_id": str(request.queue_id)},
                )
            else:
                # Unexpected result type
                logger.error(
                    f"Unexpected result type for request {request.queue_id}: {type(result)}"
                )
                raise_processing_error(
                    service="llm_provider_service",
                    operation="queue_request_processing",
                    message="Unexpected processing result type",
                    correlation_id=req_data.correlation_id or request.queue_id,
                    details={"provider": provider.value, "result_type": str(type(result))},
                )

        except HuleEduError as e:
            logger.error(
                f"LLM service error processing request {request.queue_id}: {e}", exc_info=True
            )
            await self._handle_request_hule_error(request, e)
            self._record_completion_metrics(
                provider=provider,
                result="failure",
                request=request,
                processing_started=processing_started,
            )
        except Exception as e:
            logger.error(
                f"Unexpected error processing request {request.queue_id}: {e}", exc_info=True
            )
            # Get provider from config or use default
            # Create a HuleEduError and handle it properly without re-raising
            try:
                raise_processing_error(
                    service="llm_provider_service",
                    operation="queue_request_processing",
                    message=f"Processing failed: {str(e)}",
                    correlation_id=request.request_data.correlation_id or request.queue_id,
                    details={"provider": provider.value, "queue_id": str(request.queue_id)},
                )
            except HuleEduError as processing_error:
                await self._handle_request_hule_error(request, processing_error)
                self._record_completion_metrics(
                    provider=provider,
                    result="failure",
                    request=request,
                    processing_started=processing_started,
                )

    async def _process_request_serial_bundle(self, first_request: QueuedRequest) -> None:
        """Process multiple queued requests under serial bundle mode."""

        bundle_requests: list[QueuedRequest] = []
        batch_items: list[BatchComparisonItem] = []
        processing_started: dict[str, float] = {}

        primary_provider = self._resolve_provider_from_request(first_request)
        primary_overrides = self._build_override_kwargs(first_request)
        primary_hint = self._get_cj_batching_mode_hint(first_request)

        processing_started[str(first_request.queue_id)] = time.perf_counter()
        await self._mark_request_processing(first_request)
        bundle_requests.append(first_request)
        batch_items.append(
            self._build_batch_item(first_request, primary_provider, primary_overrides)
        )

        while len(bundle_requests) < self.settings.SERIAL_BUNDLE_MAX_REQUESTS_PER_CALL:
            next_request = await self.queue_manager.dequeue()
            if not next_request:
                break

            if self._is_expired(next_request):
                await self._handle_expired_request(next_request)
                expired_provider = self._resolve_provider_from_request(next_request)
                self._record_expiry_metrics(
                    request=next_request,
                    provider=expired_provider,
                    expiry_reason="ttl",
                )
                self._record_completion_metrics(
                    provider=expired_provider,
                    result="expired",
                    request=next_request,
                    processing_started=None,
                )
                continue

            candidate_provider = self._resolve_provider_from_request(next_request)
            candidate_overrides = self._build_override_kwargs(next_request)
            candidate_hint = self._get_cj_batching_mode_hint(next_request)

            if not self._requests_are_compatible(
                base_provider=primary_provider,
                candidate_provider=candidate_provider,
                base_overrides=primary_overrides,
                candidate_overrides=candidate_overrides,
                base_hint=primary_hint,
                candidate_hint=candidate_hint,
            ):
                self._pending_request = next_request
                break

            processing_started[str(next_request.queue_id)] = time.perf_counter()
            await self._mark_request_processing(next_request)
            bundle_requests.append(next_request)
            batch_items.append(
                self._build_batch_item(next_request, candidate_provider, candidate_overrides)
            )

        logger.info(
            "serial_bundle_dispatch",
            extra={
                "bundle_size": len(bundle_requests),
                "queue_processing_mode": self.queue_processing_mode.value,
                "provider": primary_provider.value,
                "model_override": primary_overrides.get("model_override"),
                "cj_llm_batching_mode": primary_hint,
            },
        )

        try:
            batch_results = await self.comparison_processor.process_comparison_batch(batch_items)
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
                        "queue_processing_mode": self.queue_processing_mode.value,
                    },
                )

            for queued_request, result in zip(bundle_requests, batch_results, strict=True):
                if isinstance(result, LLMOrchestratorResponse):
                    await self._handle_request_success(queued_request, result)
                    self._record_completion_metrics(
                        provider=result.provider,
                        result="success",
                        request=queued_request,
                        processing_started=processing_started[str(queued_request.queue_id)],
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
                            "queue_processing_mode": self.queue_processing_mode.value,
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
                    "queue_processing_mode": self.queue_processing_mode.value,
                    "bundle_size": len(bundle_requests),
                },
            )
            for queued_request in bundle_requests:
                await self._handle_request_hule_error(queued_request, error)
                self._record_completion_metrics(
                    provider=primary_provider,
                    result="failure",
                    request=queued_request,
                    processing_started=processing_started[str(queued_request.queue_id)],
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
                    await self._handle_request_hule_error(queued_request, processing_error)
                    self._record_completion_metrics(
                        provider=primary_provider,
                        result="failure",
                        request=queued_request,
                        processing_started=processing_started[str(queued_request.queue_id)],
                    )

    def _build_override_kwargs(self, request: QueuedRequest) -> Dict[str, Any]:
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

    def _build_batch_item(
        self,
        request: QueuedRequest,
        provider: LLMProviderType,
        overrides: Dict[str, Any],
    ) -> BatchComparisonItem:
        """Create a BatchComparisonItem for the supplied queued request."""

        return BatchComparisonItem(
            provider=provider,
            user_prompt=request.request_data.user_prompt,
            correlation_id=request.request_data.correlation_id or request.queue_id,
            overrides=overrides or None,
        )

    async def _mark_request_processing(self, request: QueuedRequest) -> None:
        """Mark a queued request as processing."""

        await self.queue_manager.update_status(
            queue_id=request.queue_id,
            status=QueueStatus.PROCESSING,
        )

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
        """Determine if two requests can be bundled together."""

        if candidate_provider is not base_provider:
            return False

        if base_overrides != candidate_overrides:
            return False

        if base_hint is None and candidate_hint is None:
            return True

        return base_hint == candidate_hint

    def _get_cj_batching_mode_hint(self, request: QueuedRequest) -> str | None:
        """Return the CJ-provided batching hint if present."""

        metadata = request.request_data.metadata or {}
        hint = metadata.get("cj_llm_batching_mode")
        if isinstance(hint, str):
            return hint
        return None

    def _resolve_provider_from_request(self, request: QueuedRequest) -> LLMProviderType:
        """Determine which provider should service the request."""
        overrides = request.request_data.llm_config_overrides
        if overrides and overrides.provider_override:
            return overrides.provider_override
        return getattr(self.settings, "DEFAULT_LLM_PROVIDER", LLMProviderType.OPENAI)

    async def _record_queue_stats(self) -> None:
        """Update Prometheus gauges and emit periodic queue logs."""
        if not self.queue_metrics:
            return

        depth_gauge = self.queue_metrics.get("llm_queue_depth")
        if depth_gauge is None:
            return

        try:
            stats = await self.queue_manager.get_queue_stats()
        except Exception as exc:  # pragma: no cover - defensive logging only
            logger.debug(f"Unable to collect queue stats: {exc}")
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

    def _record_expiry_metrics(
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

    def _record_completion_metrics(
        self,
        *,
        provider: LLMProviderType,
        result: str,
        request: QueuedRequest,
        processing_started: float | None,
    ) -> None:
        """Record per-request timing metrics for queue processing.

        Expired requests should not contribute to processing-time or callback metrics but
        still update queue wait-time metrics for observability.
        """
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

        # Only record processing time and callbacks for actual work that produced or attempted
        # a callback (success/failure). Expired or otherwise short-circuited requests should not
        # affect these metrics.
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

    async def _handle_request_success(
        self, request: QueuedRequest, result: LLMOrchestratorResponse
    ) -> None:
        """Handle successful request completion.

        Args:
            request: The processed request
            result: The successful result
        """
        logger.info(
            f"Request {request.queue_id} completed successfully, "
            f"correlation_id: {request.request_data.correlation_id}"
        )

        # Update status to completed
        await self.queue_manager.update_status(
            queue_id=request.queue_id,
            status=QueueStatus.COMPLETED,
            result_location=f"cache:{request.queue_id}",
        )

        # Publish completion event
        await self.event_publisher.publish_llm_request_completed(
            provider=result.provider.value,
            correlation_id=result.correlation_id,
            success=True,
            response_time_ms=int(
                (datetime.now(timezone.utc) - request.queued_at).total_seconds() * 1000
            ),
            metadata={
                "request_type": "comparison",
                "queue_id": str(request.queue_id),
                "queued_duration_seconds": int(
                    (datetime.now(timezone.utc) - request.queued_at).total_seconds()
                ),
            },
        )

        # Publish callback event for successful completion
        await self._publish_callback_event(request, result)

        # CRITICAL: Remove completed request from queue to prevent clogging
        await self.queue_manager.remove(request.queue_id)

        self._requests_processed += 1

    async def _handle_request_hule_error(self, request: QueuedRequest, error: HuleEduError) -> None:
        """Handle request processing error from HuleEduError.

        Args:
            request: The failed request
            error: The HuleEduError that occurred
        """
        error_details = error.error_detail
        logger.error(
            f"Request {request.queue_id} failed: {error_details.message}, "
            f"correlation_id: {request.request_data.correlation_id}"
        )

        # Check if we should retry based on error type
        is_retryable = error_details.error_code.name in {
            "RATE_LIMIT",
            "EXTERNAL_SERVICE_ERROR",
            "TIMEOUT",
            "CONNECTION_ERROR",
        }

        if is_retryable and request.retry_count < self.settings.QUEUE_MAX_RETRIES:
            request.retry_count += 1
            request.status = QueueStatus.QUEUED
            logger.info(
                f"Requeueing request {request.queue_id} for retry "
                f"({request.retry_count}/{self.settings.QUEUE_MAX_RETRIES})"
            )

            # Re-enqueue for retry - first remove from queue to avoid "already exists" error
            try:
                # Remove the request from queue first to avoid duplicate
                await self.queue_manager.remove(request.queue_id)
            except Exception as e:
                logger.warning(f"Failed to remove request {request.queue_id} before retry: {e}")

            # Now re-enqueue for retry
            retry_success = await self.queue_manager.enqueue(request)
            if not retry_success:
                logger.error(
                    f"Failed to re-enqueue request {request.queue_id} for retry, "
                    f"marking as failed to prevent infinite loop"
                )
                # Mark as failed to prevent infinite loop
                await self.queue_manager.update_status(
                    queue_id=request.queue_id,
                    status=QueueStatus.FAILED,
                    message=f"Failed to re-enqueue for retry: {error_details.message}",
                )
                # Publish callback event for error completion
                await self._publish_callback_event_error(request, error)
        else:
            # Mark as failed
            await self.queue_manager.update_status(
                queue_id=request.queue_id,
                status=QueueStatus.FAILED,
                message=error_details.message,
            )

            # Get provider from error or use default
            provider = LLMProviderType.OPENAI
            if "provider" in error_details.details:
                try:
                    provider = LLMProviderType(error_details.details["provider"])
                except ValueError:
                    pass

            # Publish failure event
            await self.event_publisher.publish_llm_provider_failure(
                provider=provider.value,
                failure_type=error_details.error_code.name.lower(),
                correlation_id=error_details.correlation_id,
                error_details=error_details.message,
                circuit_breaker_opened=False,
            )

            # Publish callback event for error completion
            await self._publish_callback_event_error(request, error)

            # CRITICAL: Remove failed request from queue to prevent clogging
            await self.queue_manager.remove(request.queue_id)

    async def _handle_expired_request(self, request: QueuedRequest) -> None:
        """Handle an expired request.

        Args:
            request: The expired request
        """
        logger.warning(
            f"Request {request.queue_id} has expired, "
            f"correlation_id: {request.request_data.correlation_id}"
        )

        await self.queue_manager.update_status(
            queue_id=request.queue_id,
            status=QueueStatus.EXPIRED,
            message="Request expired before processing",
        )

    def _is_expired(self, request: QueuedRequest) -> bool:
        """Check if a request has expired.

        Args:
            request: The request to check

        Returns:
            True if expired, False otherwise
        """
        expiry_time = request.queued_at + request.ttl
        return datetime.now(timezone.utc) > expiry_time

    async def _periodic_cleanup(self) -> None:
        """Perform periodic cleanup tasks."""
        current_time = time.time()
        if current_time - self._last_cleanup_time < self._cleanup_interval:
            return

        self._last_cleanup_time = current_time

        # Cleanup expired requests
        expired_count = await self.queue_manager.cleanup_expired()
        if expired_count > 0:
            logger.info(f"Cleaned up {expired_count} expired requests")

        # Log processing stats
        logger.info(f"Queue processor stats - Processed: {self._requests_processed}")

    async def _publish_callback_event(
        self, request: QueuedRequest, result: LLMOrchestratorResponse
    ) -> None:
        """Publish callback event with successful LLM comparison result.

        Args:
            request: The processed request
            result: The successful result
        """
        try:
            request_meta = dict(request.request_data.metadata or {})
            prompt_hash = result.metadata.get("prompt_sha256") if result.metadata else None
            if prompt_hash:
                request_meta.setdefault("prompt_sha256", prompt_hash)

            # Create success callback event
            callback_event = LLMComparisonResultV1(
                request_id=str(request.queue_id),
                correlation_id=request.correlation_id or request.queue_id,
                winner=result.winner,
                justification=result.justification,
                confidence=result.confidence * 4 + 1,  # Convert 0-1 to 1-5 scale
                error_detail=None,
                provider=result.provider,
                model=result.model,
                response_time_ms=result.response_time_ms,
                token_usage=TokenUsage(
                    prompt_tokens=result.token_usage.get("prompt_tokens", 0),
                    completion_tokens=result.token_usage.get("completion_tokens", 0),
                    total_tokens=result.token_usage.get("total_tokens", 0),
                ),
                cost_estimate=result.cost_estimate,
                requested_at=request.queued_at,
                completed_at=datetime.now(timezone.utc),
                trace_id=result.trace_id,
                request_metadata=request_meta,
            )

            # Create event envelope and publish
            envelope = EventEnvelope[LLMComparisonResultV1](
                event_type="LLMComparisonResultV1",
                event_timestamp=datetime.now(timezone.utc),
                source_service="llm_provider_service",
                correlation_id=request.correlation_id or request.queue_id,
                data=callback_event,
            )

            await self.event_publisher.publish_to_topic(
                topic=request.callback_topic,
                envelope=envelope,
            )

            logger.info(
                f"Published success callback event for request {request.queue_id}, "
                f"correlation_id: {request.correlation_id}, "
                f"topic: {request.callback_topic}"
            )

        except Exception as e:
            # Don't fail the request on publish failure - just log and continue
            logger.error(
                f"Failed to publish callback event for request {request.queue_id}: {e}, "
                f"correlation_id: {request.correlation_id}",
                exc_info=True,
            )

    async def _publish_callback_event_error(
        self, request: QueuedRequest, error: HuleEduError
    ) -> None:
        """Publish callback event with error result.

        Args:
            request: The failed request
            error: The HuleEduError that occurred
        """
        try:
            # Get provider from error or use default
            fallback_provider = LLMProviderType.OPENAI
            if "provider" in error.error_detail.details:
                try:
                    fallback_provider = LLMProviderType(error.error_detail.details["provider"])
                except ValueError:
                    pass

            request_meta = dict(request.request_data.metadata or {})

            # Ensure prompt hash is always available so downstream runners can
            # correlate callbacks even when providers fail before returning
            # metadata. Prefer the configured provider override, fall back to
            # the provider embedded in the error, then the default.
            provider_hint = fallback_provider
            overrides = request.request_data.llm_config_overrides
            if overrides and overrides.provider_override:
                provider_hint = overrides.provider_override
            elif "provider" in error.error_detail.details:
                try:
                    provider_hint = LLMProviderType(error.error_detail.details["provider"])
                except ValueError:
                    provider_hint = fallback_provider

            if "prompt_sha256" not in request_meta:
                try:
                    request_meta["prompt_sha256"] = compute_prompt_sha256(
                        provider=provider_hint,
                        user_prompt=request.request_data.user_prompt,
                    )
                except Exception as exc:  # pragma: no cover - defensive guard
                    logger.warning(
                        "Failed to compute prompt hash for error callback",
                        extra={
                            "queue_id": str(request.queue_id),
                            "correlation_id": str(request.correlation_id or ""),
                            "reason": str(exc),
                        },
                    )

            # Create error callback event
            callback_event = LLMComparisonResultV1(
                request_id=str(request.queue_id),
                correlation_id=request.correlation_id or request.queue_id,
                winner=None,
                justification=None,
                confidence=None,
                error_detail=error.error_detail,  # Use structured ErrorDetail
                provider=fallback_provider,
                model="unknown",
                response_time_ms=0,
                token_usage=TokenUsage(),  # Empty for errors
                cost_estimate=0.0,
                requested_at=request.queued_at,
                completed_at=datetime.now(timezone.utc),
                trace_id=None,
                request_metadata=request_meta,
            )

            # Create event envelope and publish
            envelope = EventEnvelope[LLMComparisonResultV1](
                event_type="LLMComparisonResultV1",
                event_timestamp=datetime.now(timezone.utc),
                source_service="llm_provider_service",
                correlation_id=request.correlation_id or request.queue_id,
                data=callback_event,
            )

            await self.event_publisher.publish_to_topic(
                topic=request.callback_topic,
                envelope=envelope,
            )

            logger.info(
                f"Published error callback event for request {request.queue_id}, "
                f"correlation_id: {request.correlation_id}, "
                f"topic: {request.callback_topic}"
            )

        except Exception as e:
            # Don't fail the request on publish failure - just log and continue
            logger.error(
                f"Failed to publish error callback event for request {request.queue_id}: {e}, "
                f"correlation_id: {request.correlation_id}",
                exc_info=True,
            )
