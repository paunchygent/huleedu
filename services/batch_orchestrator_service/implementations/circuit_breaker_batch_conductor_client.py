"""Service-specific circuit breaker batch conductor client wrapper.

This module provides a typed wrapper for batch conductor clients that adds
circuit breaker protection while maintaining full protocol compatibility.
This wrapper lives within the Batch Orchestrator Service to respect
architectural boundaries.
"""

from typing import Any

from common_core.pipeline_models import PhaseName
from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.resilience.circuit_breaker import CircuitBreaker

from services.batch_orchestrator_service.protocols import BatchConductorClientProtocol

logger = create_service_logger("circuit_breaker_batch_conductor_client")


class CircuitBreakerBatchConductorClient(BatchConductorClientProtocol):
    """Batch conductor client with circuit breaker protection.

    This wrapper implements BatchConductorClientProtocol and adds circuit breaker
    protection to all batch conductor operations. It delegates all actual work
    to the underlying client while providing resilience through the circuit
    breaker pattern.

    This is a SERVICE-SPECIFIC wrapper that lives within the Batch Orchestrator
    Service to respect architectural boundaries. It imports the service's own
    protocols while using the shared CircuitBreaker mechanism.

    Circuit Breaker Behavior:
    - CLOSED: All requests pass through normally
    - OPEN: Requests are blocked and CircuitBreakerError is raised
    - HALF_OPEN: Limited requests allowed to test recovery
    """

    def __init__(
        self, delegate: BatchConductorClientProtocol, circuit_breaker: CircuitBreaker
    ) -> None:
        """Initialize circuit breaker batch conductor client.

        Args:
            delegate: The actual batch conductor client implementation
            circuit_breaker: Circuit breaker for resilience protection
        """
        self._delegate = delegate
        self._circuit_breaker = circuit_breaker

    async def resolve_pipeline(
        self, batch_id: str, requested_pipeline: PhaseName, correlation_id: str
    ) -> dict[str, Any]:
        """Request pipeline resolution with circuit breaker protection.

        Args:
            batch_id: The unique identifier of the target batch
            requested_pipeline: The final pipeline the user wants to run
            correlation_id: The correlation ID from the original request for event tracking

        Returns:
            BCS response containing resolved pipeline and analysis

        Raises:
            CircuitBreakerError: If circuit is open
            Exception: If BCS communication fails or returns error
        """
        logger.debug(
            "Resolving pipeline through circuit breaker",
            extra={
                "correlation_id": correlation_id,
                "batch_id": batch_id,
                "requested_pipeline": requested_pipeline,
            },
        )
        return await self._circuit_breaker.call(
            self._delegate.resolve_pipeline,
            batch_id,
            requested_pipeline,
            correlation_id,
        )

    async def report_phase_completion(
        self,
        batch_id: str,
        completed_phase: PhaseName,
        success: bool = True,
    ) -> None:
        """Report phase completion with circuit breaker protection.

        Args:
            batch_id: The unique identifier of the batch
            completed_phase: The phase that has completed
            success: Whether the phase completed successfully

        Note: This is a best-effort operation - failures should be logged but not block.

        Raises:
            CircuitBreakerError: If circuit is open (though this should be handled gracefully)
        """
        logger.debug(
            "Reporting phase completion through circuit breaker",
            extra={
                "batch_id": batch_id,
                "completed_phase": completed_phase,
                "success": success,
            },
        )
        return await self._circuit_breaker.call(
            self._delegate.report_phase_completion,
            batch_id,
            completed_phase,
            success,
        )

    # Add other methods from BatchConductorClientProtocol as needed
    # This is a template - the actual methods depend on the protocol definition
