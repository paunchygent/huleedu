# Distributed Tracing Specialist - Real-World Examples

Practical examples of distributed tracing with OpenTelemetry and Jaeger in HuleEdu.

## Table of Contents

1. [Service Setup Examples](#service-setup-examples)
2. [HTTP Request Tracing](#http-request-tracing)
3. [Kafka Event Tracing](#kafka-event-tracing)
4. [Cross-Service Trace Propagation](#cross-service-trace-propagation)
5. [Database Operation Tracing](#database-operation-tracing)
6. [LLM Request Tracing](#llm-request-tracing)

---

## Service Setup Examples

### Example 1: Complete Spellchecker Service Setup

**File**: `services/spellchecker_service/app.py`

```python
from quart import Quart
from huleedu_service_libs.observability.tracing import init_tracing
from huleedu_service_libs.middleware.frameworks.quart_middleware import (
    setup_tracing_middleware
)

app = Quart(__name__)

# Initialize tracer at module level
tracer = init_tracing("spellchecker_service")

@app.before_serving
async def startup():
    # Setup tracing middleware
    setup_tracing_middleware(app, tracer)

    logger.info("Spellchecker Service started with tracing enabled")
```

---

## HTTP Request Tracing

### Example 2: API Endpoint with Manual Span

**File**: `services/content_service/api/essays.py`

```python
from quart import Blueprint, request, jsonify, g
from huleedu_service_libs.observability.tracing import trace_operation

bp = Blueprint("essays", __name__)

@bp.route("/api/essays", methods=["POST"])
async def create_essay():
    """Create essay with span creation."""

    # Middleware already created request span
    # Add custom span for business logic
    with trace_operation(
        tracer,
        "create_essay_business_logic",
        attributes={
            "correlation_id": g.correlation_id,
            "endpoint": "/api/essays",
        }
    ) as span:
        data = await request.get_json()

        # Create essay
        essay = await essay_service.create_essay(data)

        # Add result attributes
        span.set_attribute("essay_id", str(essay.id))
        span.set_attribute("user_id", data.get("user_id"))
        span.set_attribute("word_count", len(essay.content.split()))

        return jsonify(essay.dict()), 201
```

**Jaeger View**:
```
POST /api/essays                       [200ms] (middleware span)
  └─ create_essay_business_logic       [180ms] (custom span)
```

---

### Example 3: Nested Spans for Multi-Step Process

```python
@bp.route("/api/batches/<batch_id>/process", methods=["POST"])
async def process_batch(batch_id: str):
    """Process batch with nested spans."""

    with trace_operation(
        tracer,
        "process_batch",
        attributes={
            "batch_id": batch_id,
            "correlation_id": g.correlation_id,
        }
    ) as parent_span:

        # Step 1: Fetch essays
        with trace_operation(tracer, "fetch_essays") as fetch_span:
            essays = await batch_repo.get_essays(batch_id)
            fetch_span.set_attribute("essay_count", len(essays))

        parent_span.set_attribute("essay_count", len(essays))

        # Step 2: Process each essay
        for idx, essay in enumerate(essays):
            with trace_operation(
                tracer,
                "process_single_essay",
                attributes={
                    "essay_id": str(essay.id),
                    "index": idx,
                }
            ):
                await process_essay(essay)

        # Step 3: Mark batch complete
        with trace_operation(tracer, "mark_batch_complete"):
            await batch_repo.update_status(batch_id, "completed")

        return jsonify({"status": "completed"}), 200
```

**Jaeger View**:
```
POST /api/batches/<id>/process              [5000ms]
  └─ process_batch                          [4950ms]
       ├─ fetch_essays                      [100ms]
       ├─ process_single_essay (idx=0)      [800ms]
       ├─ process_single_essay (idx=1)      [750ms]
       ├─ process_single_essay (idx=2)      [820ms]
       ...
       └─ mark_batch_complete               [50ms]
```

---

## Kafka Event Tracing

### Example 4: Publishing Event with Trace Context

**File**: `services/essay_lifecycle_service/event_publisher.py`

```python
from huleedu_service_libs.observability.tracing import (
    trace_operation,
    inject_trace_context,
)

async def publish_spellcheck_request(essay_id: str) -> None:
    """Publish event with trace context propagation."""

    with trace_operation(
        tracer,
        "publish_spellcheck_request",
        attributes={
            "essay_id": essay_id,
            "correlation_id": g.correlation_id,
        }
    ) as span:

        # Create event
        event = SpellCheckRequestedEvent(
            essay_id=essay_id,
            content=essay.content,
            language="en",
        )

        # Create envelope
        envelope = EventEnvelope(
            correlation_id=g.correlation_context.uuid,
            event_type="SpellCheckRequestedEvent",
            source_service="essay_lifecycle_service",
            data=event,
            metadata={},
        )

        # Inject trace context into metadata
        inject_trace_context(envelope.metadata)

        span.set_attribute("event_id", str(envelope.event_id))

        # Publish to Kafka
        await kafka_producer.send(envelope)

        logger.info(
            "Event published with trace context",
            event_id=str(envelope.event_id),
            trace_id=get_current_trace_id(),
        )
```

---

### Example 5: Consuming Event with Trace Context

**File**: `services/spellchecker_service/event_processor.py`

```python
from huleedu_service_libs.observability.tracing import (
    trace_operation,
    extract_trace_context,
)

async def process_spellcheck_event(
    envelope: EventEnvelope[SpellCheckRequestedEvent]
) -> None:
    """Process event with trace context continuation."""

    # Extract trace context from event metadata
    ctx = extract_trace_context(envelope.metadata)

    # Start span with extracted context (continues the trace!)
    with trace_operation(
        tracer,
        "process_spellcheck_event",
        attributes={
            "event_id": str(envelope.event_id),
            "correlation_id": str(envelope.correlation_id),
            "event_type": envelope.event_type,
            "essay_id": envelope.data.essay_id,
        }
    ) as span:

        # Perform spell check
        with trace_operation(tracer, "spell_check_operation") as check_span:
            result = await spell_checker.check(
                text=envelope.data.content,
                language=envelope.data.language,
            )
            check_span.set_attribute("corrections_count", len(result.corrections))

        # Publish result
        with trace_operation(tracer, "publish_result") as publish_span:
            await publish_result(result)
            publish_span.set_attribute("result_event_id", str(result_event_id))

        span.set_attribute("total_duration_ms", total_duration)
```

**Jaeger View** (cross-service trace):
```
[essay_lifecycle_service] POST /api/essays                      [5000ms]
  └─ publish_spellcheck_request                                  [50ms]
      └─ [kafka] send event                                      [20ms]

[spellchecker_service] process_spellcheck_event                 [800ms]
  ├─ spell_check_operation                                       [600ms]
  └─ publish_result                                              [100ms]
```

**Note**: Both services show in single trace due to trace context propagation!

---

## Cross-Service Trace Propagation

### Example 6: HTTP → Kafka → HTTP Flow

**Service 1: Content Service** (HTTP request)
```python
@bp.route("/api/essays", methods=["POST"])
async def create_essay():
    with trace_operation(tracer, "create_essay") as span:
        # Create essay in database
        essay = await essay_repo.create(data)
        span.set_attribute("essay_id", str(essay.id))

        # Publish event (trace context auto-injected)
        await event_publisher.publish_essay_created(essay)

        return jsonify(essay.dict()), 201
```

**Service 2: Essay Lifecycle** (Kafka consumer → publisher)
```python
async def process_essay_created(envelope: EventEnvelope) -> None:
    # Extract trace context
    ctx = extract_trace_context(envelope.metadata)

    with trace_operation(tracer, "process_essay_created", context=ctx):
        # Process essay
        await processor.process(envelope.data)

        # Publish next event (trace context auto-injected)
        await event_publisher.publish_spellcheck_request(essay_id)
```

**Service 3: Spellchecker** (Kafka consumer)
```python
async def process_spellcheck_request(envelope: EventEnvelope) -> None:
    # Extract trace context
    ctx = extract_trace_context(envelope.metadata)

    with trace_operation(tracer, "spell_check", context=ctx) as span:
        result = await spell_checker.check(essay)
        span.set_attribute("corrections", len(result.corrections))
```

**Jaeger View** (single unified trace):
```
[content_service] POST /api/essays                              [6000ms]
  └─ create_essay                                               [5950ms]
      └─ [essay_lifecycle_service] process_essay_created       [5000ms]
          └─ [spellchecker_service] spell_check                [800ms]
```

---

## Database Operation Tracing

### Example 7: Database Query Tracing

```python
from huleedu_service_libs.observability.tracing import trace_operation

async def get_essay_by_id(essay_id: str) -> Essay:
    """Fetch essay with database span."""

    with trace_operation(
        tracer,
        "db_query_essay",
        attributes={
            "db.system": "postgresql",
            "db.operation": "SELECT",
            "db.table": "essays",
            "essay_id": essay_id,
        }
    ) as span:
        async with get_db_session() as session:
            result = await session.execute(
                select(EssayModel).where(EssayModel.id == essay_id)
            )
            essay = result.scalar_one()

            span.set_attribute("db.rows_returned", 1)

            return Essay.from_orm(essay)
```

**Jaeger View**:
```
GET /api/essays/<id>                [250ms]
  └─ get_essay_business_logic       [230ms]
      └─ db_query_essay              [200ms]
```

---

## LLM Request Tracing

### Example 8: LLM API Call Tracing

```python
async def call_openai_api(prompt: str, model: str = "gpt-4") -> LLMResponse:
    """Call OpenAI with comprehensive tracing."""

    with trace_operation(
        tracer,
        "openai_api_call",
        attributes={
            "llm.provider": "openai",
            "llm.model": model,
            "llm.prompt_length": len(prompt),
        }
    ) as span:

        try:
            response = await openai_client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
            )

            # Record token usage
            span.set_attribute("llm.prompt_tokens", response.usage.prompt_tokens)
            span.set_attribute("llm.completion_tokens", response.usage.completion_tokens)
            span.set_attribute("llm.total_tokens", response.usage.total_tokens)

            # Record response
            span.set_attribute("llm.response_length", len(response.choices[0].message.content))

            return LLMResponse.from_openai_response(response)

        except RateLimitError as e:
            span.set_attribute("llm.rate_limited", True)
            span.set_attribute("llm.retry_after", e.retry_after)
            span.record_exception(e)
            raise

        except Exception as e:
            span.record_exception(e)
            raise
```

**Jaeger View with Attributes**:
```
Span: openai_api_call
Duration: 2.3s
Attributes:
  llm.provider: openai
  llm.model: gpt-4
  llm.prompt_length: 1523
  llm.prompt_tokens: 380
  llm.completion_tokens: 125
  llm.total_tokens: 505
  llm.response_length: 542
```

---

## Related Resources

- **reference.md**: Detailed tracing patterns and configuration
- **SKILL.md**: Quick reference and activation criteria
- `/libs/huleedu_service_libs/src/huleedu_service_libs/observability/tracing.py`: Tracing utilities
- **Jaeger UI**: <http://localhost:16686>
