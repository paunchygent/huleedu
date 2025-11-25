"""Result handling for executed LLM requests."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from common_core import LLMProviderType, QueueStatus
from huleedu_service_libs.logging_utils import create_service_logger

from services.llm_provider_service.exceptions import HuleEduError
from services.llm_provider_service.implementations.callback_event_publisher import (
    CallbackEventPublisher,
)
from services.llm_provider_service.internal_models import LLMOrchestratorResponse
from services.llm_provider_service.protocols import (
    LLMEventPublisherProtocol,
    QueueManagerProtocol,
)
from services.llm_provider_service.queue_models import QueuedRequest

if TYPE_CHECKING:
    from services.llm_provider_service.config import Settings
    from services.llm_provider_service.implementations.queue_processor_metrics import (
        QueueProcessorMetrics,
    )

logger = create_service_logger("llm_provider_service.result_handler")


class ExecutionResultHandler:
    """Handles success, error, and retry logic for executed requests."""

    def __init__(
        self,
        *,
        queue_manager: QueueManagerProtocol,
        event_publisher: LLMEventPublisherProtocol,
        callback_publisher: CallbackEventPublisher,
        metrics: QueueProcessorMetrics,
        settings: Settings,
    ) -> None:
        self.queue_manager = queue_manager
        self.event_publisher = event_publisher
        self.callback_publisher = callback_publisher
        self.metrics = metrics
        self.settings = settings
        self.requests_processed = 0

    async def handle_expired_request(self, request: QueuedRequest) -> None:
        """Handle an expired queued request."""

        logger.warning(
            f"Request {request.queue_id} has expired, "
            f"correlation_id: {request.request_data.correlation_id}"
        )

        await self.queue_manager.update_status(
            queue_id=request.queue_id,
            status=QueueStatus.EXPIRED,
            message="Request expired before processing",
        )

    async def handle_request_success(
        self, request: QueuedRequest, result: LLMOrchestratorResponse
    ) -> None:
        """Handle a successfully completed request."""
        logger.info(
            f"Request {request.queue_id} completed successfully, "
            f"correlation_id: {request.request_data.correlation_id}"
        )

        await self.queue_manager.update_status(
            queue_id=request.queue_id,
            status=QueueStatus.COMPLETED,
            result_location=f"cache:{request.queue_id}",
        )

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

        self.metrics.record_cache_scope_metrics(request=request, result=result)
        await self.callback_publisher.publish_success_event(request, result)
        await self.queue_manager.remove(request.queue_id)

        self.requests_processed += 1

    async def handle_request_hule_error(self, request: QueuedRequest, error: HuleEduError) -> None:
        """Handle a request that failed with HuleEduError."""
        error_details = error.error_detail
        logger.error(
            f"Request {request.queue_id} failed with HuleEduError: {error_details.message}",
            exc_info=True,
        )

        retryable_codes = {
            "RATE_LIMIT",
            "EXTERNAL_SERVICE_ERROR",
            "TIMEOUT",
            "CONNECTION_ERROR",
        }
        is_retryable = error_details.error_code.name in retryable_codes

        if is_retryable and request.retry_count < self.settings.QUEUE_MAX_RETRIES:
            request.retry_count += 1
            request.status = QueueStatus.QUEUED
            logger.info(
                f"Requeueing request {request.queue_id} for retry "
                f"({request.retry_count}/{self.settings.QUEUE_MAX_RETRIES})"
            )

            try:
                await self.queue_manager.remove(request.queue_id)
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.warning(f"Failed to remove request {request.queue_id} before retry: {exc}")

            retry_success = await self.queue_manager.enqueue(request)
            if not retry_success:
                logger.error(
                    f"Failed to re-enqueue request {request.queue_id} for retry, "
                    f"marking as failed to prevent infinite loop"
                )
                await self.queue_manager.update_status(
                    queue_id=request.queue_id,
                    status=QueueStatus.FAILED,
                    message=f"Failed to re-enqueue for retry: {error_details.message}",
                )
                await self.callback_publisher.publish_error_event(request, error)
        else:
            await self.queue_manager.update_status(
                queue_id=request.queue_id,
                status=QueueStatus.FAILED,
                message=error_details.message,
            )

            provider = LLMProviderType.OPENAI
            if "provider" in error_details.details:
                try:
                    provider = LLMProviderType(error_details.details["provider"])
                except ValueError:
                    pass

            await self.event_publisher.publish_llm_provider_failure(
                provider=provider.value,
                failure_type=error_details.error_code.name.lower(),
                correlation_id=error_details.correlation_id,
                error_details=error_details.message,
                circuit_breaker_opened=False,
            )

            await self.callback_publisher.publish_error_event(request, error)
            await self.queue_manager.remove(request.queue_id)
