# CJ Assessment Service - Phase 4: ErrorDetail Migration Instructions

## Overview

This document provides detailed migration instructions for replacing all 12 direct ErrorDetail instantiations with appropriate factory functions in the CJ Assessment Service.

## Complete List of ErrorDetail Instantiations

| File | Line | Context |
|------|------|---------|
| api/health_routes.py | 30 | create_error_response function |
| event_processor.py | 402 | _create_parsing_error_detail function |
| event_processor.py | 418 | _categorize_processing_error (CJAssessmentError) |
| event_processor.py | 438 | _categorize_processing_error (general) |
| event_processor.py | 454 | _create_publishing_error_detail function |
| implementations/db_access_impl.py | 323 | _reconstruct_error_detail function |
| implementations/llm_interaction_impl.py | 184 | Exception handling in task processing |
| implementations/llm_interaction_impl.py | 214 | Exception handling from gather |
| implementations/llm_interaction_impl.py | 251 | Critical processing error |
| tests/test_llm_interaction_overrides.py | 178 | Test setup |
| tests/unit/test_llm_provider_service_client.py | 61 | HTTPStatusError handling |
| tests/unit/test_llm_provider_service_client.py | 77 | General exception handling |

## Key Model Differences

### CJ Assessment Service ErrorDetail (local)
```python
class ErrorDetail(BaseModel):
    error_code: ErrorCode
    message: str
    correlation_id: UUID
    timestamp: datetime
    service: str = "cj_assessment_service"
    details: dict = Field(default_factory=dict)
```

### Common Core ErrorDetail (canonical)
```python
class ErrorDetail(BaseModel):
    error_code: ErrorCode
    message: str
    correlation_id: UUID
    timestamp: datetime
    service: str
    operation: str  # REQUIRED - Missing in CJ model
    details: dict[str, Any] = Field(default_factory=dict)
    stack_trace: Optional[str] = None  # Auto-captured by factory
    trace_id: Optional[str] = None     # Auto-captured by factory
    span_id: Optional[str] = None      # Auto-captured by factory
```

## Migration Instructions by File

### 1. api/health_routes.py

**Current Code (Line 30-36):**
```python
def create_error_response(
    error_code: ErrorCode,
    message: str,
    correlation_id: UUID,
    status_code: int = 500,
    details: dict | None = None,
) -> ErrorResponse:
    error_detail = ErrorDetail(
        error_code=error_code,
        message=message,
        correlation_id=correlation_id,
        timestamp=datetime.now(UTC),
        details=details or {},
    )
    return ErrorResponse(error=error_detail, status_code=status_code)
```

**Migration:**
This function needs to be refactored since it's a generic error creator. Replace with:
```python
def create_error_response(
    error_code: ErrorCode,
    message: str,
    correlation_id: UUID,
    status_code: int = 500,
    details: dict | None = None,
) -> ErrorResponse:
    # Map error codes to appropriate factory functions
    if error_code == ErrorCode.VALIDATION_ERROR:
        raise_validation_error(
            service="cj_assessment_service",
            operation="health_check",  # Or pass operation as parameter
            field="unknown",
            message=message,
            correlation_id=correlation_id,
            **(details or {})
        )
    elif error_code == ErrorCode.RESOURCE_NOT_FOUND:
        raise_resource_not_found(
            service="cj_assessment_service",
            operation="health_check",
            resource_type="unknown",
            resource_id="unknown",
            correlation_id=correlation_id,
            **(details or {})
        )
    # ... add other mappings as needed
    else:
        # Default to processing error
        raise_processing_error(
            service="cj_assessment_service",
            operation="health_check",
            message=message,
            correlation_id=correlation_id,
            **(details or {})
        )
```

### 2. implementations/llm_interaction_impl.py

**Instance 1 (Line 184-190):**
```python
except Exception as e:
    error_detail = ErrorDetail(
        error_code=ErrorCode.PROCESSING_ERROR,
        message=f"Failed to process comparison task: {str(e)}",
        correlation_id=self.correlation_id,
        timestamp=datetime.now(UTC),
        details={"exception_type": type(e).__name__},
    )
```

**Migration:**
```python
except Exception as e:
    raise_processing_error(
        service="cj_assessment_service",
        operation="process_comparison_task",
        message=f"Failed to process comparison task: {str(e)}",
        correlation_id=self.correlation_id,
        exception_type=type(e).__name__,
    )
```

**Instance 2 (Line 214-219):**
```python
error_detail = ErrorDetail(
    error_code=ErrorCode.PROCESSING_ERROR,
    message="One or more comparison tasks failed",
    correlation_id=self.correlation_id,
    timestamp=datetime.now(UTC),
    details={"failed_indices": failed_indices},
)
```

