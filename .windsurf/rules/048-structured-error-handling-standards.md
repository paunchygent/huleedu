---
description: Structured error handling with common_core ErrorCode enums
globs: 
alwaysApply: false
---
# 048: Structured Error Handling Standards

## Mandatory Pattern

**ALL** error handling uses `ErrorDetail` objects from `common_core.error_enums`:

```python
# REQUIRED
return result, ErrorDetail(
    error_code=ErrorCode.VALIDATION_ERROR,
    message="Error message",
    correlation_id=correlation_id,  # Explicit parameter
    timestamp=datetime.now(UTC)
)

# Protocol return: tuple[T | None, ErrorDetail | None]
```

## Prohibited

```python
# NEVER
return None, "Error message"
error_message = str(exception)
```

## Error Code Management

All error enums **MUST** be defined in `common_core.error_enums`. Extend with service-specific enums or add generic enums for cross-cutting concerns. **NEVER** define error enums outside `common_core`.

## Refactoring Mandate

AI agents **MUST** refactor unstructured error handling when encountered. Replace `str` errors with `ErrorDetail` objects.
