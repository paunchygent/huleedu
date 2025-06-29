"""Security service implementation."""
from __future__ import annotations

from typing import List

from huleedu_service_libs.logging_utils import create_service_logger

from services.result_aggregator_service.protocols import SecurityServiceProtocol

logger = create_service_logger("result_aggregator.security")


class SecurityServiceImpl(SecurityServiceProtocol):
    """Implementation of security service for API authentication."""

    def __init__(self, internal_api_key: str, allowed_service_ids: List[str]):
        """Initialize with API key and allowed services."""
        self.internal_api_key = internal_api_key
        self.allowed_service_ids = set(allowed_service_ids)

    async def validate_service_credentials(self, api_key: str, service_id: str) -> bool:
        """Validate service-to-service authentication."""
        # Check API key
        if api_key != self.internal_api_key:
            logger.warning(
                "Invalid API key provided",
                service_id=service_id,
            )
            return False

        # Check service ID is allowed
        if service_id not in self.allowed_service_ids:
            logger.warning(
                "Service not allowed",
                service_id=service_id,
                allowed_services=list(self.allowed_service_ids),
            )
            return False

        logger.debug(
            "Service authenticated successfully",
            service_id=service_id,
        )
        return True
