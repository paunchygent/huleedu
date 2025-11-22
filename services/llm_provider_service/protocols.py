"""Protocol definitions for LLM Provider Service."""

from typing import Any, Awaitable, Callable, Dict, List, Optional, Protocol
from uuid import UUID

from common_core import LLMProviderType, QueueStatus
from common_core.events.envelope import EventEnvelope

from services.llm_provider_service.internal_models import (
    BatchComparisonItem,
    LLMOrchestratorResponse,
    LLMProviderResponse,
    LLMQueuedResult,
)
from services.llm_provider_service.queue_models import QueuedRequest, QueueStats


class LLMProviderProtocol(Protocol):
    """Protocol for individual LLM provider implementations."""

    async def generate_comparison(
        self,
        user_prompt: str,
        correlation_id: UUID,
        prompt_blocks: list[dict[str, Any]] | None = None,
        system_prompt_override: str | None = None,
        model_override: str | None = None,
        temperature_override: float | None = None,
        max_tokens_override: int | None = None,
    ) -> LLMProviderResponse:
        """Generate LLM comparison response.

        Args:
            user_prompt: Complete comparison prompt with essays embedded
            correlation_id: Request correlation ID for tracing
            system_prompt_override: Optional system prompt override
            model_override: Optional model override
            temperature_override: Optional temperature override
            max_tokens_override: Optional max tokens override

        Returns:
            The LLM provider response containing comparison result

        Raises:
            HuleEduError: On any failure to generate comparison
        """
        ...


class LLMOrchestratorProtocol(Protocol):
    """Protocol for LLM orchestration service."""

    async def perform_comparison(
        self,
        provider: LLMProviderType,
        user_prompt: str,
        correlation_id: UUID,
        prompt_blocks: list[Dict[str, Any]] | None = None,
        request_metadata: Dict[str, Any] | None = None,
        **overrides: Any,
    ) -> LLMQueuedResult:
        """Perform LLM comparison with provider selection.

        Args:
            provider: LLM provider to use
            user_prompt: Complete comparison prompt with essays embedded
            correlation_id: Request correlation ID
            request_metadata: Arbitrary metadata to echo back in callbacks
            **overrides: Additional parameter overrides

        Returns:
            LLMQueuedResult - ALL requests are queued for async processing with callback delivery

        Raises:
            HuleEduError: On any failure to perform comparison
        """
        ...

    async def process_queued_request(
        self,
        provider: LLMProviderType,
        user_prompt: str,
        correlation_id: UUID,
        prompt_blocks: list[Dict[str, Any]] | None = None,
        **overrides: Any,
    ) -> LLMOrchestratorResponse:
        """Process a queued request directly (internal use only).

        This method bypasses queueing and directly calls providers.
        ONLY used by QueueProcessor for processing already-queued requests.

        Args:
            provider: LLM provider to use
            user_prompt: Complete comparison prompt with essays embedded
            correlation_id: Request correlation ID
            **overrides: Additional parameter overrides

        Returns:
            LLMOrchestratorResponse with immediate result

        Raises:
            HuleEduError: On any failure to process request
        """
        ...

    async def test_provider(self, provider: LLMProviderType, correlation_id: UUID) -> bool:
        """Test provider connectivity and availability.

        Args:
            provider: Provider to test
            correlation_id: Request correlation ID for tracing

        Returns:
            True if provider is available and functional

        Raises:
            HuleEduError: On provider test failure with details
        """
        ...


class LLMEventPublisherProtocol(Protocol):
    """Protocol for LLM usage event publishing."""

    async def publish_llm_request_started(
        self,
        provider: str,
        correlation_id: UUID,
        metadata: Dict[str, Any],
    ) -> None:
        """Publish LLM request started event.

        Args:
            provider: LLM provider name
            correlation_id: Request correlation ID
            metadata: Additional event metadata
        """
        ...

    async def publish_llm_request_completed(
        self,
        provider: str,
        correlation_id: UUID,
        success: bool,
        response_time_ms: int,
        metadata: Dict[str, Any],
    ) -> None:
        """Publish LLM request completed event.

        Args:
            provider: LLM provider name
            correlation_id: Request correlation ID
            success: Whether request was successful
            response_time_ms: Response time in milliseconds
            metadata: Additional event metadata
        """
        ...

    async def publish_llm_provider_failure(
        self,
        provider: str,
        failure_type: str,
        correlation_id: UUID,
        error_details: str,
        circuit_breaker_opened: bool = False,
    ) -> None:
        """Publish LLM provider failure event.

        Args:
            provider: LLM provider name
            failure_type: Type of failure
            correlation_id: Request correlation ID
            error_details: Error details
            circuit_breaker_opened: Whether circuit breaker opened
        """
        ...

    async def publish_to_topic(
        self,
        topic: str,
        envelope: EventEnvelope[Any],
        key: Optional[str] = None,
    ) -> None:
        """Publish event to specific topic.

        Args:
            topic: Kafka topic name
            envelope: Event envelope to publish
            key: Optional message key for partitioning
        """
        ...


