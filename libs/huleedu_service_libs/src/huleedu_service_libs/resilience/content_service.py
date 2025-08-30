"""Circuit breaker Content Service client wrapper.

This module provides a typed wrapper for Content Service clients that adds
circuit breaker protection while maintaining full protocol compatibility.
"""

from uuid import UUID

from common_core.domain_enums import ContentType

from huleedu_service_libs.http_client.protocols import ContentServiceClientProtocol
from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.resilience.circuit_breaker import CircuitBreaker

logger = create_service_logger("circuit_breaker_content_service")


class CircuitBreakerContentServiceClient(ContentServiceClientProtocol):
    """Content Service client with circuit breaker protection.

    This wrapper implements ContentServiceClientProtocol and adds circuit breaker
    protection to all Content Service operations. It delegates all actual work
    to the underlying client while providing resilience through the circuit
    breaker pattern.

    Circuit Breaker Behavior:
    - CLOSED: All requests pass through normally
    - OPEN: Requests are blocked and CircuitBreakerError is raised
    - HALF_OPEN: Limited requests allowed to test recovery
    """

    def __init__(
        self, delegate: ContentServiceClientProtocol, circuit_breaker: CircuitBreaker
    ) -> None:
        """Initialize circuit breaker Content Service client.

        Args:
            delegate: The actual Content Service client implementation
            circuit_breaker: Circuit breaker for resilience protection
        """
        self._delegate = delegate
        self._circuit_breaker = circuit_breaker

    async def fetch_content(
        self,
        storage_id: str,
        correlation_id: UUID,
        essay_id: str | None = None,
    ) -> str:
        """Fetch content by storage ID with circuit breaker protection.

        Args:
            storage_id: Content storage identifier
            correlation_id: Request correlation ID for tracing
            essay_id: Optional essay ID for logging context

        Returns:
            Content text

        Raises:
            CircuitBreakerError: If circuit is open
            HuleEduError: On fetch failure, content not found, or service error
        """
        logger.debug(
            f"Fetching content {storage_id} through circuit breaker",
            extra={"correlation_id": str(correlation_id), "storage_id": storage_id},
        )
        return await self._circuit_breaker.call(
            self._delegate.fetch_content, storage_id, correlation_id, essay_id
        )

    async def store_content(
        self,
        content: str,
        content_type: ContentType,
        correlation_id: UUID,
        essay_id: str | None = None,
    ) -> str:
        """Store content to Content Service with circuit breaker protection.

        Args:
            content: Content text to store
            content_type: Type of content being stored
            correlation_id: Request correlation ID for tracing
            essay_id: Optional essay ID for logging context

        Returns:
            New storage ID for the stored content

        Raises:
            CircuitBreakerError: If circuit is open
            HuleEduError: On storage failure or invalid response
        """
        logger.debug(
            f"Storing content ({content_type.value}, {len(content)} chars) through circuit breaker",
            extra={
                "correlation_id": str(correlation_id),
                "content_type": content_type.value,
                "content_length": len(content),
            },
        )
        return await self._circuit_breaker.call(
            self._delegate.store_content, content, content_type, correlation_id, essay_id
        )
