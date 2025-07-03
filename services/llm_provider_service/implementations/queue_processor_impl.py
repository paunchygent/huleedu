"""
Queue processor for handling queued LLM requests.

Continuously processes queued requests when providers become available,
manages request lifecycle, and handles result storage.
"""

import asyncio
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import UUID

from huleedu_service_libs.logging_utils import create_service_logger

from common_core import LLMProviderType, QueueStatus
from common_core.error_enums import ErrorCode
from services.llm_provider_service.config import Settings
from services.llm_provider_service.internal_models import (
    LLMOrchestratorResponse,
    LLMProviderError,
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
        settings: Settings,
    ):
        """Initialize queue processor.

        Args:
            orchestrator: LLM orchestrator for making requests
            queue_manager: Queue manager for request handling
            event_publisher: Event publisher for notifications
            settings: Service settings
        """
        self.orchestrator = orchestrator
        self.queue_manager = queue_manager
        self.event_publisher = event_publisher
        self.settings = settings

        # Processing state
        self._running = False
        self._processing_task: Optional[asyncio.Task] = None
        self._results_cache: Dict[UUID, LLMOrchestratorResponse] = {}
        self._max_results_cache_size = 1000

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

            # Call orchestrator to process the request
            # Note: This will check provider availability and make the actual LLM call
            result, error = await self.orchestrator.perform_comparison(
                provider=provider,
                user_prompt=req_data.user_prompt,
                essay_a=req_data.essay_a,
                essay_b=req_data.essay_b,
                correlation_id=req_data.correlation_id or request.queue_id,
                **overrides,
            )

            if error:
                await self._handle_request_error(request, error)
            elif isinstance(result, LLMOrchestratorResponse):
                await self._handle_request_success(request, result)
            else:
                # Shouldn't happen - queued request shouldn't return another queued result
                logger.error(
                    f"Unexpected result type for request {request.queue_id}: {type(result)}"
                )
                await self._handle_request_error(
                    request,
                    LLMProviderError(
                        error_type=ErrorCode.PROCESSING_ERROR,
                        error_message="Unexpected processing result",
                        provider=provider,
                        correlation_id=req_data.correlation_id or request.queue_id,
                        is_retryable=False,
                    ),
                )

        except Exception as e:
            logger.error(f"Error processing request {request.queue_id}: {e}", exc_info=True)
            # Get provider from config or use default
            req_provider = LLMProviderType.OPENAI
            if request.request_data.llm_config_overrides and request.request_data.llm_config_overrides.provider_override:
                req_provider = request.request_data.llm_config_overrides.provider_override
            
            await self._handle_request_error(
                request,
                LLMProviderError(
                    error_type=ErrorCode.PROCESSING_ERROR,
                    error_message=f"Processing failed: {str(e)}",
                    provider=req_provider,
                    correlation_id=request.request_data.correlation_id or request.queue_id,
                    is_retryable=True,
                ),
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

        # Store result in cache
        self._store_result(request.queue_id, result)

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

        self._requests_processed += 1

    async def _handle_request_error(
        self, request: QueuedRequest, error: LLMProviderError
    ) -> None:
        """Handle request processing error.

        Args:
            request: The failed request
            error: The error that occurred
        """
        logger.error(
            f"Request {request.queue_id} failed: {error.error_message}, "
            f"correlation_id: {request.request_data.correlation_id}"
        )

        # Check if we should retry
        if error.is_retryable and request.retry_count < self.settings.QUEUE_MAX_RETRIES:
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
                error_message=error.error_message,
            )

            # Publish failure event
            await self.event_publisher.publish_llm_provider_failure(
                provider=error.provider.value,
                failure_type=error.error_type.value,
                correlation_id=error.correlation_id,
                error_details=error.error_message,
                circuit_breaker_opened=False,
            )

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
            error_message="Request expired before processing",
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

    def _store_result(self, queue_id: UUID, result: LLMOrchestratorResponse) -> None:
        """Store result in local cache.

        Args:
            queue_id: The queue ID
            result: The result to store
        """
        # Simple cache management - remove oldest if at capacity
        if len(self._results_cache) >= self._max_results_cache_size:
            # Remove first item (oldest in insertion order)
            oldest_key = next(iter(self._results_cache))
            del self._results_cache[oldest_key]

        self._results_cache[queue_id] = result

    def get_result(self, queue_id: UUID) -> Optional[LLMOrchestratorResponse]:
        """Get a stored result.

        Args:
            queue_id: The queue ID to retrieve

        Returns:
            The stored result or None if not found
        """
        return self._results_cache.get(queue_id)

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
        logger.info(
            f"Queue processor stats - Processed: {self._requests_processed}, "
            f"Results cached: {len(self._results_cache)}"
        )