class LLMRetryManagerProtocol(Protocol):
    """Protocol for LLM request retry management."""

    async def with_retry(
        self,
        operation: Callable[..., Awaitable[Any]],
        operation_name: str,
        **kwargs: Any,
    ) -> Any:
        """Execute operation with retry logic.

        Args:
            operation: Async operation to execute
            operation_name: Name of operation for logging
            **kwargs: Arguments to pass to operation

        Returns:
            Result from operation
        """
        ...


class QueueManagerProtocol(Protocol):
    """Protocol for request queue management."""

    async def enqueue(self, request: QueuedRequest) -> bool:
        """Enqueue a request for later processing.

        Args:
            request: The request to queue

        Returns:
            True if enqueued successfully, False if queue is full
        """
        ...

    async def dequeue(self) -> Optional[QueuedRequest]:
        """Get the next request to process.

        Returns:
            Next request or None if queue is empty
        """
        ...

    async def remove(self, queue_id: UUID) -> bool:
        """Remove a request from the queue by ID.

        Args:
            queue_id: The queue ID to remove

        Returns:
            True if removed successfully, False if not found
        """
        ...

    async def get_status(self, queue_id: UUID) -> Optional[QueuedRequest]:
        """Get status of a queued request.

        Args:
            queue_id: The queue ID to check

        Returns:
            Request details or None if not found
        """
        ...

    async def update_status(
        self,
        queue_id: UUID,
        status: QueueStatus,
        message: Optional[str] = None,
        result_location: Optional[str] = None,
    ) -> bool:
        """Update status of a queued request.

        Args:
            queue_id: The queue ID to update
            status: New status
            message: Optional error or status message
            result_location: Optional result location

        Returns:
            True if updated successfully

        Raises:
            HuleEduError: On failure to update status
        """
        ...

    async def get_queue_stats(self) -> QueueStats:
        """Get current queue statistics.

        Returns:
            Queue statistics
        """
        ...

    async def cleanup_expired(self) -> int:
        """Remove expired requests from queue.

        Returns:
            Number of requests removed
        """
        ...


class QueueRepositoryProtocol(Protocol):
    """Protocol for queue persistence implementations."""

    async def add(self, request: QueuedRequest) -> bool:
        """Add request to queue storage."""
        ...

    async def get_next(self) -> Optional[QueuedRequest]:
        """Get next request by priority and age."""
        ...

    async def get_by_id(self, queue_id: UUID) -> Optional[QueuedRequest]:
        """Get specific request by ID."""
        ...

    async def update(self, request: QueuedRequest) -> bool:
        """Update existing request."""
        ...

    async def delete(self, queue_id: UUID) -> bool:
        """Remove request from queue."""
        ...

    async def get_all_queued(self) -> List[QueuedRequest]:
        """Get all requests with QUEUED status."""
        ...

    async def count(self) -> int:
        """Get total queue size."""
        ...

    async def get_memory_usage(self) -> int:
        """Get total memory usage in bytes."""
        ...


class ConnectionPoolManagerProtocol(Protocol):
    """Protocol for HTTP connection pool management."""

    async def get_session(self, provider: str) -> Any:
        """Get optimized session for specific provider.

        Args:
            provider: Provider name

        Returns:
            HTTP session for the provider
        """
        ...

    async def get_connection_stats(self, provider: str) -> Dict[str, Any]:
        """Get connection statistics for a provider.

        Args:
            provider: Provider name

        Returns:
            Dictionary with connection statistics
        """
        ...

    async def health_check_connections(self) -> Dict[str, bool]:
        """Perform health check on all connection pools.

        Returns:
            Dictionary mapping provider names to health status
        """
        ...

    async def cleanup(self) -> None:
        """Clean up all sessions and connection pools."""
        ...


class ComparisonProcessorProtocol(Protocol):
    """Protocol for processing LLM comparisons - domain logic only."""

    async def process_comparison(
        self,
        provider: LLMProviderType,
        user_prompt: str,
        correlation_id: UUID,
        prompt_blocks: list[dict[str, Any]] | None = None,
        **overrides: Any,
    ) -> "LLMOrchestratorResponse":
        """Process LLM comparison without infrastructure concerns.

        This is pure domain logic - no queuing, no callbacks.
        Used by QueueProcessor for actual LLM invocation.

        Args:
            provider: LLM provider to use
            user_prompt: Complete comparison prompt with essays embedded
            correlation_id: Request correlation ID
            **overrides: Additional parameter overrides

        Returns:
            LLMOrchestratorResponse with immediate result

        Raises:
            HuleEduError: On any failure to process comparison
        """
        ...

    async def process_comparison_batch(
        self,
        items: list[BatchComparisonItem],
    ) -> list[LLMOrchestratorResponse]:
        """Process a batch of LLM comparisons (default: sequential per-request)."""
        ...