**Migration:**
```python
raise_processing_error(
    service="cj_assessment_service",
    operation="process_comparisons_batch",
    message="One or more comparison tasks failed",
    correlation_id=self.correlation_id,
    failed_indices=failed_indices,
)
```

**Instance 3 (Line 251-257):**
```python
error_detail = ErrorDetail(
    error_code=ErrorCode.PROCESSING_ERROR,
    message=f"Critical error processing comparisons: {str(e)}",
    correlation_id=self.correlation_id,
    timestamp=datetime.now(UTC),
    details={"exception_type": type(e).__name__},
)
```

**Migration:**
```python
raise_processing_error(
    service="cj_assessment_service",
    operation="process_comparisons_critical_error",
    message=f"Critical error processing comparisons: {str(e)}",
    correlation_id=self.correlation_id,
    exception_type=type(e).__name__,
)
```

### 3. event_processor.py

**Instance 1 (Line 402-411) - _create_parsing_error_detail:**
```python
def _create_parsing_error_detail(
    self, error: Exception, field: str, value: Any
) -> ErrorDetail:
    return ErrorDetail(
        error_code=ErrorCode.PARSING_ERROR,
        message=f"Failed to parse {field}: {str(error)}",
        correlation_id=self.correlation_id,
        timestamp=datetime.now(UTC),
        details={"field": field, "value": str(value), "error_type": type(error).__name__},
    )
```

**Migration:**
```python
def _create_parsing_error(
    self, error: Exception, field: str, value: Any
) -> None:
    raise_parsing_error(
        service="cj_assessment_service",
        operation="parse_event_field",
        parse_target=field,
        message=f"Failed to parse {field}: {str(error)}",
        correlation_id=self.correlation_id,
        field=field,
        value=str(value),
        error_type=type(error).__name__,
    )
```

**Instance 2 (Line 418-424) - _categorize_processing_error for CJAssessmentError:**
```python
if isinstance(error, CJAssessmentError):
    return ErrorDetail(
        error_code=error.error_code,
        message=error.message,
        correlation_id=error.correlation_id or self.correlation_id,
        timestamp=error.timestamp,
        details=error.details,
    )
```

**Migration:**
Since this is already a structured error, we need to re-raise with proper context:
```python
if isinstance(error, CJAssessmentError):
    # Map CJAssessmentError to appropriate factory based on error_code
    if error.error_code == ErrorCode.VALIDATION_ERROR:
        raise_validation_error(
            service="cj_assessment_service",
            operation="categorize_processing_error",
            field="unknown",
            message=error.message,
            correlation_id=error.correlation_id or self.correlation_id,
            **error.details
        )
    # ... other mappings
```

**Instance 3 (Line 438-447) - _categorize_processing_error for general exceptions:**
```python
return ErrorDetail(
    error_code=error_code,
    message=f"Processing failed: {error_msg}",
    correlation_id=self.correlation_id,
    timestamp=datetime.now(UTC),
    details={
        "exception_type": type(error).__name__,
        "exception_message": str(error),
        "is_retryable": error_code in retryable_errors,
    },
)
```

**Migration:**
```python
# Based on error_code, use appropriate factory
if error_code == ErrorCode.TIMEOUT:
    raise_timeout_error(
        service="cj_assessment_service",
        operation="process_event",
        timeout_seconds=0,  # Unknown
        message=f"Processing failed: {error_msg}",
        correlation_id=self.correlation_id,
        exception_type=type(error).__name__,
        exception_message=str(error),
        is_retryable=True,
    )
elif error_code == ErrorCode.CONNECTION_ERROR:
    raise_connection_error(
        service="cj_assessment_service",
        operation="process_event",
        target="unknown",  # Fixed: 'target' not 'target_service'
        message=f"Processing failed: {error_msg}",
        correlation_id=self.correlation_id,
        exception_type=type(error).__name__,
        exception_message=str(error),
        is_retryable=True,
    )
# ... other mappings
```

**Instance 4 (Line 454-463) - _create_publishing_error_detail:**
```python
def _create_publishing_error_detail(
    self, error: Exception, event_type: str, topic: str
) -> ErrorDetail:
    return ErrorDetail(
        error_code=ErrorCode.KAFKA_PUBLISH_ERROR,
        message=f"Failed to publish {event_type} event: {str(error)}",
        correlation_id=self.correlation_id,
        timestamp=datetime.now(UTC),
        details={"event_type": event_type, "topic": topic, "error_type": type(error).__name__},
    )
```

