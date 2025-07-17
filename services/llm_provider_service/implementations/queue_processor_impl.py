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

from services.llm_provider_service.config import Settings
from services.llm_provider_service.exceptions import (
    HuleEduError,
    raise_processing_error,
)
from services.llm_provider_service.implementations.trace_context_manager_impl import (
    TraceContextManagerImpl,
)
from services.llm_provider_service.internal_models import (
    LLMOrchestratorResponse,
    LLMQueuedResult,
)
from services.llm_provider_service.protocols import (
    LLMEventPublisherProtocol,
    LLMOrchestratorProtocol,
    QueueManagerProtocol,
)
from services.llm_provider_service.queue_models import QueuedRequest

logger = create_service_logger("llm_provider_service.queue_processor")


class QueueProcessorImpl:
    """Processes queued LLM requests in the background."""

    def __init__(
        self,
        orchestrator: LLMOrchestratorProtocol,
        queue_manager: QueueManagerProtocol,
        event_publisher: LLMEventPublisherProtocol,
        trace_context_manager: TraceContextManagerImpl,
        settings: Settings,
    ):
        """Initialize queue processor.

        Args:
            orchestrator: LLM orchestrator for making requests
            queue_manager: Queue manager for request handling
            event_publisher: Event publisher for notifications
            trace_context_manager: Trace context manager for distributed tracing
            settings: Service settings
        """
        self.orchestrator = orchestrator
        self.queue_manager = queue_manager
        self.event_publisher = event_publisher
        self.trace_context_manager = trace_context_manager
        self.settings = settings

        # Processing state
        self._running = False
        self._processing_task: Optional[asyncio.Task] = None

        # Performance tracking
        self._requests_processed = 0
        self._last_cleanup_time = time.time()
        self._cleanup_interval = 300  # 5 minutes

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

                # Get next request from queue
                request = await self.queue_manager.dequeue()
                if not request:
                    # No requests, wait a bit
                    await asyncio.sleep(self.settings.QUEUE_POLL_INTERVAL_SECONDS)
                    continue

                # Check if request has expired
                if self._is_expired(request):
                    await self._handle_expired_request(request)
                    continue

                # Process the request
                await self._process_request(request)

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
        logger.info(
            f"Processing queued request {request.queue_id}, "
            f"correlation_id: {request.request_data.correlation_id}"
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
            provider = LLMProviderType.OPENAI  # Default provider
            overrides: Dict[str, Any] = {}

            if req_data.llm_config_overrides:
                config = req_data.llm_config_overrides
                if config.provider_override:
                    provider = config.provider_override
                if config.model_override:
                    overrides["model_override"] = config.model_override
                if config.temperature_override is not None:
                    overrides["temperature_override"] = config.temperature_override
                if config.system_prompt_override:
                    overrides["system_prompt_override"] = config.system_prompt_override
                if config.max_tokens_override:
                    overrides["max_tokens_override"] = config.max_tokens_override

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

                # Note: This will check provider availability and make the actual LLM call
                result = await self.orchestrator.perform_comparison(
                    provider=provider,
                    user_prompt=req_data.user_prompt,
                    essay_a=req_data.essay_a,
                    essay_b=req_data.essay_b,
                    correlation_id=req_data.correlation_id or request.queue_id,
                    **overrides,
                )

            if isinstance(result, LLMOrchestratorResponse):
                await self._handle_request_success(request, result)
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
        except Exception as e:
            logger.error(
                f"Unexpected error processing request {request.queue_id}: {e}", exc_info=True
            )
            # Get provider from config or use default
            req_provider = LLMProviderType.OPENAI
            if (
                request.request_data.llm_config_overrides
                and request.request_data.llm_config_overrides.provider_override
            ):
                req_provider = request.request_data.llm_config_overrides.provider_override

            raise_processing_error(
                service="llm_provider_service",
                operation="queue_request_processing",
                message=f"Processing failed: {str(e)}",
                correlation_id=request.request_data.correlation_id or request.queue_id,
                details={"provider": req_provider.value, "queue_id": str(request.queue_id)},
            )

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

            # Re-enqueue for retry
            await self.queue_manager.enqueue(request)
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
            # Create success callback event
            callback_event = LLMComparisonResultV1(
                request_id=str(request.queue_id),
                correlation_id=request.correlation_id or request.queue_id,
                winner=result.winner,
                justification=(
                    result.justification[:50] if result.justification else None
                ),  # Enforce max length - 50 characters NOT 500!
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
                request_metadata=request.request_data.metadata or {},
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
                request_metadata=request.request_data.metadata or {},
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
