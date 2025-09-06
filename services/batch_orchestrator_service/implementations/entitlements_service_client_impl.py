"""Implementation of EntitlementsServiceProtocol for HTTP-based credit checking."""

import json
import logging
from typing import Any

import aiohttp
from huleedu_service_libs.observability import get_tracer, trace_operation

from services.batch_orchestrator_service.protocols import EntitlementsServiceProtocol

logger = logging.getLogger(__name__)


class EntitlementsServiceClientImpl(EntitlementsServiceProtocol):
    """HTTP client implementation for Entitlements Service communication."""

    def __init__(self, base_url: str, timeout_seconds: float = 10.0) -> None:
        """Initialize with entitlements service configuration.

        Args:
            base_url: Base URL of the entitlements service (e.g., "http://localhost:8083")
            timeout_seconds: Request timeout in seconds
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = aiohttp.ClientTimeout(total=timeout_seconds)

    async def check_credits(
        self,
        user_id: str,
        org_id: str | None,
        required_credits: list[tuple[str, int]],
        correlation_id: str,
    ) -> dict[str, Any]:
        """Check if sufficient credits are available for the given requirements.

        Makes HTTP POST request to /v1/entitlements/check-credits endpoint.

        Args:
            user_id: User requesting the credits
            org_id: Organization ID (if applicable)
            required_credits: List of (metric_name, quantity) tuples
            correlation_id: Request correlation ID for tracing

        Returns:
            Dict with credit availability information:
            {
                "sufficient": bool,
                "available_credits": int,
                "required_credits": int,
                "source": "user" | "org",
                "details": {...}
            }

        Raises:
            aiohttp.ClientError: If HTTP communication fails
            ValueError: If response format is invalid
            Exception: If entitlements service returns error
        """
        tracer = get_tracer("batch_orchestrator_service")

        # Convert required_credits list to dict for JSON serialization
        credit_requirements = {}
        for metric_name, quantity in required_credits:
            credit_requirements[metric_name] = quantity

        request_data = {
            "user_id": user_id,
            "org_id": org_id,
            "requirements": credit_requirements,
            "correlation_id": correlation_id,
        }

        url = f"{self.base_url}/v1/entitlements/check-credits"

        with trace_operation(
            tracer,
            "entitlements.check_credits",
            {
                "http.method": "POST",
                "http.url": url,
                "user_id": user_id,
                "org_id": org_id,
                "correlation_id": correlation_id,
                "required_resources": len(required_credits),
            },
        ):
            try:
                async with aiohttp.ClientSession(timeout=self.timeout) as session:
                    logger.info(
                        "Checking credits with entitlements service",
                        extra={
                            "user_id": user_id,
                            "org_id": org_id,
                            "requirements": credit_requirements,
                            "correlation_id": correlation_id,
                            "url": url,
                        },
                    )

                    async with session.post(
                        url,
                        json=request_data,
                        headers={
                            "Content-Type": "application/json",
                            "X-Correlation-ID": correlation_id,
                        },
                    ) as response:
                        response_text = await response.text()

                        if response.status == 200:
                            try:
                                result: dict[str, Any] = json.loads(response_text)
                                logger.info(
                                    "Credit check completed successfully",
                                    extra={
                                        "user_id": user_id,
                                        "org_id": org_id,
                                        "sufficient": result.get("sufficient"),
                                        "correlation_id": correlation_id,
                                    },
                                )
                                return result
                            except json.JSONDecodeError as e:
                                error_msg = f"Invalid JSON in entitlements response: {e}"
                                logger.error(error_msg, extra={"correlation_id": correlation_id})
                                raise ValueError(error_msg) from e

                        elif response.status == 400:
                            # Client error - invalid request format
                            logger.error(
                                "Invalid credit check request format",
                                extra={
                                    "status_code": response.status,
                                    "response": response_text,
                                    "correlation_id": correlation_id,
                                },
                            )
                            raise ValueError(f"Invalid request format: {response_text}")

                        elif response.status == 404:
                            # User/org not found
                            logger.error(
                                "User or organization not found in entitlements",
                                extra={
                                    "user_id": user_id,
                                    "org_id": org_id,
                                    "status_code": response.status,
                                    "correlation_id": correlation_id,
                                },
                            )
                            raise ValueError(f"User or organization not found: {user_id}, {org_id}")

                        elif response.status >= 500:
                            # Server error - entitlements service issue
                            logger.error(
                                "Entitlements service error",
                                extra={
                                    "status_code": response.status,
                                    "response": response_text,
                                    "correlation_id": correlation_id,
                                },
                            )
                            raise Exception(
                                f"Entitlements service error: {response.status} - {response_text}"
                            )

                        else:
                            # Unexpected status code
                            logger.error(
                                "Unexpected response from entitlements service",
                                extra={
                                    "status_code": response.status,
                                    "response": response_text,
                                    "correlation_id": correlation_id,
                                },
                            )
                            raise Exception(
                                f"Unexpected response: {response.status} - {response_text}"
                            )

            except aiohttp.ClientError as e:
                error_msg = f"Failed to communicate with entitlements service: {e}"
                logger.error(
                    error_msg,
                    extra={
                        "user_id": user_id,
                        "org_id": org_id,
                        "correlation_id": correlation_id,
                        "url": url,
                    },
                    exc_info=True,
                )
                raise Exception(error_msg) from e
            except Exception:
                logger.error(
                    "Unexpected error during credit check",
                    extra={
                        "user_id": user_id,
                        "org_id": org_id,
                        "correlation_id": correlation_id,
                    },
                    exc_info=True,
                )
                raise
