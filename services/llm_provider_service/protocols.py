"""Protocol definitions for LLM Provider Service."""

from typing import Any, Awaitable, Callable, Dict, List, Optional, Protocol, Tuple
from uuid import UUID

from common_core import LLMProviderType, QueueStatus
from services.llm_provider_service.internal_models import (
    LLMOrchestratorResponse,
    LLMProviderError,
    LLMProviderResponse,
)


class LLMProviderProtocol(Protocol):
    """Protocol for individual LLM provider implementations."""

    async def generate_comparison(
        self,
        user_prompt: str,
        essay_a: str,
        essay_b: str,
        system_prompt_override: str | None = None,
        model_override: str | None = None,
        temperature_override: float | None = None,
        max_tokens_override: int | None = None,
    ) -> Tuple[LLMProviderResponse | None, LLMProviderError | None]:
        """Generate LLM comparison response.

        Args:
            user_prompt: The comparison prompt
            essay_a: First essay to compare
            essay_b: Second essay to compare
            system_prompt_override: Optional system prompt override
            model_override: Optional model override
            temperature_override: Optional temperature override
            max_tokens_override: Optional max tokens override

        Returns:
            Tuple of (response_model, error_model)
        """
        ...


class LLMOrchestratorProtocol(Protocol):
    """Protocol for LLM orchestration service."""

    async def perform_comparison(
        self,
        provider: LLMProviderType,
        user_prompt: str,
        essay_a: str,
        essay_b: str,
        correlation_id: UUID,
        **overrides: Any,
    ) -> Tuple[LLMOrchestratorResponse | None, LLMProviderError | None]:
        """Perform LLM comparison with provider selection.

        Args:
            provider: LLM provider to use
            user_prompt: The comparison prompt
            essay_a: First essay to compare
            essay_b: Second essay to compare
            correlation_id: Request correlation ID
            **overrides: Additional parameter overrides

        Returns:
            Tuple of (response_model, error_model)
        """
        ...

    async def test_provider(self, provider: LLMProviderType) -> Tuple[bool, str]:
        """Test provider connectivity and availability.

        Args:
            provider: Provider to test

        Returns:
            Tuple of (success, message)
        """
        ...


class LLMCacheManagerProtocol(Protocol):
    """Protocol for LLM response caching."""

    async def get_cached_response(self, cache_key: str) -> Dict[str, Any] | None:
        """Get cached LLM response.

        Args:
            cache_key: Cache key for the response

        Returns:
            Cached response dict or None if not found
        """
        ...

    async def cache_response(
        self, cache_key: str, response: Dict[str, Any], ttl: int = 3600
    ) -> None:
        """Cache LLM response.

        Args:
            cache_key: Cache key for the response
            response: Response to cache
            ttl: Time to live in seconds
        """
        ...

    def generate_cache_key(
        self, provider: str, user_prompt: str, essay_a: str, essay_b: str, **params: Any
    ) -> str:
        """Generate consistent cache key for LLM request.

        Args:
            provider: LLM provider name
            user_prompt: The comparison prompt
            essay_a: First essay to compare
            essay_b: Second essay to compare
            **params: Additional parameters affecting the response

        Returns:
            Cache key string
        """
        ...

    async def is_cache_healthy(self) -> Dict[str, Any]:
        """Check cache health status for monitoring.

        Returns:
            Dict containing cache health information
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


class LLMCacheRepositoryProtocol(Protocol):
    """Protocol for cache repository implementations."""

    async def get(self, key: str) -> Dict[str, Any] | None:
        """Get value from cache."""
        ...

    async def set(self, key: str, value: Dict[str, Any], ttl: int) -> None:
        """Set value in cache with TTL."""
        ...

    async def delete(self, key: str) -> None:
        """Delete value from cache."""
        ...

    async def clear(self) -> None:
        """Clear all cached values."""
        ...

    async def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        ...


# Import queue models for type hints
from services.llm_provider_service.queue_models import QueuedRequest, QueueStats


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
        error_message: Optional[str] = None,
        result_location: Optional[str] = None,
    ) -> bool:
        """Update status of a queued request.

        Args:
            queue_id: The queue ID to update
            status: New status
            error_message: Optional error message
            result_location: Optional result location

        Returns:
            True if updated successfully
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
