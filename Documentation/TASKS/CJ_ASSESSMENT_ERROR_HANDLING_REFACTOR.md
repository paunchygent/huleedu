# CJ Assessment Service Error Handling Refactor

## Task Overview

Refactor the CJ Assessment Service error handling to align with HuleEdu's architectural patterns and observability requirements. The current implementation uses plain string errors without proper categorization, loses correlation IDs, and lacks structured error responses needed for effective monitoring and debugging.

## Current State Analysis

### Problems Identified

1. **No Error Enum Usage**
   - Service returns plain string errors: `return None, "error message"`
   - No use of `common_core.error_enums.ErrorCode`
   - Cannot categorize or filter errors by type

2. **Lost Correlation IDs**
   - Correlation IDs generated for requests but discarded in error responses
   - Makes distributed tracing impossible
   - Cannot track errors across service boundaries

3. **Poor Observability**
   - No structured error logging
   - Cannot create specific Grafana dashboards for error types
   - No way to set up targeted alerts (e.g., rate limit vs timeout)
   - Metrics cannot distinguish between error categories

4. **Inconsistent Error Handling**
   - Mix of exception raising and tuple returns
   - Retry logic issues due to improper use of retry manager
   - No clear distinction between retryable and non-retryable errors

5. **Missing Error Context**
   - No HTTP status codes in error responses
   - No service identification in errors
   - No timestamp information
   - No retry hints for clients

## Desired State

### 1. Service-Specific Exception Hierarchy

```python
# services/cj_assessment_service/exceptions.py
from uuid import UUID
from common_core.error_enums import ErrorCode

class CJAssessmentError(Exception):
    """Base exception for CJ Assessment Service."""
    def __init__(
        self, 
        error_code: ErrorCode,
        message: str,
        correlation_id: UUID | None = None,
        details: dict | None = None
    ):
        self.error_code = error_code
        self.message = message
        self.correlation_id = correlation_id
        self.details = details or {}
        super().__init__(message)

class LLMProviderError(CJAssessmentError):
    """LLM Provider Service communication errors."""
    def __init__(
        self,
        message: str,
        correlation_id: UUID | None = None,
        status_code: int | None = None,
        is_retryable: bool = False,
        retry_after: int | None = None,
        provider: str | None = None
    ):
        details = {
            "status_code": status_code,
            "is_retryable": is_retryable,
            "retry_after": retry_after,
            "provider": provider
        }
        super().__init__(
            error_code=ErrorCode.EXTERNAL_SERVICE_ERROR,
            message=message,
            correlation_id=correlation_id,
            details=details
        )

class ContentServiceError(CJAssessmentError):
    """Content Service communication errors."""
    pass

class AssessmentProcessingError(CJAssessmentError):
    """Internal assessment processing errors."""
    pass

class InvalidPromptError(CJAssessmentError):
    """Invalid prompt format errors."""
    def __init__(self, message: str, correlation_id: UUID | None = None):
        super().__init__(
            error_code=ErrorCode.VALIDATION_ERROR,
            message=message,
            correlation_id=correlation_id
        )
```

### 2. Structured Error Response Model

```python
# services/cj_assessment_service/api_models.py
from pydantic import BaseModel
from uuid import UUID
from datetime import datetime
from common_core.error_enums import ErrorCode

class ErrorDetail(BaseModel):
    """Detailed error information."""
    error_code: ErrorCode
    message: str
    correlation_id: UUID
    timestamp: datetime
    service: str = "cj_assessment_service"
    details: dict = {}
    
class ErrorResponse(BaseModel):
    """API error response."""
    error: ErrorDetail
    status_code: int
```

### 3. Enhanced LLM Provider Client Error Handling

```python
# In llm_provider_service_client.py
async def generate_comparison(self, ...) -> tuple[dict[str, Any] | None, ErrorDetail | None]:
    """Generate comparison with proper error handling."""
    correlation_id = uuid4()
    
    try:
        # ... existing logic ...
    except aiohttp.ClientResponseError as e:
        error_detail = ErrorDetail(
            error_code=self._map_status_to_error_code(e.status),
            message=f"LLM Provider Service error: {e.message}",
            correlation_id=correlation_id,
            timestamp=datetime.utcnow(),
            details={
                "status_code": e.status,
                "is_retryable": e.status in [429, 500, 502, 503, 504],
                "provider": provider_override or self.settings.DEFAULT_LLM_PROVIDER.value
            }
        )
        logger.error(
            "LLM Provider Service error",
            extra={
                "error_code": error_detail.error_code.value,
                "correlation_id": str(correlation_id),
                "status_code": e.status,
                "provider": error_detail.details.get("provider")
            }
        )
        return None, error_detail
```

### 4. Retry Manager Integration

