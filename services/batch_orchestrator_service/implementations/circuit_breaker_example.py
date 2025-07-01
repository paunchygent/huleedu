"""
Example implementation of circuit breaker for HTTP client calls in Batch Orchestrator Service.

This shows how to protect external service calls with circuit breaker pattern.
"""

from datetime import timedelta
from typing import Optional

import aiohttp
from aiohttp import ClientError

from services.libs.huleedu_service_libs.resilience import CircuitBreaker, circuit_breaker
from services.libs.huleedu_service_libs.observability import get_tracer
from services.libs.huleedu_service_libs.observability.custom_logger import get_logger


logger = get_logger(__name__)


class ResilientHttpClient:
    """HTTP client with circuit breaker protection."""

    def __init__(self, service_name: str):
        self.service_name = service_name
        self.tracer = get_tracer(service_name)
        
        # Create circuit breakers for different endpoints
        self.essay_lifecycle_breaker = CircuitBreaker(
            name=f"{service_name}.essay_lifecycle",
            failure_threshold=3,
            recovery_timeout=timedelta(seconds=30),
            success_threshold=2,
            expected_exception=ClientError,
            tracer=self.tracer,
        )
        
        self.cj_assessment_breaker = CircuitBreaker(
            name=f"{service_name}.cj_assessment",
            failure_threshold=5,
            recovery_timeout=timedelta(seconds=60),
            expected_exception=ClientError,
            tracer=self.tracer,
        )

    async def call_essay_lifecycle(
        self, 
        session: aiohttp.ClientSession,
        endpoint: str,
        **kwargs
    ) -> dict:
        """Make HTTP call to Essay Lifecycle Service with circuit breaker."""
        
        async def _make_request():
            async with session.get(f"http://essay_lifecycle_service:8080{endpoint}", **kwargs) as response:
                response.raise_for_status()
                return await response.json()
        
        # Use circuit breaker to protect the call
        return await self.essay_lifecycle_breaker.call(_make_request)

    async def call_cj_assessment(
        self,
        session: aiohttp.ClientSession,
        endpoint: str,
        **kwargs
    ) -> dict:
        """Make HTTP call to CJ Assessment Service with circuit breaker."""
        
        async def _make_request():
            async with session.post(f"http://cj_assessment_service:8080{endpoint}", **kwargs) as response:
                response.raise_for_status()
                return await response.json()
        
        return await self.cj_assessment_breaker.call(_make_request)


# Alternative: Using decorator pattern
class ServiceClient:
    """Example using circuit breaker decorator."""
    
    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
    
    @circuit_breaker(
        failure_threshold=3,
        recovery_timeout=timedelta(seconds=30),
        expected_exception=ClientError,
        name="spell_checker_service"
    )
    async def check_spelling(self, text: str) -> dict:
        """Call spell checker service with circuit breaker protection."""
        if not self.session:
            self.session = aiohttp.ClientSession()
        
        async with self.session.post(
            "http://spell_checker_service:8080/api/v1/check",
            json={"text": text}
        ) as response:
            response.raise_for_status()
            return await response.json()


# Usage in a protocol implementation
from typing import Protocol


class EssayLifecycleClientProtocol(Protocol):
    """Protocol for Essay Lifecycle Service client."""
    
    async def get_essay_status(self, essay_id: str) -> dict:
        """Get essay status."""
        ...


class ResilientEssayLifecycleClient:
    """Implementation with circuit breaker."""
    
    def __init__(self, http_client: ResilientHttpClient, session: aiohttp.ClientSession):
        self.http_client = http_client
        self.session = session
    
    async def get_essay_status(self, essay_id: str) -> dict:
        """Get essay status with circuit breaker protection."""
        try:
            return await self.http_client.call_essay_lifecycle(
                self.session,
                f"/api/v1/essays/{essay_id}/status"
            )
        except Exception as e:
            logger.error(f"Failed to get essay status: {e}")
            # Return a default/cached value or propagate error based on business logic
            raise