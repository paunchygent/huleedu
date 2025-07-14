# TASK-LLM-01: Event-Driven Callback Publishing in LLM Provider Service

**Status**: Ready for Implementation  
**Estimated Duration**: 3-4 days  
**Dependencies**: None  
**Risk Level**: Medium (Breaking change - removes polling endpoints)
**Architectural Impact**: High (Establishes event-driven pattern for platform)

## 📋 Executive Summary

Transform the `llm_provider_service` from a polling-based architecture to a pure event-driven system. This is a **breaking change** that removes all polling endpoints and requires ALL queued requests to specify a callback topic for result delivery via Kafka.

## 🎯 Business Objectives

1. **Reduce Infrastructure Costs**: Eliminate wasteful HTTP polling that consumes bandwidth and compute
2. **Improve Scalability**: Enable handling of 1000+ concurrent requests (vs ~20 with HTTP limits)
3. **Decrease Latency**: Sub-second callback delivery vs 2-60 second polling delays
4. **Establish Platform Pattern**: Create blueprint for all future async service interactions

## 🚨 Breaking Changes (No Backwards Compatibility)

### Removed Endpoints

- `GET /api/v1/comparison/status/{queue_id}` - **DELETED**
- `GET /api/v1/comparison/results/{queue_id}` - **DELETED**

### Removed Infrastructure

- Local result cache storage - **DELETED**
- Queue status tracking for polling - **DELETED**
- HTTP result retrieval logic - **DELETED**

### New Requirements

- ALL queued requests MUST provide `callback_topic` field
- Results delivered ONLY via Kafka events
- No synchronous result retrieval for queued requests

## ✅ Architecture Readiness Assessment

**Current Infrastructure Status**: EXCELLENT

- ✅ Kafka integration operational via `KafkaBus`
- ✅ Event publishing patterns established (`EventEnvelope`)
- ✅ DI configured with `LLMEventPublisherProtocol`
- ✅ Queue processor has event publisher access
- ✅ Trace context propagation implemented

## 📚 Required Architecture Rules

**MUST READ** before implementation:

- `.cursor/rules/020-architectural-mandates.mdc` - Async-first service patterns
- `.cursor/rules/030-event-driven-architecture-eda-standards.mdc` - Event publishing standards
- `.cursor/rules/042-async-patterns-and-di.mdc` - Dependency injection patterns
- `.cursor/rules/051-pydantic-v2-standards.mdc` - Event contract requirements
- `.cursor/rules/048-structured-error-handling-standards.mdc` - Error handling standards

## 🎨 Implementation Design

### Phase 1: Event Contract & Infrastructure (Day 1)

#### 1.1 Create Callback Event Model

**File**: `common_core/src/common_core/events/llm_provider_events.py` (new)

```python
from datetime import datetime
from typing import Optional, Any
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from common_core import EssayComparisonWinner, LLMProviderType
from common_core.models.error_models import ErrorDetail


class TokenUsage(BaseModel):
    """Token usage breakdown for LLM operations."""
    prompt_tokens: int = Field(default=0, ge=0, description="Number of tokens in the prompt")
    completion_tokens: int = Field(default=0, ge=0, description="Number of tokens in the completion")
    total_tokens: int = Field(default=0, ge=0, description="Total number of tokens used")


class LLMComparisonResultV1(BaseModel):
    """
    Event payload for LLM comparison results delivered via callback.
    Supports both success and error scenarios.
    """
    
    # Request identification
    request_id: str = Field(description="Original queue ID from LLM Provider Service")
    correlation_id: UUID = Field(description="Correlation ID for distributed tracing")
    
    # === SUCCESS FIELDS (mutually exclusive with error field) ===
    winner: Optional[EssayComparisonWinner] = Field(
        None, description="Selected essay: 'essay_a' or 'essay_b'"
    )
    justification: Optional[str] = Field(
        None, max_length=500, description="Justification for the decision"
    )
    confidence: Optional[float] = Field(
        None, ge=0.0, le=1.0, description="Confidence score"
    )
    
    # === ERROR FIELD (mutually exclusive with success fields) ===
    error_detail: Optional[ErrorDetail] = Field(
        None, description="Structured error information if comparison failed"
    )
    
    # === COMMON METADATA ===
    provider: LLMProviderType = Field(description="Provider used for comparison")
    model: str = Field(description="Model name/version used")
    
    # Performance metrics
    response_time_ms: int = Field(ge=0, description="Total processing time in milliseconds")
    token_usage: TokenUsage = Field(
        default_factory=TokenUsage,
        description="Token usage breakdown"
    )
    cost_estimate: float = Field(ge=0.0, description="Estimated cost in USD")
    
    # Timestamps
    requested_at: datetime = Field(description="When request was originally submitted")
    completed_at: datetime = Field(description="When processing completed")
    
    # Tracing
    trace_id: Optional[str] = Field(None, description="Distributed trace ID")
    request_metadata: dict[str, Any] = Field(
        default_factory=dict, description="Original request metadata"
    )
    
    @model_validator(mode='after')
    def validate_exclusive_fields(self) -> 'LLMComparisonResultV1':
        """Ensure either success fields or error_detail is set, but not both."""
        has_success_fields = self.winner is not None
        has_error_field = self.error_detail is not None
        
        if has_success_fields and has_error_field:
            raise ValueError("Cannot have both success fields and error_detail")  # Internal validation error
        
        if not has_success_fields and not has_error_field:
            raise ValueError("Must have either success fields or error_detail")  # Internal validation error
        
        # If success, all success fields must be set
        if has_success_fields:
            if self.justification is None or self.confidence is None:
                raise ValueError("All success fields (winner, justification, confidence) must be set together")  # Internal validation error
        
        return self
    
    @property
    def is_success(self) -> bool:
        """Check if this represents a successful comparison."""
        return self.winner is not None
    
    @property
    def is_error(self) -> bool:
        """Check if this represents an error result."""
        return self.error_detail is not None
```