```python
# Fix retry logic to use call_with_retry directly
result, error = await self.retry_manager.call_with_retry(
    make_request,
    provider_name="llm_provider_service"
)
```

### 5. Event Processing Error Handling

```python
# In event_processor.py
async def process_cj_assessment_request(self, event: EventEnvelope) -> None:
    """Process with comprehensive error handling."""
    try:
        # ... processing logic ...
    except CJAssessmentError as e:
        await self._publish_failure_event(
            event=event,
            error_code=e.error_code,
            error_message=e.message,
            error_details=e.details
        )
        logger.error(
            "CJ Assessment processing failed",
            extra={
                "error_code": e.error_code.value,
                "correlation_id": str(e.correlation_id),
                "essay_pair_id": event.data.essay_pair_id,
                **e.details
            }
        )
```

### 6. API Route Error Handling

```python
# In api routes
@router.post("/assessment")
async def create_assessment(...) -> Response:
    try:
        # ... route logic ...
    except CJAssessmentError as e:
        error_response = ErrorResponse(
            error=ErrorDetail(
                error_code=e.error_code,
                message=e.message,
                correlation_id=e.correlation_id,
                timestamp=datetime.utcnow(),
                details=e.details
            ),
            status_code=_map_error_to_status(e.error_code)
        )
        return jsonify(error_response.dict()), error_response.status_code
```

## Implementation Plan

### Phase 1: Foundation (Priority: Critical)

1. **Create Exception Hierarchy**
   - [ ] Create `exceptions.py` with base and specific exceptions
   - [ ] Map exceptions to appropriate ErrorCode values
   - [ ] Include all necessary context fields

2. **Define Error Models**
   - [ ] Add ErrorDetail and ErrorResponse to `api_models.py`
   - [ ] Ensure Pydantic serialization works correctly
   - [ ] Add validation for required fields

3. **Update Retry Logic**
   - [ ] Change `with_retry` to `call_with_retry` in LLM client
   - [ ] Ensure exceptions properly trigger retries
   - [ ] Add tests for retry behavior

### Phase 2: Service Integration (Priority: High)

4. **Refactor LLM Provider Client**
   - [ ] Replace string errors with ErrorDetail objects
   - [ ] Preserve correlation IDs throughout error flow
   - [ ] Add structured logging with error context
   - [ ] Map HTTP status codes to ErrorCode enums

5. **Update Event Processing**
   - [ ] Catch and categorize exceptions properly
   - [ ] Include error details in failure events
   - [ ] Add correlation ID to all log entries

6. **Enhance API Routes**
   - [ ] Implement consistent error response format
   - [ ] Map internal errors to appropriate HTTP status codes
   - [ ] Include correlation IDs in all responses

### Phase 3: Observability (Priority: High)

7. **Structured Logging**
   - [ ] Update all error logs to include error_code
   - [ ] Add correlation_id to every log entry
   - [ ] Include entity IDs (essay_pair_id, etc.) in logs
   - [ ] Use consistent field names for log parsing

8. **Metrics Integration**
   - [ ] Add error counters by error_code
   - [ ] Track retry attempts and outcomes
   - [ ] Monitor external service errors separately
   - [ ] Create service-specific error rate metrics

9. **Distributed Tracing**
   - [ ] Ensure correlation IDs flow through all operations
   - [ ] Add trace spans for external service calls
   - [ ] Include error details in trace metadata

### Phase 4: Testing (Priority: Critical)

10. **Unit Tests**
    - [ ] Test exception hierarchy and error mapping
    - [ ] Verify retry behavior for different error types
    - [ ] Test error serialization and response format
    - [ ] Validate correlation ID propagation

11. **Integration Tests**
    - [ ] Test error handling with mock LLM provider errors
    - [ ] Verify failure event publishing
    - [ ] Test API error responses
    - [ ] Validate observability data generation

## Observability Requirements

### Logging Structure

```json
{
  "timestamp": "2024-07-09T10:30:45Z",
  "level": "ERROR",
  "service": "cj_assessment_service",
  "correlation_id": "123e4567-e89b-12d3-a456-426614174000",
  "error_code": "EXTERNAL_SERVICE_ERROR",
  "message": "LLM Provider Service error",
  "essay_pair_id": "pair-123",
  "status_code": 503,
  "provider": "anthropic",
  "is_retryable": true,
  "retry_attempt": 2
}
```

### Metrics to Track

- `cj_assessment_errors_total{error_code, endpoint}`
- `cj_assessment_llm_errors_total{error_code, provider, status_code}`
- `cj_assessment_retry_attempts_total{error_code, outcome}`
- `cj_assessment_error_response_time_seconds{error_code}`

### Grafana Dashboard Panels

