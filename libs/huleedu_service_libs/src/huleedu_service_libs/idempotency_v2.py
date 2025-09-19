"""
Redesigned Idempotency Decorator for Kafka Message Handlers - Version 2.0

This is a complete redesign of the idempotency system based on comprehensive research
of industry best practices and analysis of the original implementation flaws.

Key Improvements:
1. Service-namespaced Redis keys for better isolation and debugging
2. Configurable TTL per event type for optimal memory usage
3. Comprehensive observability with structured logging
4. Robust error handling with fail-open behavior
5. Enhanced debugging capabilities for production troubleshooting

Based on research from:
- Industry best practices from AWS, Google Cloud, Azure
- Analysis of HuleEdu event architecture requirements
"""

from __future__ import annotations

import functools
import hashlib
import json
import time
from collections.abc import Awaitable, Callable, Coroutine
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
DEFAULT_TTL_SECONDS = 86400  # 24 hours

# TTL for processing state (shorter to avoid blocking on crashes)
DEFAULT_PROCESSING_TTL_SECONDS = 300  # 5 minutes

# Processing state constants
IDEMPOTENCY_STATUS_PROCESSING = "processing"
IDEMPOTENCY_STATUS_COMPLETED = "completed"


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


def idempotent_consumer(
    redis_client: RedisClientProtocol,
    config: IdempotencyConfig,
) -> Callable[[Callable[..., Awaitable[Any]]], Callable[..., Coroutine[Any, Any, Any | None]]]:
    """
    Transaction-aware idempotency decorator for Kafka message handlers with Unit of Work.

    This decorator provides two-phase idempotency that integrates with transactional
    handlers using the Unit of Work pattern. It prevents duplicate processing while
    ensuring idempotency keys are only confirmed after successful transaction commits.

    Key Features:
    1. **Two-Phase Commit**: Sets "processing" status initially, confirms after success
    2. **Transaction Safety**: Only marks as completed after Unit of Work commits
    3. **Crash Recovery**: Processing keys expire quickly to allow retry after crashes
    4. **Service Isolation**: Each service maintains separate idempotency namespace
    5. **Event-Type Specific TTLs**: Optimized memory usage based on business requirements

    Args:
        redis_client: Active Redis client implementing RedisClientProtocol
        config: IdempotencyConfig with service name, TTL settings, and debug options

    Returns:
        Decorator that wraps handlers with transaction-aware idempotency

    Example:
        ```python
        @idempotent_consumer(redis_client=redis, config=config)
        async def handle_message(msg: ConsumerRecord, *, confirm_idempotency) -> Any:
            # Start transaction
            async with session.begin():
                # Do work...
                await repository.save(entity)

            # Confirm idempotency AFTER transaction commits
            await confirm_idempotency()
            return result
        ```
    """

    def decorator(
        func: Callable[..., Awaitable[Any]],
    ) -> Callable[..., Coroutine[Any, Any, Any | None]]:
        @functools.wraps(func)
        async def wrapper(msg: ConsumerRecord, *args: Any, **kwargs: Any) -> Any | None:
            try:
                # Extract ALL metadata from headers first
                event_id = None
                event_type = None
                correlation_id = None
                source_service = None
                headers_used = False

                if hasattr(msg, "headers") and msg.headers:
                    # Robust decoding for both str and bytes keys
                    headers_dict = {}
                    for k, v in msg.headers:
                        key = k.decode("utf-8") if isinstance(k, bytes) else k
                        value = v.decode("utf-8") if v else None
                        headers_dict[key] = value

                    event_id = headers_dict.get("event_id")
                    event_type = headers_dict.get("event_type")
                    correlation_id = headers_dict.get("trace_id")  # trace_id is correlation_id
                    source_service = headers_dict.get("source_service")

                    headers_used = bool(event_id and event_type)  # Track full header usage

                # Only parse JSON if headers incomplete
                event_dict = None
                if not (event_id and event_type):
                    event_dict = json.loads(msg.value)
                    # If critical headers missing, prioritize body values entirely
                    if not event_id:  # Critical header missing, use body values
                        event_type = event_dict.get("event_type", "unknown")
                        event_id = event_dict.get("event_id")
                        correlation_id = event_dict.get("correlation_id")
                        source_service = event_dict.get("source_service", "unknown")
                        headers_used = False  # Override since we're using body
                    else:
                        # Only event_type missing from headers, use body for that
                        event_type = event_dict.get("event_type", "unknown")
                        correlation_id = correlation_id or event_dict.get("correlation_id")
                        source_service = source_service or event_dict.get(
                            "source_service", "unknown"
                        )

                # Optimized deterministic hash (maintain backward compatibility)
                if event_id and headers_used:
                    # Fast path: header-based hash using same algorithm
                    # but avoid JSON parsing by using header values directly
                    hash_input = {"event_id": event_id}
                    # For headers, we don't have easy access to data, so use event_id only
                    hash_data = json.dumps(hash_input, sort_keys=True, separators=(",", ":"))
                    deterministic_hash = hashlib.sha256(hash_data.encode("utf-8")).hexdigest()
                else:
                    # Fallback: use existing proven logic for backward compatibility
                    deterministic_hash = generate_deterministic_event_id(msg.value)

                # Create service-namespaced Redis key
                redis_key = config.generate_redis_key(event_type, event_id, deterministic_hash)

                # Enhanced logging
                log_context = {
                    "service": config.service_name,
                    "event_type": event_type,
                    "event_id": event_id,
                    "correlation_id": correlation_id,
                    "source_service": source_service,
                    "deterministic_hash": deterministic_hash[:16] + "...",
                    "redis_key": redis_key,
                    "kafka_topic": msg.topic,
                    "kafka_partition": msg.partition,
                    "kafka_offset": msg.offset,
                    "headers_used": headers_used,  # Track header utilization
                    "json_parsed": event_dict is not None,  # Track if JSON parsing occurred
                }

                if config.enable_debug_logging:
                    logger.debug("Starting transaction-aware idempotency check", extra=log_context)

                # Check if already exists and get current status
                existing_value = await redis_client.get(redis_key)

                if existing_value:
                    try:
                        existing_data = json.loads(existing_value)
                        status = existing_data.get("status", IDEMPOTENCY_STATUS_COMPLETED)

                        if status == IDEMPOTENCY_STATUS_COMPLETED:
                            # Already successfully processed
                            logger.warning(
                                "DUPLICATE_EVENT_DETECTED: Event already completed",
                                extra={
                                    **log_context,
                                    "action": "skipped_duplicate",
                                    "status": status,
                                },
                            )
                            return None

                        elif status == IDEMPOTENCY_STATUS_PROCESSING:
                            # Check if processing is stale (crashed worker)
                            started_at = existing_data.get("started_at", 0)
                            if time.time() - started_at > DEFAULT_PROCESSING_TTL_SECONDS:
                                logger.warning(
                                    "STALE_PROCESSING_DETECTED: Retrying stale processing event",
                                    extra={
                                        **log_context,
                                        "action": "retry_stale",
                                        "stale_duration_seconds": time.time() - started_at,
                                    },
                                )
                                # Delete stale key and continue
                                await redis_client.delete_key(redis_key)
                            else:
                                # Still being processed by another worker
                                logger.warning(
                                    "DUPLICATE_EVENT_DETECTED: Event still processing",
                                    extra={
                                        **log_context,
                                        "action": "skipped_processing",
                                        "status": status,
                                    },
                                )
                                return None
                    except json.JSONDecodeError:
                        # Backward compatibility - treat as completed
                        logger.warning(
                            "DUPLICATE_EVENT_DETECTED: Legacy format, treating as completed",
                            extra={**log_context, "action": "skipped_legacy"},
                        )
                        return None

                # Set processing state with short TTL
                processing_data = json.dumps(
                    {
                        "status": IDEMPOTENCY_STATUS_PROCESSING,
                        "started_at": time.time(),
                        "processed_by": config.service_name,
                        "event_id": event_id,
                        "correlation_id": correlation_id,
                        "source_service": source_service,
                    }
                )

                # Use shorter TTL for processing state
                is_first_time = await redis_client.set_if_not_exists(
                    redis_key,
                    processing_data,
                    ttl_seconds=DEFAULT_PROCESSING_TTL_SECONDS,
                )

                if not is_first_time:
                    # Lost race condition to another worker
                    logger.warning(
                        "RACE_CONDITION_LOST: Another worker claimed this event",
                        extra={**log_context, "action": "skipped_race_condition"},
                    )
                    return None

                # Define confirmation callback
                async def confirm_idempotency() -> None:
                    """Confirm successful processing after transaction commit."""
                    try:
                        # Get appropriate TTL for this event type
                        ttl_seconds = config.get_ttl_for_event_type(event_type)

                        # Update to completed status with full TTL
                        completed_data = json.dumps(
                            {
                                "status": IDEMPOTENCY_STATUS_COMPLETED,
                                "started_at": time.time(),
                                "completed_at": time.time(),
                                "processed_by": config.service_name,
                                "event_id": event_id,
                                "correlation_id": correlation_id,
                                "source_service": source_service,
                            }
                        )

                        # Overwrite with completed status and proper TTL
                        await redis_client.setex(redis_key, ttl_seconds, completed_data)

                        logger.debug(
                            "IDEMPOTENCY_CONFIRMED: Processing confirmed after commit",
                            extra={
                                **log_context,
                                "action": "confirmed_completion",
                                "ttl_seconds": ttl_seconds,
                            },
                        )
                    except Exception as confirm_error:
                        # Log but don't fail - processing succeeded
                        logger.error(
                            "CONFIRMATION_FAILED: Could not confirm idempotency",
                            extra={
                                **log_context,
                                "action": "confirmation_error",
                                "error": str(confirm_error),
                            },
                            exc_info=True,
                        )

                # Execute business logic with confirmation callback
                try:
                    processing_start = time.time()

                    # Pass confirmation callback as a keyword argument
                    result = await func(
                        msg, *args, confirm_idempotency=confirm_idempotency, **kwargs
                    )

                    processing_duration = time.time() - processing_start

                    # Log success (confirmation happens in handler after commit)
                    logger.debug(
                        "PROCESSING_COMPLETE: Awaiting transaction commit confirmation",
                        extra={
                            **log_context,
                            "action": "processing_complete",
                            "processing_duration_ms": round(processing_duration * 1000, 2),
                        },
                    )

                    return result

                except Exception as processing_error:
                    # Processing failed - release idempotency lock for retry
                    logger.error(
                        "Processing failed: Releasing idempotency lock for retry",
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
                        await redis_client.delete_key(redis_key)
                        logger.debug(
                            "CLEANUP_SUCCESS: Idempotency key released for retry",
                            extra={**log_context, "action": "cleanup_completed"},
                        )
                    except Exception as cleanup_error:
                        logger.error(
                            "CLEANUP_FAILED: Could not release idempotency key",
                            extra={
                                **log_context,
                                "action": "cleanup_failed",
                                "cleanup_error": str(cleanup_error),
                            },
                            exc_info=True,
                        )

                    # Re-raise original processing exception
                    raise processing_error

            except json.JSONDecodeError as json_error:
                # Invalid JSON - fail open and process anyway
                logger.error(
                    "INVALID_JSON: Processing without idempotency",
                    extra={
                        "service": config.service_name,
                        "action": "processing_without_idempotency",
                        "error": str(json_error),
                        "kafka_topic": msg.topic,
                        "kafka_partition": msg.partition,
                        "kafka_offset": msg.offset,
                    },
                    exc_info=True,
                )

                # Create no-op confirm function for fail-open scenario
                async def noop_confirm():
                    pass

                return await func(msg, *args, confirm_idempotency=noop_confirm, **kwargs)

            except Exception as redis_error:
                # Redis operation failed - fail open and process anyway
                logger.error(
                    "REDIS_ERROR: Processing without idempotency protection",
                    extra={
                        "service": config.service_name,
                        "action": "processing_without_idempotency",
                        "error": str(redis_error),
                        "error_type": type(redis_error).__name__,
                        "kafka_topic": msg.topic,
                        "kafka_partition": msg.partition,
                        "kafka_offset": msg.offset,
                    },
                    exc_info=True,
                )

                # Create no-op confirm function for fail-open scenario
                async def noop_confirm():
                    pass

                return await func(msg, *args, confirm_idempotency=noop_confirm, **kwargs)

        return wrapper

    return decorator