#### 1.2 Add Event Type and Topic Mapping

**File**: `common_core/src/common_core/event_enums.py`

```python
# Add to ProcessingEvent enum:
LLM_COMPARISON_RESULT = "llm_provider.comparison_result"

# Add to _TOPIC_MAPPING:
ProcessingEvent.LLM_COMPARISON_RESULT: "huleedu.llm_provider.comparison_result.v1"

# Add to common_core/src/common_core/error_enums.py:
class LLMErrorCode(str, Enum):
    """Error codes specific to LLM Provider Service."""
    # Provider errors
    PROVIDER_UNAVAILABLE = "LLM_PROVIDER_UNAVAILABLE"
    PROVIDER_RATE_LIMIT = "LLM_PROVIDER_RATE_LIMIT"
    PROVIDER_TIMEOUT = "LLM_PROVIDER_TIMEOUT"
    PROVIDER_API_ERROR = "LLM_PROVIDER_API_ERROR"
    
    # Request errors
    INVALID_PROMPT = "LLM_INVALID_PROMPT"
    CONTENT_TOO_LONG = "LLM_CONTENT_TOO_LONG"
    INVALID_CONFIG = "LLM_INVALID_CONFIG"
    
    # Processing errors
    QUEUE_FULL = "LLM_QUEUE_FULL"
    INTERNAL_ERROR = "LLM_INTERNAL_ERROR"
    CALLBACK_TOPIC_MISSING = "LLM_CALLBACK_TOPIC_MISSING"
    CONTENT_TOO_LONG = "LLM_CONTENT_TOO_LONG"
    INVALID_CALLBACK_TOPIC = "LLM_INVALID_CALLBACK_TOPIC"
    
    # Processing errors
    PARSING_ERROR = "LLM_PARSING_ERROR"
    INVALID_RESPONSE = "LLM_INVALID_RESPONSE"
    COST_LIMIT_EXCEEDED = "LLM_COST_LIMIT_EXCEEDED"
    QUEUE_FULL = "LLM_QUEUE_FULL"
    
    # System errors
    INTERNAL_ERROR = "LLM_INTERNAL_ERROR"
    CONFIGURATION_ERROR = "LLM_CONFIGURATION_ERROR"
```

#### 1.3 Update Common Core Exports

**File**: `common_core/src/common_core/events/__init__.py`

- Add `LLMComparisonResultV1, TokenUsage` to imports and `__all__`

**File**: `common_core/src/common_core/__init__.py`

- Add `LLMComparisonResultV1, TokenUsage` to imports and `__all__`
- Add `LLMComparisonResultV1.model_rebuild(raise_errors=True)`
- Add `TokenUsage.model_rebuild(raise_errors=True)`

#### 1.4 Bootstrap Kafka Topic

**File**: `scripts/kafka_topic_bootstrap.py`

- Add `"huleedu.llm_provider.comparison_result.v1"` to topics list

