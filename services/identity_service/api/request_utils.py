"""Request utility functions for Identity Service API routes.

Provides common utilities for handling HTTP request data:
- Correlation ID extraction and generation
- Client information extraction (IP address, user agent)
- Device information parsing from user agent strings
- JWT token extraction from Authorization headers

These utilities are shared across all Identity Service route modules.
"""

from __future__ import annotations

import uuid
from uuid import UUID

from huleedu_service_libs.logging_utils import create_service_logger
from quart import request

logger = create_service_logger("identity_service.api.request_utils")


def extract_correlation_id() -> UUID:
    """Extract correlation ID from request headers or generate new one.

    Returns:
        UUID: Correlation ID from X-Correlation-ID header or generated UUID
    """
    correlation_header = request.headers.get("X-Correlation-ID")
    if correlation_header:
        try:
            return UUID(correlation_header)
        except ValueError:
            logger.warning(
                f"Invalid correlation ID format in header: {correlation_header}, generating new one"
            )
            return uuid.uuid4()
    return uuid.uuid4()


def extract_client_info() -> tuple[str | None, str | None]:
    """Extract client IP and user agent from request.

    Handles proxy scenarios by checking X-Forwarded-For header first.

    Returns:
        tuple: (ip_address, user_agent) - either can be None
    """
    # Get IP address from headers (considering proxy)
    ip_address = request.headers.get("X-Forwarded-For")
    if ip_address:
        # Take the first IP if there are multiple (client IP)
        ip_address = ip_address.split(",")[0].strip()
    else:
        # Fallback to direct connection IP
        ip_address = request.remote_addr

    # Get user agent
    user_agent = request.headers.get("User-Agent")

    return ip_address, user_agent


def parse_device_info(user_agent: str | None) -> tuple[str | None, str | None]:
    """Parse device name and type from user agent string.

    Performs simple device type detection based on common patterns.

    Args:
        user_agent: User agent string from request headers

    Returns:
        tuple: (device_name, device_type) - both can be None

    Device types: mobile, ios, desktop, unknown
    Device names: Chrome, Firefox, Safari, Edge, Unknown Browser
    """
    if not user_agent:
        return None, None

    # Simple device type detection
    user_agent_lower = user_agent.lower()

    device_type = None
    if "mobile" in user_agent_lower or "android" in user_agent_lower:
        device_type = "mobile"
    elif "iphone" in user_agent_lower or "ipad" in user_agent_lower:
        device_type = "ios"
    elif "windows" in user_agent_lower:
        device_type = "desktop"
    elif "mac" in user_agent_lower:
        device_type = "desktop"
    elif "linux" in user_agent_lower:
        device_type = "desktop"
    else:
        device_type = "unknown"

    # Extract browser as device name (simplified)
    device_name = None
    if "chrome" in user_agent_lower:
        device_name = "Chrome"
    elif "firefox" in user_agent_lower:
        device_name = "Firefox"
    elif "safari" in user_agent_lower and "chrome" not in user_agent_lower:
        device_name = "Safari"
    elif "edge" in user_agent_lower:
        device_name = "Edge"
    else:
        device_name = "Unknown Browser"

    return device_name, device_type


def extract_jwt_token() -> str | None:
    """Extract JWT token from Authorization header.

    Returns:
        str | None: JWT token without 'Bearer ' prefix, or None if not found
    """
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:]  # Remove 'Bearer ' prefix
    return None


def extract_token_from_body_or_header() -> str | None:
    """Extract token from Authorization header.

    Note: Body extraction should be handled by the route since it requires async.
    This function only handles the Authorization header.

    Returns:
        str | None: Token from header, or None if not found
    """
    # Only try Authorization header (body requires async)
    return extract_jwt_token()


def validate_request_size(max_size_kb: int = 10) -> bool:
    """Validate request body size to prevent abuse.

    Args:
        max_size_kb: Maximum allowed request size in KB

    Returns:
        bool: True if request size is acceptable
    """
    content_length = request.headers.get("Content-Length")
    if content_length:
        try:
            size_bytes = int(content_length)
            max_bytes = max_size_kb * 1024
            return size_bytes <= max_bytes
        except ValueError:
            return False
    return True  # No content length header