**Migration:**
```python
def _raise_publishing_error(
    self, error: Exception, event_type: str, topic: str
) -> None:
    raise_kafka_publish_error(
        service="cj_assessment_service",
        operation="publish_event",
        message=f"Failed to publish {event_type} event: {str(error)}",
        correlation_id=self.correlation_id,
        event_type=event_type,
        topic=topic,
        exception_type=type(error).__name__,
    )
```

### 4. implementations/db_access_impl.py

**Instance (Line 323-330) - _reconstruct_error_detail:**
```python
def _reconstruct_error_detail(self, record: ErrorRecord) -> ErrorDetail:
    return ErrorDetail(
        error_code=ErrorCode(record.error_code),
        message=record.error_message,
        correlation_id=record.correlation_id,
        timestamp=record.timestamp,
        service=record.service,
        details=record.details or {},
    )
```

**Migration:**
This is a special case - reconstructing from database. We need to create a custom reconstruction that uses the canonical ErrorDetail:
```python
def _reconstruct_error_detail(self, record: ErrorRecord) -> ErrorDetail:
    # Import the canonical ErrorDetail from common_core
    from common_core.models.error_models import ErrorDetail as CanonicalErrorDetail
    
    return CanonicalErrorDetail(
        error_code=ErrorCode(record.error_code),
        message=record.error_message,
        correlation_id=record.correlation_id,
        timestamp=record.timestamp,
        service=record.service,
        operation=record.details.get("operation", "unknown"),  # Extract from details if stored
        details=record.details or {},
        stack_trace=None,  # Not stored in DB
        trace_id=None,     # Not stored in DB
        span_id=None,      # Not stored in DB
    )
```

### 5. Test Files

**tests/test_llm_interaction_overrides.py (Line 178-185):**
```python
error_detail = ErrorDetail(
    error_code=ErrorCode.EXTERNAL_SERVICE_ERROR,
    message="LLM Provider unavailable",
    correlation_id=correlation_id,
    timestamp=datetime.now(UTC),
    service="cj_assessment_service",
    details={"provider": "test"},
)
```

**Migration:**
Tests should be updated to use pytest.raises pattern:
```python
# Instead of creating ErrorDetail, test that the exception is raised
with pytest.raises(HuleEduError) as exc_info:
    # Code that should raise the error
    pass

# Then assert on the error details
assert exc_info.value.error_detail.error_code == ErrorCode.EXTERNAL_SERVICE_ERROR
assert "LLM Provider unavailable" in exc_info.value.error_detail.message
```

## Import Updates Required

Add these imports to files using factory functions:
```python
from huleedu_service_libs.error_handling import (
    raise_validation_error,
    raise_resource_not_found,
    raise_external_service_error,
    raise_timeout_error,
    raise_connection_error,
    raise_parsing_error,
    raise_invalid_response,
    raise_configuration_error,
    raise_processing_error,
    raise_kafka_publish_error,
)
```

## Migration Summary

### Total ErrorDetail Instantiations: 12

**By File:**
- event_processor.py: 4 instances
- implementations/llm_interaction_impl.py: 3 instances  
- tests/: 3 instances
- api/health_routes.py: 1 instance
- implementations/db_access_impl.py: 1 instance

**By Error Type:**
- PROCESSING_ERROR: 4 instances
- PARSING_ERROR: 1 instance
- KAFKA_PUBLISH_ERROR: 1 instance
- EXTERNAL_SERVICE_ERROR: 2 instances
- Dynamic/Variable: 4 instances

### Migration Strategy

1. **Phase 4a: Core Implementation Files** (Non-breaking)
   - event_processor.py (4 instances)
   - implementations/llm_interaction_impl.py (3 instances)
   - api/health_routes.py (1 instance)

2. **Phase 4b: Special Cases**
   - implementations/db_access_impl.py - Requires custom reconstruction logic

3. **Phase 4c: Test Updates**
   - Update all test files to use pytest.raises pattern
   - Remove ErrorDetail creation in tests

### Execution Order

1. Start with implementations/llm_interaction_impl.py (simplest cases)
2. Move to event_processor.py (more complex with dynamic error codes)
3. Update api/health_routes.py (requires refactoring)
4. Handle db_access_impl.py special case
5. Update all tests last

### Validation Steps

After each file migration:
1. Run `pdm run ruff check <file>` for linting
2. Run `pdm run mypy services/cj_assessment_service` for type checking
3. Run relevant tests to ensure functionality

## Next Steps

1. Create a new branch for Phase 4 migration
2. Update each file following these migration patterns
3. Remove the local ErrorDetail model from models_api.py after all migrations
4. Update all imports to use common_core ErrorDetail
5. Run full test suite to validate changes
6. Update documentation to reflect new error handling pattern