### Phase 2: API Contract Updates (Day 1-2)

#### 2.1 Make Callback Topic Required

**File**: `services/llm_provider_service/api_models.py`

```python
class LLMComparisonRequest(BaseModel):
    """Request model for LLM comparison with mandatory callback."""
    
    user_prompt: str = Field(..., description="The comparison prompt")
    essay_a: str = Field(..., description="First essay to compare")
    essay_b: str = Field(..., description="Second essay to compare")
    
    # REQUIRED callback topic for async processing
    callback_topic: str = Field(
        ..., 
        description="Kafka topic for result callback (required for all requests)"
    )
    
    # Optional configuration overrides
    llm_config_overrides: Optional[LLMConfigOverrides] = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    correlation_id: UUID = Field(default_factory=uuid4)
```

#### 2.2 Update Queue Model

**File**: `services/llm_provider_service/queue_models.py`

```python
class QueuedRequest(BaseModel):
    """Model for queued LLM requests with mandatory callback."""
    
    # ... existing fields ...
    
    # REQUIRED callback information
    callback_topic: str = Field(..., description="Kafka topic for result delivery")
    
    # Remove unused callback_url field
    # callback_url: Optional[str] = None  # DELETED
```

### Phase 2.5: Add Missing Event Publisher Infrastructure (Day 2)

#### 2.5.1 Update Event Publisher Protocol

**File**: `services/llm_provider_service/protocols.py`

```python
class LLMEventPublisherProtocol(Protocol):
    """Protocol for publishing LLM events to Kafka."""
    
    # ... existing methods ...
    
    async def publish_to_topic(
        self,
        topic: str,
        envelope: EventEnvelope[Any],
        key: Optional[str] = None
    ) -> None:
        """Publish event to specific topic."""
        ...
```

#### 2.5.2 Implement publish_to_topic Method

**File**: `services/llm_provider_service/implementations/event_publisher_impl.py`

```python
async def publish_to_topic(
    self,
    topic: str,
    envelope: EventEnvelope[Any],
    key: Optional[str] = None
) -> None:
    """Publish event to specific topic."""
    try:
        # Serialize the envelope
        message_value = envelope.model_dump_json().encode('utf-8')
        
        # Send to Kafka
        await self.producer.send_and_wait(
            topic=topic,
            value=message_value,
            key=key.encode('utf-8') if key else None
        )
        
        logger.debug(
            f"Published event to topic {topic}",
            extra={
                "event_type": envelope.event_type,
                "correlation_id": str(envelope.correlation_id),
                "topic": topic
            }
        )
    except Exception as e:
        logger.error(
            f"Failed to publish to topic {topic}: {e}",
            extra={"correlation_id": str(envelope.correlation_id)},
            exc_info=True
        )
        raise
```

### Phase 3: Remove Polling Infrastructure (Day 2)

#### 3.1 Delete Status/Results Endpoints

**File**: `services/llm_provider_service/api/llm_routes.py`

Remove entirely:

- `@llm_bp.route("/status/<queue_id>", methods=["GET"])`
- `@llm_bp.route("/results/<queue_id>", methods=["GET"])`

#### 3.2 Remove Cache Storage Logic

**File**: `services/llm_provider_service/implementations/queue_processor_impl.py`

Delete:

- `_store_in_cache()` method
- All Redis cache interactions
- Result retrieval logic

### Phase 4: Implement Callback Publishing (Day 2-3)

#### 4.1 Update Queue Orchestrator

**File**: `services/llm_provider_service/implementations/llm_orchestrator_impl.py`

```python
async def _queue_request(
    self,
    user_prompt: str,
    essay_a: str,
    essay_b: str,
    correlation_id: UUID,
    overrides: dict[str, Any],
) -> LLMQueuedResult:
    """Queue a request for async processing with mandatory callback."""
    
    # Validate callback topic is provided
    callback_topic = overrides.get("callback_topic")
    if not callback_topic:
        # Use structured error handling
        from services.libs.huleedu_service_libs.error_handling import raise_validation_error
        raise_validation_error(
            service="llm_provider_service",
            operation="queue_request",
            field="callback_topic",
            message="callback_topic is required for queued requests",
            correlation_id=correlation_id
        )
    
    # Create queued request
    request_data = LLMComparisonRequest(
        user_prompt=user_prompt,
        essay_a=essay_a,
        essay_b=essay_b,
        correlation_id=correlation_id,
        callback_topic=callback_topic,  # Now required
        metadata=overrides,
    )
    
    # ... rest of existing queuing logic ...
```

