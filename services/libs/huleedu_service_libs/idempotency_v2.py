"""
Redesigned Idempotency Decorator for Kafka Message Handlers - Version 2.0

This is a complete redesign of the idempotency system based on comprehensive research
of industry best practices and analysis of the original implementation flaws.

Key Improvements:
1. Service-namespaced Redis keys for better isolation and debugging
2. Configurable TTL per event type for optimal memory usage
3. Comprehensive observability with structured logging
4. Robust error handling with fail-open behavior
5. Backward-compatible interface for seamless migration
6. Enhanced debugging capabilities for production troubleshooting

Based on research from:
- Industry best practices from AWS, Google Cloud, Azure
- Analysis of HuleEdu event architecture requirements
- Root cause analysis of the original hash collision bug
"""

from __future__ import annotations

import functools
import json
import time
from collections.abc import Awaitable, Callable
from typing import Any, Dict

from aiokafka import ConsumerRecord

from .event_utils import generate_deterministic_event_id
from .logging_utils import create_service_logger
from .protocols import RedisClientProtocol

logger = create_service_logger("idempotency-v2")

# Event-type specific TTL configuration based on business requirements
DEFAULT_EVENT_TYPE_TTLS = {
    # Quick processing events (spellcheck, validation, uploads)
    "huleedu.essay.spellcheck.requested.v1": 3600,  # 1 hour (spellcheck requests)
    "huleedu.essay.spellcheck.completed.v1": 3600,  # 1 hour (spellcheck results)
    "huleedu.file.essay.content.provisioned.v1": 3600,  # 1 hour
    "huleedu.file.essay.validation.failed.v1": 3600,  # 1 hour
    # Batch coordination events (require longer retention for workflow coordination)
    "huleedu.batch.essays.registered.v1": 43200,  # 12 hours
    "huleedu.els.batch.essays.ready.v1": 43200,  # 12 hours
    "huleedu.els.batch.phase.outcome.v1": 43200,  # 12 hours
    # Assessment processing events (complex AI workflows, longer retention)
    "huleedu.cj_assessment.completed.v1": 86400,  # 24 hours
    "huleedu.batch.cj_assessment.initiate.command.v1": 86400,  # 24 hours
    "huleedu.batch.spellcheck.initiate.command.v1": 86400,  # 24 hours
    # Long-running processes (batch operations, migrations, aggregations)
    "huleedu.result_aggregator.batch.completed.v1": 259200,  # 72 hours
    "huleedu.result_aggregator.class.summary.updated.v1": 259200,  # 72 hours
}

# Default TTL for unknown event types
DEFAULT_TTL_SECONDS = 86400  # 24 hours (backward compatibility)


class IdempotencyConfig:
    """Configuration class for idempotency behavior."""

    def __init__(
        self,
        service_name: str,
        event_type_ttls: Dict[str, int] | None = None,
        default_ttl: int = DEFAULT_TTL_SECONDS,
        key_prefix: str = "huleedu:idempotency:v2",
        enable_debug_logging: bool = False,
    ):
        self.service_name = service_name
        self.event_type_ttls = event_type_ttls or DEFAULT_EVENT_TYPE_TTLS.copy()
        self.default_ttl = default_ttl
        self.key_prefix = key_prefix
        self.enable_debug_logging = enable_debug_logging

    def get_ttl_for_event_type(self, event_type: str) -> int:
        """Get the appropriate TTL for a specific event type."""
        return self.event_type_ttls.get(event_type, self.default_ttl)

    def generate_redis_key(self, event_type: str, event_id: str, deterministic_hash: str) -> str:
        """
        Generate a namespaced Redis key for idempotency tracking.

        Format: {prefix}:{service}:{event_type}:{deterministic_hash}

        This provides:
        - Service isolation for debugging
        - Event type visibility for monitoring
        - Deterministic hash for uniqueness
        """
        # Sanitize event type for Redis key (replace dots with underscores)
        safe_event_type = event_type.replace(".", "_")
        return f"{self.key_prefix}:{self.service_name}:{safe_event_type}:{deterministic_hash}"


