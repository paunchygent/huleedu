# Structlog Logging Specialist - Real-World Examples

Practical examples of structured logging with Structlog in HuleEdu services.

## Table of Contents

1. [Service Configuration Examples](#service-configuration-examples)
2. [HTTP Request Logging](#http-request-logging)
3. [Kafka Event Processing](#kafka-event-processing)
4. [Context Variable Usage](#context-variable-usage)
5. [Error Handling with Logging](#error-handling-with-logging)
6. [Cross-Service Correlation](#cross-service-correlation)

---

## Service Configuration Examples

### Example 1: Complete Service Setup

**File**: `services/spellchecker_service/app.py`

```python
from quart import Quart
from huleedu_service_libs.logging_utils import (
    configure_service_logging,
    create_service_logger,
)
from huleedu_service_libs.middleware.frameworks.quart_correlation_middleware import (
    setup_correlation_middleware
)
from spellchecker_service.settings import settings

# Configure logging before app creation
configure_service_logging(
    service_name="spellchecker_service",
    environment=settings.ENVIRONMENT,  # "production" or "development"
    log_level=settings.LOG_LEVEL,      # "INFO", "DEBUG", etc.
)

# Create app-level logger
logger = create_service_logger("spellchecker_service.app")

app = Quart(__name__)

@app.before_serving
async def startup():
    # Setup correlation middleware
    setup_correlation_middleware(app)

    logger.info(
        "Spellchecker Service starting",
        environment=settings.ENVIRONMENT,
        log_level=settings.LOG_LEVEL,
        version=settings.SERVICE_VERSION,
    )

@app.after_serving
async def shutdown():
    logger.info("Spellchecker Service shutting down")
```

---

## HTTP Request Logging

### Example 2: API Endpoint with Correlation

**File**: `services/content_service/api/essays.py`

```python
from quart import Blueprint, request, jsonify, g
from huleedu_service_libs.logging_utils import create_service_logger

bp = Blueprint("essays", __name__)
logger = create_service_logger("content_service.api.essays")

@bp.route("/api/essays", methods=["POST"])
async def create_essay():
    """Create new essay with correlation logging."""

    # Correlation ID automatically available from middleware
    correlation_id = g.correlation_id

    logger.info(
        "Creating essay",
        correlation_id=correlation_id,
        endpoint="/api/essays",
        method="POST",
    )

    try:
        data = await request.get_json()

        logger.debug(
            "Request data received",
            correlation_id=correlation_id,
            data_keys=list(data.keys()),
        )

        # Create essay
        essay = await essay_service.create_essay(data)

        logger.info(
            "Essay created successfully",
            correlation_id=correlation_id,
            essay_id=str(essay.id),
            user_id=data.get("user_id"),
        )

        return jsonify(essay.dict()), 201

    except ValidationError as e:
        logger.warning(
            "Validation error",
            correlation_id=correlation_id,
            error=str(e),
            validation_errors=e.errors(),
        )
        return jsonify({"error": str(e)}), 400

    except Exception as e:
        logger.error(
            "Essay creation failed",
            correlation_id=correlation_id,
            error=str(e),
            exc_info=True,  # Full traceback
        )
        return jsonify({"error": "Internal server error"}), 500
```

---

### Example 3: Health Check Logging

```python
@bp.route("/healthz", methods=["GET"])
async def health_check():
    """Health check endpoint."""

    logger.debug("Health check requested")

    try:
        # Check dependencies
        db_healthy = await check_database()
        kafka_healthy = await check_kafka()

        if db_healthy and kafka_healthy:
            logger.info(
                "Health check passed",
                database=db_healthy,
                kafka=kafka_healthy,
            )
            return jsonify({"status": "healthy"}), 200
        else:
            logger.warning(
                "Health check failed",
                database=db_healthy,
                kafka=kafka_healthy,
            )
            return jsonify({"status": "unhealthy"}), 503

    except Exception as e:
        logger.error(
            "Health check error",
            error=str(e),
            exc_info=True,
        )
        return jsonify({"status": "error"}), 500
```

---

## Kafka Event Processing

### Example 4: Event Processor with Context

**File**: `services/spellchecker_service/event_processor.py`

```python
from structlog.contextvars import bind_contextvars, clear_contextvars
from huleedu_service_libs.logging_utils import create_service_logger
from common_core.events.envelope import EventEnvelope

logger = create_service_logger("spellchecker_service.event_processor")

async def process_spellcheck_event(
    envelope: EventEnvelope[SpellCheckRequestedEvent]
) -> None:
    """Process spell check event with full logging."""

    # Bind event context for all subsequent logs
    bind_contextvars(
        correlation_id=str(envelope.correlation_id),
        event_id=str(envelope.event_id),
        event_type=envelope.event_type,
        source_service=envelope.source_service,
    )

    try:
        logger.info(
            "Event received",
            essay_id=envelope.data.essay_id,
            language=envelope.data.language,
        )

        # Process spell check
        result = await spell_checker.check(
            text=envelope.data.content,
            language=envelope.data.language,
        )

        logger.info(
            "Spell check completed",
            essay_id=envelope.data.essay_id,
            corrections_count=len(result.corrections),
        )

        # Publish result event
        await publish_result(result)

        logger.info("Result event published")

    except Exception as e:
        logger.error(
            "Event processing failed",
            essay_id=envelope.data.essay_id,
            error=str(e),
            exc_info=True,
        )
        raise

    finally:
        # Critical: clear context to prevent leaks
        clear_contextvars()
```

---

## Context Variable Usage

### Example 5: Multi-Step Processing with Context

```python
from structlog.contextvars import bind_contextvars, clear_contextvars

async def process_batch(batch_id: str, correlation_id: UUID) -> None:
    """Process batch with persistent context."""

    # Bind context once
    bind_contextvars(
        correlation_id=str(correlation_id),
        batch_id=batch_id,
    )

    try:
        logger.info("Batch processing started")  # Includes correlation_id, batch_id

        # Step 1
        essays = await fetch_essays(batch_id)
        logger.info("Essays fetched", essay_count=len(essays))

        # Step 2
        for essay in essays:
            # Add essay-specific context temporarily
            bind_contextvars(essay_id=str(essay.id))

            logger.info("Processing essay")  # Includes correlation_id, batch_id, essay_id
            await process_essay(essay)
            logger.info("Essay processed")

            # Remove essay-specific context for next iteration
            clear_contextvars()
            bind_contextvars(
                correlation_id=str(correlation_id),
                batch_id=batch_id,
            )

        # Step 3
        logger.info("Batch processing completed")  # Includes correlation_id, batch_id

    finally:
        clear_contextvars()
```

---

## Error Handling with Logging

### Example 6: Structured Error Handling

```python
from huleedu_service_libs.error_handling import (
    HuleEduError,
    create_error_detail_with_context,
)

async def score_essay(essay_id: str) -> AssessmentResult:
    """Score essay with structured error logging."""

    logger.info("Starting essay scoring", essay_id=essay_id)

    try:
        # Fetch essay
        essay = await essay_repo.get(essay_id)

        logger.debug(
            "Essay fetched",
            essay_id=essay_id,
            word_count=len(essay.content.split()),
        )

        # Call LLM service
        result = await llm_service.score(essay)

        logger.info(
            "Essay scored",
            essay_id=essay_id,
            total_score=result.total_score,
        )

        return result

    except NotFoundException as e:
        logger.warning(
            "Essay not found",
            essay_id=essay_id,
            error=str(e),
        )

        error_detail = create_error_detail_with_context(
            error_code=ErrorCode.RESOURCE_NOT_FOUND,
            message=f"Essay not found: {essay_id}",
            service="cj_assessment_service",
            operation="score_essay",
            correlation_id=g.correlation_id,
            details={"essay_id": essay_id}
        )
        raise HuleEduError(error_detail=error_detail) from e

    except Exception as e:
        logger.error(
            "Essay scoring failed",
            essay_id=essay_id,
            error=str(e),
            exc_info=True,
        )

        error_detail = create_error_detail_with_context(
            error_code=ErrorCode.PROCESSING_ERROR,
            message=f"Essay scoring failed: {e}",
            service="cj_assessment_service",
            operation="score_essay",
            correlation_id=g.correlation_id,
            details={"essay_id": essay_id}
        )
        raise HuleEduError(error_detail=error_detail) from e
```

---

## Cross-Service Correlation

### Example 7: Publishing Event with Correlation

```python
from common_core.events.envelope import EventEnvelope
from quart import g

async def publish_spellcheck_request(essay_id: str) -> None:
    """Publish event with correlation context."""

    # Create event with correlation ID from request
    event = SpellCheckRequestedEvent(
        essay_id=essay_id,
        content=essay.content,
        language="en",
    )

    # Create envelope with correlation
    envelope = EventEnvelope(
        correlation_id=g.correlation_context.uuid,  # Propagate correlation
        event_type="SpellCheckRequestedEvent",
        source_service="essay_lifecycle_service",
        data=event,
    )

    logger.info(
        "Publishing spell check request",
        correlation_id=str(envelope.correlation_id),
        event_id=str(envelope.event_id),
        essay_id=essay_id,
    )

    await kafka_producer.send(envelope)

    logger.info(
        "Event published",
        correlation_id=str(envelope.correlation_id),
        event_id=str(envelope.event_id),
    )
```

**Result**: Correlation ID flows through:
1. HTTP Request → essay_lifecycle_service
2. Kafka Event → spellchecker_service
3. All logs in both services share correlation ID
4. Loki query `{container=~"huleedu_.*"} |= "correlation_id_value"` traces full flow

---

## Related Resources

- **reference.md**: Detailed configuration and patterns
- **SKILL.md**: Quick reference and activation criteria
- `/libs/huleedu_service_libs/src/huleedu_service_libs/logging_utils.py`: Logging utilities