#### 4.2 Implement Success Callback Publishing

**File**: `services/llm_provider_service/implementations/queue_processor_impl.py`

```python
async def _handle_request_success(
    self, 
    request: QueuedRequest, 
    response: LLMOrchestratorResponse
) -> None:
    """Handle successful request completion with event publishing."""
    
    # Log success
    logger.info(
        f"Request {request.queue_id} completed successfully",
        extra={"correlation_id": str(request.correlation_id)}
    )
    
    # Create success callback event
    callback_event = LLMComparisonResultV1(
        request_id=request.queue_id,
        correlation_id=request.correlation_id,
        winner=response.winner,
        justification=response.justification[:500],  # Enforce length limit
        confidence=response.confidence,
        error_detail=None,  # No error for success
        provider=response.provider,
        model=response.model,
        response_time_ms=response.response_time_ms,
        token_usage=TokenUsage(
            prompt_tokens=response.token_usage.get("prompt_tokens", 0),
            completion_tokens=response.token_usage.get("completion_tokens", 0),
            total_tokens=response.token_usage.get("total_tokens", 0)
        ),
        cost_estimate=response.cost_estimate,
        requested_at=request.queued_at,
        completed_at=datetime.now(UTC),
        trace_id=response.trace_id,
        request_metadata=response.metadata,
    )
    
    # Publish to callback topic
    await self._publish_callback_event(callback_event, request.callback_topic)
    
    # Update metrics
    self._requests_processed += 1
    metrics.counter("llm_requests_processed_total", status="success").inc()
```

#### 4.3 Implement Error Callback Publishing

**File**: `services/llm_provider_service/implementations/queue_processor_impl.py`

```python
async def _handle_request_failure(
    self, 
    request: QueuedRequest, 
    error: Exception,
    error_code: LLMErrorCode = LLMErrorCode.INTERNAL_ERROR
) -> None:
    """Handle failed request with error event publishing."""
    
    logger.error(
        f"Request {request.queue_id} failed",
        extra={
            "correlation_id": str(request.correlation_id),
            "error": str(error),
            "error_code": error_code.value
        },
        exc_info=True
    )
    
    # Use structured error handling factory
    from services.libs.huleedu_service_libs.error_handling import (
        raise_llm_provider_service_error,
        create_error_detail  # For cases where we need ErrorDetail without raising
    )
    
    # Create error detail for the callback event
    error_detail = create_error_detail(
        error_code=error_code,
        service=self.settings.SERVICE_NAME,
        operation="process_comparison",
        message=str(error)[:1000],
        correlation_id=request.correlation_id,
        details={
            "request_id": request.queue_id,
            "provider": request.request_data.llm_config_overrides.provider_override 
                       or self.settings.DEFAULT_LLM_PROVIDER,
            "queue_position": getattr(request, "queue_position", None)
        }
    )
    
    # Create error callback event
    callback_event = LLMComparisonResultV1(
        request_id=request.queue_id,
        correlation_id=request.correlation_id,
        winner=None,
        justification=None,
        confidence=None,
        error_detail=error_detail,
        provider=request.request_data.llm_config_overrides.provider_override 
                 or self.settings.DEFAULT_LLM_PROVIDER,
        model="unknown",
        response_time_ms=0,
        token_usage=TokenUsage(),  # Empty token usage for errors
        cost_estimate=0.0,
        requested_at=request.queued_at,
        completed_at=datetime.now(UTC),
        trace_id=None,
        request_metadata=request.request_data.metadata,
    )
    
    # Publish error to callback topic
    await self._publish_callback_event(callback_event, request.callback_topic)
    
    # Update metrics
    metrics.counter("llm_requests_processed_total", status="error").inc()
```

#### 4.4 Callback Publishing Helper

**File**: `services/llm_provider_service/implementations/queue_processor_impl.py`

