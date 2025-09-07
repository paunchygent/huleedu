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

    async def check_credits_bulk(
        self,
        user_id: str,
        org_id: str | None,
        requirements: dict[str, int],
        correlation_id: str,
    ) -> dict[str, Any]:
        """Bulk credit check against Entitlements bulk endpoint.

        Returns the response body with keys: allowed, available_credits,
        required_credits, per_metric, denial_reason?, correlation_id.
        """
        tracer = get_tracer("batch_orchestrator_service")

        request_data = {
            "user_id": user_id,
            "org_id": org_id,
            "requirements": requirements,
            "correlation_id": correlation_id,
        }

        url = f"{self.base_url}/v1/entitlements/check-credits/bulk"

        with trace_operation(
            tracer,
            "entitlements.check_credits_bulk",
            {
                "http.method": "POST",
                "http.url": url,
                "user_id": user_id,
                "org_id": org_id,
                "correlation_id": correlation_id,
                "required_resources": len(requirements),
            },
        ):
            try:
                async with aiohttp.ClientSession(timeout=self.timeout) as session:
                    logger.info(
                        "Bulk credit check with entitlements service",
                        extra={
                            "user_id": user_id,
                            "org_id": org_id,
                            "requirements": requirements,
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

                        def _parse_body() -> dict[str, Any]:
                            try:
                                body: dict[str, Any] = json.loads(response_text)
                                return body
                            except json.JSONDecodeError as e:
                                err = f"Invalid JSON in entitlements response: {e}"
                                logger.error(err, extra={"correlation_id": correlation_id})
                                raise ValueError(err) from e

                        if response.status in (200, 402, 429):
                            body = _parse_body()
                            logger.info(
                                "Bulk credit check response",
                                extra={
                                    "user_id": user_id,
                                    "org_id": org_id,
                                    "status": response.status,
                                    "allowed": body.get("allowed"),
                                    "correlation_id": correlation_id,
                                },
                            )
                            return body

                        elif response.status == 400:
                            logger.error(
                                "Invalid bulk credit check request",
                                extra={
                                    "status_code": response.status,
                                    "response": response_text,
                                    "correlation_id": correlation_id,
                                },
                            )
                            raise ValueError(f"Invalid request format: {response_text}")

                        elif response.status == 404:
                            logger.error(
                                "Entitlements resource not found",
                                extra={
                                    "status_code": response.status,
                                    "response": response_text,
                                    "correlation_id": correlation_id,
                                },
                            )
                            raise ValueError(f"Resource not found: {response_text}")

                        elif response.status >= 500:
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
                    "Unexpected error during bulk credit check",
                    extra={
                        "user_id": user_id,
                        "org_id": org_id,
                        "correlation_id": correlation_id,
                    },
                    exc_info=True,
                )
                raise
