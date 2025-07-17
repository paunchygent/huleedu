"""
HuleEdu Service Libraries Package.

This package contains shared utilities and libraries used across
HuleEdu microservices, including Kafka client utilities and common
service infrastructure components.
"""

# HuleEdu Service Libraries Package
from .kafka_client import KafkaBus
from .observability import (
    extract_trace_context,
    get_current_trace_id,
    init_tracing,
    inject_trace_context,
    trace_operation,
)
from .quart_app import HuleEduApp
from .redis_client import RedisClient

__all__ = [
    "HuleEduApp",
    "KafkaBus",
    "RedisClient",
    "init_tracing",
    "trace_operation",
    "get_current_trace_id",
    "inject_trace_context",
    "extract_trace_context",
]

# Framework-specific middleware should be imported directly from:
# - huleedu_service_libs.middleware.frameworks.quart_middleware
# - huleedu_service_libs.middleware.frameworks.fastapi_middleware
