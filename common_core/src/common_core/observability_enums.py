"""
common_core.observability_enums - Enums for metrics, monitoring, and observability.
"""

from __future__ import annotations

from enum import Enum


class MetricName(str, Enum):
    """Canonical names for key business metrics."""

    PIPELINE_EXECUTION_TIME = "pipeline_execution_time"
    ESSAY_PROCESSING_RATE = "essay_processing_rate"
    KAFKA_CONSUMER_LAG = "kafka_consumer_lag"
    CONTENT_SERVICE_LATENCY = "content_service_latency"
    LLM_API_CALL_DURATION = "llm_api_call_duration"


class OperationType(str, Enum):
    """Types of operations for metrics collection."""

    UPLOAD = "upload"
    DOWNLOAD = "download"
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    PUBLISH = "publish"
    CONSUME = "consume"


class CacheOperation(str, Enum):
    """Types of cache operations."""

    GET = "get"
    SET = "set"
    DELETE = "delete"
    CLEAR = "clear"