1. Error rate by type (stacked graph)
2. LLM provider error breakdown
3. Retry success/failure rates
4. Error response times by type
5. Correlation between error types and service load

## Success Criteria

1. **Zero String Errors**: All errors use ErrorCode enums
2. **100% Correlation ID Coverage**: Every error includes correlation ID
3. **Structured Error Responses**: All APIs return ErrorResponse model
4. **Proper Retry Behavior**: HTTP 5xx errors trigger retries
5. **Observable Errors**: Can filter/alert on specific error types
6. **Traceable Failures**: Can track errors across service boundaries

## Implementation Approach: Clean Refactor

**NO MIGRATION PERIOD** - This is a complete, atomic refactor of all error handling code.

### Affected Files to Update

1. **Core Error Infrastructure**
   - `/services/cj_assessment_service/exceptions.py` (NEW)
   - `/services/cj_assessment_service/api_models.py` (UPDATE)

2. **LLM Provider Client**
   - `/services/cj_assessment_service/implementations/llm_provider_service_client.py`
     - All error returns must use ErrorDetail
     - Change `with_retry` to `call_with_retry`
     - Update all error logging

3. **Content Service Client**
   - `/services/cj_assessment_service/implementations/content_service_client.py`
     - Replace string errors with exceptions
     - Add proper error context

4. **Event Processing**
   - `/services/cj_assessment_service/event_processor.py`
     - Catch typed exceptions
     - Include error details in failure events
   - `/services/cj_assessment_service/implementations/event_publisher_impl.py`
     - Handle publishing errors properly

5. **Core Business Logic**
   - `/services/cj_assessment_service/implementations/cj_assessment_service_impl.py`
     - Replace all error strings with exceptions
     - Add correlation IDs to all operations
   - `/services/cj_assessment_service/implementations/pair_generator_impl.py`
     - Proper error handling for pair generation
   - `/services/cj_assessment_service/implementations/score_calculator_impl.py`
     - Handle calculation errors with context

6. **API Routes**
   - `/services/cj_assessment_service/api/assessment_routes.py`
     - Return ErrorResponse for all errors
     - Map exceptions to HTTP status codes
   - `/services/cj_assessment_service/api/health_routes.py`
     - Include error details in health checks

7. **Worker Main**
   - `/services/cj_assessment_service/worker_main.py`
     - Catch and log all exceptions properly
     - Ensure correlation IDs in worker context

8. **All Test Files**
   - Update all tests to expect new error formats
   - Add new tests for error scenarios
   - Ensure 100% error path coverage

### Code Update Checklist

Every error handling location must be updated to:

- [ ] Use typed exceptions instead of string errors
- [ ] Include correlation ID in error context
- [ ] Log with structured fields (error_code, correlation_id, etc.)
- [ ] Return ErrorDetail objects instead of strings
- [ ] Map to appropriate ErrorCode enum values
- [ ] Include all relevant context (entity IDs, status codes, etc.)

## Dependencies

- common_core v0.2.0+ (for ErrorCode enums)
- huleedu_service_libs (for logging utilities)
- Existing monitoring stack (Prometheus, Grafana, Loki)

## Error Code Mapping Strategy

### HTTP Status to ErrorCode Mapping

```python
def _map_status_to_error_code(status: int) -> ErrorCode:
    """Map HTTP status codes to ErrorCode enums."""
    mapping = {
        400: ErrorCode.INVALID_REQUEST,
        401: ErrorCode.AUTHENTICATION_ERROR,
        403: ErrorCode.AUTHENTICATION_ERROR,
        404: ErrorCode.RESOURCE_NOT_FOUND,
        408: ErrorCode.TIMEOUT,
        429: ErrorCode.RATE_LIMIT,
        500: ErrorCode.EXTERNAL_SERVICE_ERROR,
        502: ErrorCode.SERVICE_UNAVAILABLE,
        503: ErrorCode.SERVICE_UNAVAILABLE,
        504: ErrorCode.TIMEOUT,
    }
    return mapping.get(status, ErrorCode.EXTERNAL_SERVICE_ERROR)

def _map_error_to_status(error_code: ErrorCode) -> int:
    """Map ErrorCode to HTTP status for API responses."""
    mapping = {
        ErrorCode.VALIDATION_ERROR: 400,
        ErrorCode.INVALID_REQUEST: 400,
        ErrorCode.AUTHENTICATION_ERROR: 401,
        ErrorCode.RESOURCE_NOT_FOUND: 404,
        ErrorCode.TIMEOUT: 408,
        ErrorCode.RATE_LIMIT: 429,
        ErrorCode.EXTERNAL_SERVICE_ERROR: 502,
        ErrorCode.SERVICE_UNAVAILABLE: 503,
        ErrorCode.PROCESSING_ERROR: 500,
    }
    return mapping.get(error_code, 500)
```

