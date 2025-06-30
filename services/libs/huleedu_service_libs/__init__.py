"""
HuleEdu Service Libraries Package.

This package contains shared utilities and libraries used across
HuleEdu microservices, including Kafka client utilities and common
service infrastructure components.
"""

# HuleEdu Service Libraries Package
from huleedu_service_libs.kafka_client import KafkaBus
from huleedu_service_libs.redis_client import RedisClient
from huleedu_service_libs.observability import (
    init_tracing,
    trace_operation,
    get_current_trace_id,
    inject_trace_context,
    extract_trace_context,
)
from huleedu_service_libs.middleware import setup_tracing_middleware

__all__ = [
    "KafkaBus",
    "RedisClient",
    "init_tracing",
    "trace_operation",
    "get_current_trace_id",
    "inject_trace_context",
    "extract_trace_context",
    "setup_tracing_middleware",
]
