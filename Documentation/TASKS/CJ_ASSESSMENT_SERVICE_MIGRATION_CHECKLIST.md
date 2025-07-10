# CJ Assessment Service Error Handling Migration Checklist

**Created**: 2025-07-10  
**Service**: CJ Assessment Service  
**Migration Type**: Tuple Returns → Exception-Based Error Handling

## Overview

CJ Assessment Service is the primary user of ErrorDetail with tuple return patterns. This checklist provides a step-by-step guide for migrating to the new exception-based error handling system.

## Pre-Migration Status

- ✅ Uses ErrorDetail model
- ❌ Returns tuples: `tuple[Result | None, ErrorDetail | None]`
- ❌ Direct ErrorDetail instantiation
- ✅ Has structured database fields for errors

## Migration Checklist

### Phase 1: Update Protocols (3 methods)

**File**: `services/cj_assessment_service/protocols.py`

- [ ] Line 23: Update `ContentServiceProtocol.fetch_content()`
  - Current: `async def fetch_content(...) -> tuple[str | None, ErrorDetail | None]`
  - Target: `async def fetch_content(...) -> str`

- [ ] Line 44: Update `RetryManagerProtocol.with_retry()`
  - Current: `async def with_retry(...) -> tuple[Any, ErrorDetail | None]`
  - Target: `async def with_retry(...) -> Any`

- [ ] Line 65: Update `LLMProviderServiceProtocol.complete_assessment()`
  - Current: `async def complete_assessment(...) -> tuple[dict[str, Any] | None, ErrorDetail | None]`
  - Target: `async def complete_assessment(...) -> dict[str, Any]`

### Phase 2: Update Implementations

#### Content Client Implementation
**File**: `services/cj_assessment_service/implementations/content_client_impl.py`

- [ ] Lines 41, 60: Update method signatures to remove tuple returns
- [ ] Replace direct ErrorDetail instantiations with factory functions:
  - [ ] Lines 70-86: Replace with `raise_external_service_error()`
  - [ ] Lines 98-114: Replace with `raise_parsing_error()`
  - [ ] Lines 122-154: Replace with appropriate factory
  - [ ] Lines 157-182: Replace with appropriate factory
  - [ ] Lines 185-226: Replace with appropriate factory
- [ ] Update all return statements to either return value or raise exception

#### LLM Provider Service Client
**File**: `services/cj_assessment_service/implementations/llm_provider_service_client.py`

- [ ] Update method signatures on lines: 104, 163, 258, 310, 393, 446, 601, 710, 721
- [ ] Replace all direct ErrorDetail instantiations with factory functions
- [ ] Convert all error returns to raised exceptions
- [ ] Update success paths to return values directly

#### Retry Manager Implementation
**File**: `services/cj_assessment_service/implementations/retry_manager_impl.py`

- [ ] Update method signatures on lines: 153, 171, 192, 195
- [ ] Line 139: Replace direct ErrorDetail instantiation
- [ ] Update retry logic to catch and re-raise HuleEduError
- [ ] Ensure exponential backoff works with exceptions

### Phase 3: Update Service Layer

- [ ] Update all service methods that call the protocols
- [ ] Replace tuple unpacking patterns with try/except blocks
- [ ] Ensure proper error propagation up the call stack

### Phase 4: Update API Routes

- [ ] Check all Quart route handlers in `api/` directory
- [ ] Ensure HuleEduError exceptions are properly handled
- [ ] Verify error responses match expected format

### Phase 5: Update Tests

- [ ] Update all test files to use `assert_raises_huleedu_error`
- [ ] Replace tuple assertion patterns
- [ ] Update mock behaviors to raise exceptions instead of returning tuples
- [ ] Ensure all tests pass with new error handling

### Phase 6: Integration Testing

- [ ] Run service with all dependencies
- [ ] Test error scenarios end-to-end
- [ ] Verify error logging and monitoring
- [ ] Check OpenTelemetry trace integration

## Code Pattern Examples

### Before (Tuple Return)
```python
async def fetch_content(self, content_id: str) -> tuple[str | None, ErrorDetail | None]:
    try:
        response = await self.client.get(f"/content/{content_id}")
        return response.text, None
    except Exception as e:
        error = ErrorDetail(
            error_code=ErrorCode.EXTERNAL_SERVICE_ERROR,
            message=str(e),
            # ... other fields
        )
        return None, error
```

### After (Exception-Based)
```python
async def fetch_content(self, content_id: str) -> str:
    try:
        response = await self.client.get(f"/content/{content_id}")
        return response.text
    except Exception as e:
        raise_external_service_error(
            service="cj_assessment_service",
            operation="fetch_content",
            external_service="content_service",
            message=f"Failed to fetch content {content_id}: {str(e)}",
            correlation_id=self.correlation_id,
            content_id=content_id,
        )
```

### Before (Calling Code)
```python
content, error = await self.content_service.fetch_content(content_id)
if error:
    logger.error("Failed to fetch content", extra=error.to_log_context())
    return None, error
# Use content...
```

### After (Calling Code)
```python
try:
    content = await self.content_service.fetch_content(content_id)
    # Use content...
except HuleEduError:
    # Error is already logged by the exception handler
    raise  # Re-raise to propagate
```

## Verification Steps

1. [ ] All protocol methods have single return types (no tuples)
2. [ ] No direct ErrorDetail instantiation remains
3. [ ] All error factory functions are used appropriately
4. [ ] Tests use new testing utilities
5. [ ] Service starts successfully
6. [ ] Error scenarios produce proper HTTP responses
7. [ ] Logs show structured error data
8. [ ] OpenTelemetry spans include error attributes

## Notes

- CJ Assessment Service already has proper database schema for structured errors
- The service is well-positioned for this migration due to existing ErrorDetail usage
- This is a clean break - no backwards compatibility needed since we're not deployed