### Retryable Error Determination

```python
def _is_retryable_error(error_code: ErrorCode) -> bool:
    """Determine if an error should trigger retry."""
    retryable_codes = {
        ErrorCode.TIMEOUT,
        ErrorCode.SERVICE_UNAVAILABLE,
        ErrorCode.RATE_LIMIT,
        ErrorCode.CONNECTION_ERROR,
    }
    return error_code in retryable_codes
```

## Detailed File Updates

### 1. LLM Provider Client Complete Refactor

```python
# Key changes needed:
- Line 117: Replace None, "Invalid prompt format" with raise InvalidPromptError
- Line 166: Create LLMProviderError from response data
- Line 191: Return ErrorDetail instead of string
- Line 213: Create structured error for JSON parse failures
- Line 248: Return ErrorDetail for queue errors
- Line 271: Replace string return with ErrorDetail
- Line 293: Include correlation ID in timeout errors
- Line 320: Structure queue failure errors
- Line 465: Proper error context for all failure paths
```

### 2. Event Processor Error Handling

```python
# Must handle these error scenarios:
- Invalid event data → ErrorCode.VALIDATION_ERROR
- Content service failures → ErrorCode.CONTENT_SERVICE_ERROR
- LLM provider failures → ErrorCode.EXTERNAL_SERVICE_ERROR
- Assessment logic errors → ErrorCode.PROCESSING_ERROR
- Event publishing failures → ErrorCode.KAFKA_PUBLISH_ERROR
```

### 3. API Route Error Standardization

```python
# Every route must:
- Wrap logic in try-except
- Convert exceptions to ErrorResponse
- Return proper HTTP status codes
- Include correlation IDs in responses
- Log errors with full context
```

## Estimated Effort

- Core Infrastructure Setup: 4 hours
- File-by-file refactor: 2 days
- Test updates: 1 day
- Integration testing: 4 hours
- Total: 4 days

**Note**: This is a breaking change that requires updating all error handling at once.

## Testing Strategy

### Unit Test Requirements

1. **Exception Tests** (`test_exceptions.py`)
   - Test all exception classes initialize correctly
   - Verify error_code mapping
   - Test exception inheritance hierarchy
   - Validate serialization of error details

2. **Error Response Tests** (`test_error_responses.py`)
   - Test ErrorDetail model validation
   - Verify ErrorResponse serialization
   - Test all error code mappings
   - Validate timestamp formatting

3. **Client Error Tests** (update existing)
   - Test each error scenario returns proper exception
   - Verify correlation ID propagation
   - Test retry behavior for retryable errors
   - Ensure non-retryable errors fail immediately

### Integration Test Requirements

1. **LLM Provider Error Scenarios**
   - Mock 503 error → Verify retries and eventual success
   - Mock 400 error → Verify immediate failure
   - Mock timeout → Verify retry with backoff
   - Mock rate limit → Verify retry after delay

2. **Event Processing Errors**
   - Invalid event data → Failure event published
   - LLM provider down → Failure event with retry info
   - Content service error → Proper error categorization

3. **API Error Responses**
   - Each error type returns correct HTTP status
   - Error response format matches specification
   - Correlation IDs present in all errors

### End-to-End Test Scenarios

```python
# Must test these complete flows:
1. Happy path with no errors
2. Transient error with successful retry
3. Permanent error with proper failure handling
4. Timeout with retry exhaustion
5. Invalid input with validation error
```

## Acceptance Criteria Checklist

### Code Quality

- [ ] Zero string error returns (all use exceptions/ErrorDetail)
- [ ] All exceptions inherit from CJAssessmentError
- [ ] Every error includes correlation_id
- [ ] All errors map to ErrorCode enum values
- [ ] Consistent error logging format

### Observability

- [ ] Error logs include: error_code, correlation_id, entity_ids
- [ ] Metrics track errors by type
- [ ] Distributed tracing works with correlation IDs
- [ ] Grafana can filter errors by error_code

### Functionality

- [ ] Retryable errors (5xx) trigger retries
- [ ] Non-retryable errors (4xx) fail immediately  
- [ ] Error context preserved through retry attempts
- [ ] API returns proper HTTP status for each error type

### Testing

- [ ] 100% error path coverage
- [ ] All error scenarios have tests
- [ ] Integration tests cover external service errors
- [ ] Performance tests verify retry delays

## Notes

- This refactor aligns with patterns established in Class Management Service and LLM Provider Service
- Preserves existing retry configuration but fixes implementation issues
- Enables future enhancements like circuit breakers and intelligent retry policies
- Sets foundation for SLA monitoring and error budgets
- Clean refactor approach ensures consistency across entire service
