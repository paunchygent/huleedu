# Structlog Logging Specialist - Detailed Reference

Comprehensive guide for structured logging with Structlog in HuleEdu services.

## Table of Contents

1. [Structlog Configuration](#structlog-configuration)
2. [Correlation Context Propagation](#correlation-context-propagation)
3. [Logger Creation and Usage](#logger-creation-and-usage)
4. [Context Variables (Async-Safe)](#context-variables-async-safe)
5. [Event Logging Patterns](#event-logging-patterns)
6. [Error Handling Integration](#error-handling-integration)
7. [Context7 Integration](#context7-integration)
8. [Best Practices](#best-practices)

---

## Structlog Configuration

### Service Configuration Utility

**Library**: `/libs/huleedu_service_libs/src/huleedu_service_libs/logging_utils.py`

**Function**: `configure_service_logging(service_name, environment, log_level)`

**Production Configuration** (JSON output for Loki):
```python
def configure_service_logging(
    service_name: str,
    environment: str | None = None,
    log_level: str = "INFO",
) -> None:
    """Configure structlog for HuleEdu service."""

    if environment == "production":
        processors = [
            merge_contextvars,  # Merge context variables
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.add_log_level,
            structlog.processors.CallsiteParameterAdder([
                FILENAME, FUNC_NAME, LINENO
            ]),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),  # JSON output
        ]
    else:
        # Development: human-readable console
        processors = [
            merge_contextvars,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.add_log_level,
            structlog.processors.CallsiteParameterAdder([
                FILENAME, FUNC_NAME, LINENO
            ]),
            structlog.dev.set_exc_info,
            structlog.dev.ConsoleRenderer(colors=True),  # Colored console
        ]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(log_level)),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
```

**Usage in Service Startup**:
```python
from huleedu_service_libs.logging_utils import configure_service_logging

# In app.py
configure_service_logging(
    service_name="spellchecker_service",
    environment=settings.ENVIRONMENT,
    log_level=settings.LOG_LEVEL,
)
```

---

## Correlation Context Propagation

### HTTP Request → Logs

**Library**: `/libs/huleedu_service_libs/src/huleedu_service_libs/error_handling/correlation.py`

**CorrelationContext Dataclass**:
```python
@dataclass(frozen=True)
class CorrelationContext:
    """Correlation context extracted at HTTP boundary."""
    original: str        # Original value from client
    uuid: UUID          # Canonical UUID form
    source: Literal["header", "query", "generated"]

def extract_correlation_context_from_request(request: Any) -> CorrelationContext:
    """Extract correlation context with precedence:
    1. X-Correlation-ID header
    2. correlation_id query parameter
    3. Generate new UUID
    """
```

**Quart Middleware**:
```python
from huleedu_service_libs.middleware.frameworks.quart_correlation_middleware import (
    setup_correlation_middleware
)

# In app.py
@app.before_serving
async def startup():
    setup_correlation_middleware(app)

# Middleware automatically sets:
# g.correlation_context (CorrelationContext)
# g.correlation_id (str, backward-compatible)
```

**Logging with Correlation**:
```python
from quart import g
from huleedu_service_libs.logging_utils import create_service_logger

logger = create_service_logger("content_service.api")

@app.route("/api/essays", methods=["POST"])
async def create_essay():
    logger.info(
        "Creating essay",
        correlation_id=g.correlation_id,  # Automatically available
        user_id=user_id,
    )
```

---

### Kafka Events → Logs

**EventEnvelope Correlation**:
```python
from common_core.events.envelope import EventEnvelope

async def process_event(envelope: EventEnvelope) -> None:
    """Process Kafka event with correlation."""

    # Extract correlation from envelope
    correlation_id = envelope.correlation_id

    # Bind to context for all subsequent logs
    bind_contextvars(
        correlation_id=str(correlation_id),
        event_id=str(envelope.event_id),
        event_type=envelope.event_type,
        source_service=envelope.source_service,
    )

    # All logs now include correlation context
    logger.info("Processing event")  # Includes all bound context

    try:
        # Process...
        pass
    finally:
        # Clear context when done
        clear_contextvars()
```

---

## Logger Creation and Usage

### Creating Service Loggers

**Function**: `create_service_logger(name: str)`

```python
from huleedu_service_libs.logging_utils import create_service_logger

# Module-level logger
logger = create_service_logger("spellchecker_service.core_logic")

# Component-specific logger
kafka_logger = create_service_logger("spellchecker_service.kafka_consumer")
api_logger = create_service_logger("spellchecker_service.api.spellcheck")
```

**Naming Convention**: `{service_name}.{module}.{component}`

---

### Structured Logging

**Key-Value Pairs**:
```python
logger.info(
    "Event message (brief description)",
    correlation_id=str(correlation_id),
    essay_id=essay_id,
    user_id=user_id,
    duration_seconds=duration,
)
```

**Log Levels**:
```python
logger.debug("Detailed debugging info", debug_var=value)
logger.info("Normal operation event", key=value)
logger.warning("Warning condition", warning_detail=detail)
logger.error("Error occurred", error=str(e), exc_info=True)
```

**Exception Logging**:
```python
try:
    result = await risky_operation()
except Exception as e:
    logger.error(
        "Operation failed",
        error=str(e),
        essay_id=essay_id,
        exc_info=True,  # Include full traceback
    )
    raise
```

---

## Context Variables (Async-Safe)

### Using `bind_contextvars`

**Import**:
```python
from structlog.contextvars import bind_contextvars, clear_contextvars
```

**Binding Context**:
```python
# At request boundary
bind_contextvars(
    correlation_id=str(correlation_id),
    request_id=str(request_id),
    user_id=user_id,
)

# All logs automatically include bound context
logger.info("Processing request")  # correlation_id, request_id, user_id included
logger.info("Step 1 complete")     # Same context
logger.info("Step 2 complete")     # Same context
```

**Clearing Context**:
```python
try:
    bind_contextvars(correlation_id=str(correlation_id))
    await process_request()
finally:
    # Always clear in finally block
    clear_contextvars()
```

**Async Safety**: Context variables are async-safe and isolated per async task.

---

### Event Processing Pattern

```python
async def process_kafka_event(envelope: EventEnvelope) -> None:
    """Standard event processing with context."""

    # Bind event context
    bind_contextvars(
        correlation_id=str(envelope.correlation_id),
        event_id=str(envelope.event_id),
        event_type=envelope.event_type,
        source_service=envelope.source_service,
    )

    try:
        logger.info("Event processing started")

        # Process event (all logs include context)
        result = await event_processor.process(envelope.data)

        logger.info("Event processing completed", result_status=result.status)

    except Exception as e:
        logger.error("Event processing failed", error=str(e), exc_info=True)
        raise

    finally:
        # Critical: clear context to prevent leaks
        clear_contextvars()
```

---

## Event Logging Patterns

### Utility: `log_event_processing`

**Library**: `/libs/huleedu_service_libs/src/huleedu_service_libs/logging_utils.py`

```python
def log_event_processing(
    logger: Any,
    message: str,
    envelope: EventEnvelope,
    **kwargs: Any,
) -> None:
    """Log event processing with envelope context."""
    logger.info(
        message,
        correlation_id=str(envelope.correlation_id),
        event_id=str(envelope.event_id),
        event_type=envelope.event_type,
        source_service=envelope.source_service,
        timestamp=envelope.timestamp.isoformat(),
        **kwargs,
    )
```

**Usage**:
```python
from huleedu_service_libs.logging_utils import log_event_processing

async def handle_event(envelope: EventEnvelope[SpellCheckRequestedEvent]) -> None:
    log_event_processing(
        logger,
        "Spell check requested",
        envelope,
        essay_id=envelope.data.essay_id,
        language=envelope.data.language,
    )
```

---

## Error Handling Integration

### Automatic Correlation in Error Handlers

**Quart Error Handlers**:
```python
from huleedu_service_libs.error_handling.quart_handlers import register_error_handlers

# In app.py
register_error_handlers(app)

# Error handlers automatically log with correlation context
```

**HuleEduError with Logging**:
```python
from huleedu_service_libs.error_handling import (
    HuleEduError,
    create_error_detail_with_context,
)

try:
    result = await process_batch(batch_id)
except Exception as e:
    # Error detail automatically includes correlation_id from context
    error_detail = create_error_detail_with_context(
        error_code=ErrorCode.PROCESSING_ERROR,
        message=f"Batch processing failed: {e}",
        service="batch_orchestrator_service",
        operation="process_batch",
        correlation_id=g.correlation_id,  # From Quart context
        details={"batch_id": batch_id}
    )

    # Error automatically logged with full context
    raise HuleEduError(error_detail=error_detail) from e
```

---

## Context7 Integration

### When to Use Context7

Fetch latest Structlog documentation when:
- User asks about Structlog processors or configuration options
- Need examples of custom processors
- Troubleshooting context variable issues
- Understanding async safety guarantees
- New Structlog features or API changes

### Example Context7 Usage

```python
from context7 import get_library_docs

structlog_docs = get_library_docs(
    library_id="/hynek/structlog",
    topic="context variables async safety"
)
```

**Library ID**: `/hynek/structlog`

---

## Best Practices

### 1. Configure Once at Startup

```python
# Good: Configure at app startup
@app.before_serving
async def startup():
    configure_service_logging("my_service", environment=settings.ENVIRONMENT)

# Bad: Multiple configurations
configure_service_logging(...)  # In app.py
configure_service_logging(...)  # In worker.py (conflicts!)
```

---

### 2. Use Module-Level Loggers

```python
# Good: Module-level logger
logger = create_service_logger("my_service.module")

def my_function():
    logger.info("Function called")

# Avoid: Creating loggers in functions
def my_function():
    logger = create_service_logger("my_service.module")  # Inefficient
    logger.info("Function called")
```

---

### 3. Always Clear Context

```python
# Good: Clear in finally block
try:
    bind_contextvars(correlation_id=correlation_id)
    await process()
finally:
    clear_contextvars()

# Bad: Missing clear (context leak!)
bind_contextvars(correlation_id=correlation_id)
await process()
# Context persists to next request/event!
```

---

### 4. Use Structured Key-Value Pairs

```python
# Good: Structured logging
logger.info(
    "Essay processed",
    essay_id=essay_id,
    duration_seconds=duration,
    corrections_count=len(corrections),
)

# Bad: String formatting
logger.info(f"Essay {essay_id} processed in {duration}s with {len(corrections)} corrections")
```

**Rationale**: Structured fields can be queried in Loki with `| json | essay_id="123"`

---

### 5. Log at Appropriate Levels

**DEBUG**: Detailed debugging (disabled in production)
```python
logger.debug("Variable state", var_x=x, var_y=y)
```

**INFO**: Normal operational events
```python
logger.info("Request completed", status="success")
```

**WARNING**: Unusual but handled conditions
```python
logger.warning("Queue latency high", latency_seconds=queue_latency)
```

**ERROR**: Error conditions
```python
logger.error("Database error", error=str(e), exc_info=True)
```

---

### 6. Include `exc_info=True` for Exceptions

```python
try:
    result = await risky_operation()
except Exception as e:
    logger.error(
        "Operation failed",
        error=str(e),
        exc_info=True,  # Include full traceback
    )
    raise
```

---

### 7. Use Context Variables for Cross-Cutting Concerns

```python
# Bind once, use everywhere
bind_contextvars(
    correlation_id=str(correlation_id),
    user_id=user_id,
    request_id=str(request_id),
)

# All logs include context
logger.info("Step 1")  # correlation_id, user_id, request_id included
await do_work()
logger.info("Step 2")  # Same context
await do_more()
logger.info("Step 3")  # Same context
```

---

## Related Resources

- **examples.md**: Real-world logging examples from HuleEdu
- **SKILL.md**: Quick reference and activation criteria
- `/libs/huleedu_service_libs/src/huleedu_service_libs/logging_utils.py`: Logging utilities
- `/libs/huleedu_service_libs/src/huleedu_service_libs/error_handling/correlation.py`: Correlation utilities