def idempotent_consumer_v2(
    redis_client: RedisClientProtocol,
    config: IdempotencyConfig,
) -> Callable[[Callable[..., Awaitable[Any]]], Callable[..., Awaitable[Any | None]]]:
    """
    Advanced idempotency decorator with service namespacing and configurable TTLs.

    This redesigned decorator addresses the limitations of the original implementation
    by providing:

    1. **Service Isolation**: Each service maintains separate idempotency namespace
    2. **Event-Type Specific TTLs**: Optimized memory usage based on business requirements
    3. **Enhanced Observability**: Comprehensive structured logging for debugging
    4. **Robust Error Handling**: Fail-open behavior with proper cleanup
    5. **Backward Compatibility**: Drop-in replacement for existing decorator

    Args:
        redis_client: Active Redis client implementing RedisClientProtocol
        config: IdempotencyConfig with service name, TTL settings, and debug options

    Returns:
        Decorator function that wraps message handlers with advanced idempotency logic

    Example:
        ```python
        config = IdempotencyConfig(
            service_name="essay-lifecycle-service",
            enable_debug_logging=True
        )

        @idempotent_consumer_v2(redis_client=redis_client, config=config)
        async def handle_message(msg: ConsumerRecord) -> Any:
            # Process message logic here
            return result
        ```
    """

    def decorator(func: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any | None]]:
        @functools.wraps(func)
        async def wrapper(msg: ConsumerRecord, *args: Any, **kwargs: Any) -> Any | None:
            start_time = time.time()

            try:
                # Parse event envelope for metadata
                event_dict = json.loads(msg.value)
                event_id = event_dict.get("event_id")
                event_type = event_dict.get("event_type", "unknown")
                correlation_id = event_dict.get("correlation_id")
                source_service = event_dict.get("source_service", "unknown")

                # Generate deterministic hash using existing proven logic
                deterministic_hash = generate_deterministic_event_id(msg.value)

                # Create service-namespaced Redis key
                redis_key = config.generate_redis_key(event_type, event_id, deterministic_hash)

                # Get TTL for this specific event type
                ttl_seconds = config.get_ttl_for_event_type(event_type)

                # Structured logging for observability
                log_context = {
                    "service": config.service_name,
                    "event_type": event_type,
                    "event_id": event_id,
                    "correlation_id": correlation_id,
                    "source_service": source_service,
                    "deterministic_hash": deterministic_hash[:16]
                    + "...",  # Truncated for readability
                    "redis_key": redis_key,
                    "ttl_seconds": ttl_seconds,
                    "kafka_topic": msg.topic,
                    "kafka_partition": msg.partition,
                    "kafka_offset": msg.offset,
                }

                if config.enable_debug_logging:
                    logger.debug("Starting idempotency check", extra=log_context)

                # Atomic Redis SETNX operation
                redis_start = time.time()
                is_first_time = await redis_client.set_if_not_exists(
                    redis_key,
                    json.dumps(
                        {
                            "processed_at": time.time(),
                            "processed_by": config.service_name,
                            "event_id": event_id,
                            "correlation_id": correlation_id,
                            "source_service": source_service,
                        }
                    ),
                    ttl_seconds=ttl_seconds,
                )
                redis_duration = time.time() - redis_start

                log_context["redis_duration_ms"] = round(redis_duration * 1000, 2)

                if not is_first_time:
                    # Duplicate detected - enhanced logging for debugging
                    logger.warning(
                        "DUPLICATE_EVENT_DETECTED: Event already processed, skipping",
                        extra={
                            **log_context,
                            "action": "skipped_duplicate",
                            "total_duration_ms": round((time.time() - start_time) * 1000, 2),
                        },
                    )
                    return None  # Signal duplicate to caller

                # First-time processing
                if config.enable_debug_logging:
                    logger.debug(
                        "FIRST_TIME_EVENT: Processing new event",
                        extra={**log_context, "action": "processing_new"},
                    )

                # Execute business logic
                try:
                    processing_start = time.time()
                    result = await func(msg, *args, **kwargs)
                    processing_duration = time.time() - processing_start

                    # Success logging
                    logger.debug(
                        "PROCESSING_SUCCESS: Event processed successfully",
                        extra={
                            **log_context,
                            "action": "completed_successfully",
                            "processing_duration_ms": round(processing_duration * 1000, 2),
                            "total_duration_ms": round((time.time() - start_time) * 1000, 2),
                        },
                    )

                    return result

                except Exception as processing_error:
                    # Processing failed - release idempotency lock for retry
                    logger.error(
                        "PROCESSING_FAILED: Releasing idempotency lock for retry",
                        extra={
                            **log_context,
                            "action": "failed_releasing_lock",
                            "error": str(processing_error),
                            "error_type": type(processing_error).__name__,
                        },
                        exc_info=True,
                    )

                    # Cleanup idempotency key to allow retry
                    try:
                        cleanup_start = time.time()
                        deleted_count = await redis_client.delete_key(redis_key)
                        cleanup_duration = time.time() - cleanup_start

                        logger.debug(
                            "CLEANUP_SUCCESS: Idempotency key released for retry",
                            extra={
                                **log_context,
                                "action": "cleanup_completed",
                                "deleted_keys": deleted_count,
                                "cleanup_duration_ms": round(cleanup_duration * 1000, 2),
                            },
                        )

                    except Exception as cleanup_error:
                        logger.error(
                            "CLEANUP_FAILED: Could not release idempotency key",
                            extra={
                                **log_context,
                                "action": "cleanup_failed",
                                "cleanup_error": str(cleanup_error),
                                "cleanup_error_type": type(cleanup_error).__name__,
                            },
                            exc_info=True,
                        )

                    # Re-raise original processing exception
                    raise processing_error

            except json.JSONDecodeError as json_error:
                # Invalid JSON - fail open and process anyway
                logger.error(
                    "INVALID_JSON: Message is not valid JSON, processing without idempotency",
                    extra={
                        "service": config.service_name,
                        "action": "processing_without_idempotency",
                        "error": str(json_error),
                        "kafka_topic": msg.topic,
                        "kafka_partition": msg.partition,
                        "kafka_offset": msg.offset,
                        "raw_message_length": len(msg.value),
                    },
                    exc_info=True,
                )
                return await func(msg, *args, **kwargs)

            except Exception as redis_error:
                # Redis operation failed - fail open and process anyway
                logger.error(
                    "REDIS_ERROR: Idempotency check failed, processing without protection",
                    extra={
                        "service": config.service_name,
                        "action": "processing_without_idempotency",
                        "error": str(redis_error),
                        "error_type": type(redis_error).__name__,
                        "kafka_topic": msg.topic,
                        "kafka_partition": msg.partition,
                        "kafka_offset": msg.offset,
                        "total_duration_ms": round((time.time() - start_time) * 1000, 2),
                    },
                    exc_info=True,
                )
                return await func(msg, *args, **kwargs)

        return wrapper

    return decorator


# Backward compatibility function - provides same interface as original decorator
def idempotent_consumer(
    redis_client: RedisClientProtocol,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
    service_name: str = "unknown-service",
) -> Callable[[Callable[..., Awaitable[Any]]], Callable[..., Awaitable[Any | None]]]:
    """
    Backward-compatible wrapper for the original idempotent_consumer interface.

    This function provides a seamless migration path from the original decorator
    while leveraging the improved v2 implementation under the hood.

    Args:
        redis_client: Active Redis client
        ttl_seconds: TTL for idempotency keys (backward compatibility)
        service_name: Service identifier for namespacing

    Returns:
        Decorator with the same interface as the original implementation
    """
    config = IdempotencyConfig(
        service_name=service_name,
        default_ttl=ttl_seconds,
        enable_debug_logging=False,  # Disabled by default for backward compatibility
    )

    return idempotent_consumer_v2(redis_client=redis_client, config=config)