```python
async def _publish_callback_event(
    self,
    event: LLMComparisonResultV1,
    topic: str
) -> None:
    """Publish callback event with proper error handling."""
    try:
        # Create event envelope
        envelope = EventEnvelope[LLMComparisonResultV1](
            event_type=ProcessingEvent.LLM_COMPARISON_RESULT.value,  # Use the enum value directly
            source_service=self.settings.SERVICE_NAME,
            correlation_id=event.correlation_id,
            data=event,
        )
        
        # Publish with correlation_id as key for ordering
        await self.event_publisher.publish_to_topic(
            topic=topic,
            envelope=envelope,
            key=str(event.correlation_id)
        )
        
        logger.info(
            "Published callback event",
            extra={
                "request_id": event.request_id,
                "topic": topic,
                "correlation_id": str(event.correlation_id),
                "is_error": event.is_error
            }
        )
        
        # Update metrics
        metrics.counter(
            "callback_events_published_total",
            topic=topic,
            status="error" if event.is_error else "success"
        ).inc()
        
    except Exception as e:
        # Log but don't fail - the request is already processed
        logger.error(
            "Failed to publish callback event",
            extra={
                "topic": topic,
                "correlation_id": str(event.correlation_id),
                "error": str(e)
            },
            exc_info=True
        )
        metrics.counter("callback_publish_failures_total", topic=topic).inc()
```

### Phase 5: Testing & Monitoring (Day 3-4)

#### 5.1 Unit Tests

**File**: `services/llm_provider_service/tests/unit/test_callback_publishing.py`

```python
import pytest
from unittest.mock import AsyncMock
from uuid import uuid4
from datetime import datetime, UTC

from common_core import ProcessingEvent, EssayComparisonWinner, LLMProviderType
from common_core.events import EventEnvelope, LLMComparisonResultV1, TokenUsage
from common_core.models.error_models import ErrorDetail


@pytest.mark.asyncio
async def test_success_callback_published():
    """Test that successful comparisons publish callback events."""
    # Mock dependencies
    mock_publisher = AsyncMock(spec=LLMEventPublisherProtocol)
    
    # Create processor with mocks
    processor = QueueProcessorImpl(event_publisher=mock_publisher, ...)
    
    # Create test request with callback topic
    request = QueuedRequest(
        queue_id="test-123",
        callback_topic="test.callback.topic",
        # ... other fields
    )
    
    # Create test response
    response = LLMOrchestratorResponse(
        winner="essay_a",
        justification="Essay A is better",
        confidence=0.85,
        # ... other fields
    )
    
    # Process success
    await processor._handle_request_success(request, response)
    
    # Verify callback was published
    mock_publisher.publish_to_topic.assert_called_once()
    call_args = mock_publisher.publish_to_topic.call_args
    
    assert call_args.kwargs["topic"] == "test.callback.topic"
    envelope = call_args.kwargs["envelope"]
    assert envelope.data.winner == "essay_a"
    assert envelope.data.is_success is True
    assert envelope.data.is_error is False
    assert envelope.data.error_detail is None
    assert isinstance(envelope.data.token_usage, TokenUsage)
```

#### 5.2 Integration Tests

**File**: `services/llm_provider_service/tests/integration/test_e2e_callback_flow.py`

```python
@pytest.mark.integration
@pytest.mark.asyncio
async def test_error_callback_published():
    """Test that failed comparisons publish error callback events."""
    # Mock dependencies
    mock_publisher = AsyncMock(spec=LLMEventPublisherProtocol)
    
    # Create processor with mocks
    processor = QueueProcessorImpl(event_publisher=mock_publisher, ...)
    
    # Create test request with callback topic
    request = QueuedRequest(
        queue_id="test-456",
        callback_topic="test.error.topic",
        correlation_id=uuid4(),
        # ... other fields
    )
    
    # Create test error
    test_error = Exception("Provider API rate limit exceeded")
    
    # Process failure
    await processor._handle_request_failure(
        request, 
        test_error,
        error_code=LLMErrorCode.PROVIDER_RATE_LIMIT
    )
    
    # Verify error callback was published
    mock_publisher.publish_to_topic.assert_called_once()
    call_args = mock_publisher.publish_to_topic.call_args
    
    assert call_args.kwargs["topic"] == "test.error.topic"
    envelope = call_args.kwargs["envelope"]
    assert envelope.data.is_error is True
    assert envelope.data.is_success is False
    assert envelope.data.error_detail is not None
    assert envelope.data.error_detail.error_code == LLMErrorCode.PROVIDER_RATE_LIMIT
    assert "rate limit" in envelope.data.error_detail.message.lower()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_e2e_callback_flow(kafka_container, app_container):
    """Test complete flow from request to callback publication."""
    # Create Kafka consumer for callback topic
    callback_topic = "test.callback.topic"
    consumer = create_test_consumer(kafka_container, callback_topic)
    
    # Submit comparison request
    response = await app_container.post(
        "/api/v1/comparison",
        json={
            "essay_a": "Test essay A",
            "essay_b": "Test essay B", 
            "user_prompt": "Compare these essays",
            "callback_topic": callback_topic,
        }
    )
    
    # Should get 202 Accepted
    assert response.status_code == 202
    queue_id = response.json()["queue_id"]
    
    # Wait for callback message
    message = await wait_for_kafka_message(consumer, timeout=30)
    
    # Verify callback content
    envelope = EventEnvelope[LLMComparisonResultV1].model_validate_json(message.value)
    assert envelope.data.request_id == queue_id
    assert envelope.data.is_success is True
    assert envelope.data.winner in ["essay_a", "essay_b"]
```

