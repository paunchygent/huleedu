# Critical Parameters

Non-obvious constants and parameters with usage context.

## Event Size Threshold

```python
STORAGE_REFERENCE_THRESHOLD = 50_000  # 50KB in bytes
```

**Decision**: Event payload >50KB → Use StorageReferenceMetadata

**Context**: Kafka recommended message size <1MB. 50KB threshold provides safety margin for envelope overhead and future growth.

**Usage**:
```python
payload_size = len(json.dumps(data_dict))
if payload_size > 50_000:
    storage_id = await content_service.store(data_dict)
    event.data_ref = StorageReferenceMetadata()
    event.data_ref.add_reference(ContentType.RESULTS_JSON, storage_id)
else:
    event.inline_data = data_dict
```

## Idempotency Key TTL

```python
IDEMPOTENCY_TTL_SECONDS = 86400  # 24 hours
```

**Decision**: Store event_id in Redis for 24 hours to detect duplicates.

**Context**: Kafka may redeliver messages. Services check Redis before processing. TTL prevents unbounded growth.

**Usage**:
```python
# Check before processing
if await redis.exists(f"event:{event_id}"):
    logger.info("Duplicate event, skipping", event_id=str(event_id))
    return

# Store after processing
await redis.setex(f"event:{event_id}", IDEMPOTENCY_TTL_SECONDS, "1")
```

## Student Association Timeout

```python
ASSOCIATION_VALIDATION_TIMEOUT_HOURS = 24
```

**Decision**: Auto-confirm high-confidence associations after 24 hours if teacher doesn't validate.

**Context**: REGULAR batches require student matching. High-confidence (>0.9) matches auto-confirm to unblock processing.

**Usage**:
```python
# Class Management Service
if association.confidence > 0.9 and hours_since_created > 24:
    await self.auto_confirm_association(association.id)
    # Publish VALIDATION_TIMEOUT_PROCESSED event
```

## LLM Request Queue Depth

```python
MAX_QUEUED_REQUESTS = 1000
```

**Decision**: LLM Provider Service rejects requests when queue >1000.

**Context**: Prevents memory exhaustion from request accumulation during provider outages.

**Usage**:
```python
# LLM Provider Service
if self.queue_size >= MAX_QUEUED_REQUESTS:
    raise HuleEduError(
        error_code=LLMErrorCode.QUEUE_FULL,
        message=f"Queue at capacity: {self.queue_size}"
    )
```

## Circuit Breaker Thresholds

```python
CIRCUIT_BREAKER_FAILURE_THRESHOLD = 5      # failures
CIRCUIT_BREAKER_TIMEOUT_SECONDS = 60       # open duration
CIRCUIT_BREAKER_SUCCESS_THRESHOLD = 2      # successes to close
```

**Decision**: Open circuit after 5 consecutive failures, close after 2 successes in half-open.

**Context**: Prevents cascading failures to degraded external services.

**Usage**:
```python
# Automatic in huleedu_service_libs circuit breaker
@circuit_breaker(
    failure_threshold=5,
    timeout_duration=60,
    expected_exception=ExternalServiceError
)
async def call_external_service(...):
    ...
```

## Batch Size Limits

```python
MIN_BATCH_SIZE = 1
MAX_BATCH_SIZE = 500
MIN_CJ_BATCH_SIZE = 5      # Minimum for meaningful comparisons
OPTIMAL_CJ_BATCH_SIZE = 20  # Sweet spot for quality/cost
```

**Decision**: CJ assessment requires ≥5 essays for statistical validity.

**Context**: Bradley-Terry model needs sufficient comparisons. Below 5 essays, scores unreliable.

**Usage**:
```python
# CJ Assessment Service
if len(essays) < MIN_CJ_BATCH_SIZE:
    raise HuleEduError(
        error_code=CJAssessmentErrorCode.CJ_INSUFFICIENT_COMPARISONS,
        message=f"CJ requires ≥{MIN_CJ_BATCH_SIZE} essays, got {len(essays)}"
    )
```

## Event Envelope schema_version

```python
EVENT_ENVELOPE_SCHEMA_VERSION = 1
```

**Decision**: All envelopes use schema_version=1 (current architecture).

**Context**: Reserved for future envelope structure evolution. V2 would indicate new envelope fields.

**Usage**:
```python
# Currently always 1
envelope = EventEnvelope[MyEventV1](
    schema_version=1,  # Default, no need to specify
    # ...
)

# Future: If envelope structure changes
# schema_version=2 would indicate new envelope structure
# Consumers check: if envelope.schema_version == 2: handle_v2()
```

## Content Type for Storage

```python
# See common_core.domain_enums.ContentType for full list

# Original content
ContentType.ORIGINAL_ESSAY           # Uploaded essay
ContentType.STUDENT_PROMPT_TEXT      # Assignment instructions

# Processing results
ContentType.CORRECTED_TEXT           # Spellcheck output
ContentType.NLP_METRICS_JSON         # NLP analysis
ContentType.CJ_RESULTS_JSON          # CJ detailed results

# AI outputs
ContentType.STUDENT_FACING_AI_FEEDBACK_TEXT  # Feedback for students
ContentType.AI_DETAILED_ANALYSIS_JSON        # Internal AI analysis
```

**Decision**: Explicit ContentType for each storage operation.

**Context**: Enables Content Service to apply correct storage policies (encryption, retention, access control).

**Usage**:
```python
# Store with correct type
storage_id = await content_service.store(
    content=results_json,
    content_type=ContentType.CJ_RESULTS_JSON,
    correlation_id=correlation_id
)

# Retrieve by type
cj_ref = storage_ref.references[ContentType.CJ_RESULTS_JSON]
results = await content_service.fetch(cj_ref["storage_id"])
```

## Kafka Topic Partitions

```python
DEFAULT_TOPIC_PARTITIONS = 3
HIGH_THROUGHPUT_PARTITIONS = 6  # For events with high volume
```

**Decision**: 3 partitions for most topics, 6 for high-throughput.

**Context**: Enables parallel consumption. High-throughput topics (ESSAY_CONTENT_PROVISIONED, SPELLCHECK_COMPLETED) use 6.

**Configuration**: Set during topic creation in Kafka infrastructure, not in application code.

## Correlation ID Format

```python
# Standard UUID v4
correlation_id: UUID = uuid4()

# Deterministic from business data (for idempotency)
from uuid import uuid5, NAMESPACE_DNS
correlation_id = uuid5(NAMESPACE_DNS, f"{batch_id}:{essay_id}:{phase}")
```

**Decision**: UUIDv4 for new requests, UUIDv5 for idempotent event generation.

**Context**: UUIDv5 deterministic generation ensures same business event produces same event_id across retries.

**Usage**:
```python
# New API request
correlation_id = uuid4()

# Idempotent event
event_id = uuid5(NAMESPACE_DNS, f"batch:{batch_id}:cj_complete")
```

## Related

- `.claude/rules/020-architectural-mandates.md` - Architectural constraints
- `.claude/rules/042-async-patterns-and-di.md` - DI and async patterns
- CJ Assessment Service - Parameter usage examples