#### 5.3 Monitoring Metrics

Add to Prometheus configuration:

```yaml
# Callback publishing metrics
- name: callback_events_published_total
  type: counter
  help: "Total callback events published"
  labels: ["topic", "status"]

- name: callback_publish_failures_total  
  type: counter
  help: "Total callback publishing failures"
  labels: ["topic"]

- name: llm_requests_processed_total
  type: counter
  help: "Total LLM requests processed"
  labels: ["status"]
```

## ✅ Success Criteria

### Functional Requirements

- ✅ ALL queued requests require `callback_topic` field
- ✅ Successful comparisons publish `LLMComparisonResultV1` events
- ✅ Failed comparisons publish error events with proper error codes
- ✅ No polling endpoints remain in the service
- ✅ No cache storage code remains

### Performance Requirements

- ✅ Callback publishing latency < 100ms (p99)
- ✅ Support for 1000+ concurrent queued requests
- ✅ Zero message loss under normal operations

### Operational Requirements

- ✅ All callback events include correlation_id for tracing
- ✅ Metrics track success/error rates
- ✅ Failed publishes are logged but don't fail requests

## 🚨 Deployment Strategy

### Pre-Deployment Checklist

1. [ ] Kafka topic created and verified
2. [ ] All consuming services updated to handle new event
3. [ ] Monitoring dashboards configured
4. [ ] Load tests completed successfully

### Deployment Steps

1. **Coordinate with consumers** - This is a breaking change
2. **Stop all services** that interact with LLM Provider Service
3. **Deploy new version** of LLM Provider Service
4. **Deploy updated consumers** (e.g., CJ Assessment Service)
5. **Verify event flow** with test requests
6. **Monitor metrics** closely for first hour

### Deployment Drain Strategy

**File**: `services/llm_provider_service/implementations/graceful_shutdown.py`

```python
async def drain_in_flight_requests(
    processor: QueueProcessorProtocol,
    timeout_minutes: int = 5
) -> None:
    """Gracefully drain in-flight requests before shutdown."""
    logger.info("Starting graceful shutdown - draining in-flight requests")
    
    # Stop accepting new requests
    await processor.stop_accepting_requests()
    
    # Wait for completion with timeout
    start_time = datetime.now(UTC)
    timeout = timedelta(minutes=timeout_minutes)
    
    while processor.has_in_flight_requests():
        if datetime.now(UTC) - start_time > timeout:
            logger.warning(
                f"Timeout reached with {processor.in_flight_count()} requests still in flight"
            )
            break
            
        await asyncio.sleep(1)
        logger.info(f"Waiting for {processor.in_flight_count()} in-flight requests")
    
    logger.info("Graceful shutdown completed")
```

### Rollback Plan

1. Keep previous container images tagged and ready
2. If issues detected within 1 hour, stop all services
3. Redeploy previous versions of all affected services
4. Investigate issues before reattempting

## ⚠️ Anti-Patterns to Avoid

1. **DO NOT** add any backwards compatibility code
2. **DO NOT** store results in cache "just in case"
3. **DO NOT** make callback_topic optional
4. **DO NOT** block request processing on publish failures
5. **DO NOT** add complex retry logic for publishing

## 📊 Expected Impact

### Performance Improvements

- **Latency**: 60x improvement (sub-second vs 2-60s polling)
- **Throughput**: 50x improvement (1000+ concurrent vs 20)
- **Resource Usage**: 90% reduction in HTTP connections

### Operational Improvements

- **Observability**: Complete event flow tracking
- **Reliability**: No more lost results due to client timeouts
- **Scalability**: Horizontal scaling without connection limits

## 🔗 Related Tasks

- **TASK-LLM-02**: Refactor CJ Assessment Service to consume callbacks
- **Future**: Apply pattern to all async service interactions
