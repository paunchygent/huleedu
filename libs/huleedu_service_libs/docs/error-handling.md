# Error Handling

Framework-agnostic structured error handling with explicit framework separation for HuleEdu services.

## Overview

The error handling library provides consistent, structured error responses across all HuleEdu services while maintaining clean separation between frameworks. It features zero framework coupling in core components, with framework-specific handlers isolated in separate submodules.

### Key Features

- **Framework Separation**: FastAPI and Quart handlers in separate submodules
- **Structured Error Format**: Consistent HuleEduError with correlation IDs and context
- **Factory Functions**: Pre-built error factories for common scenarios
- **Testing Utilities**: Comprehensive test helpers for error scenarios
- **Zero Framework Coupling**: Core error handling independent of web frameworks

## Architecture

The error handling library follows a clean separation pattern:

```
error_handling/
├── __init__.py              # Core, framework-agnostic exports
├── factories.py             # Generic error factory functions
├── huleedu_error.py         # Core exception class
├── error_detail_factory.py  # Error detail creation utilities
├── fastapi/                 # FastAPI-specific handlers
│   └── __init__.py
├── quart/                   # Quart-specific handlers
│   └── __init__.py
├── testing.py               # Test utilities
└── [service-specific factories]
```

## Import Patterns

### WORKING Patterns (use these)

```python
# Core exception and utilities
from huleedu_service_libs.error_handling.huleedu_error import HuleEduError
from huleedu_service_libs.error_handling.error_detail_factory import create_error_detail_with_context

# Framework-specific handlers (explicit)
from huleedu_service_libs.error_handling.fastapi import register_error_handlers  # FastAPI
from huleedu_service_libs.error_handling.quart import register_error_handlers    # Quart

# Generic error factories (these work from main module)
from huleedu_service_libs.error_handling import (
    raise_validation_error,
    raise_resource_not_found,
    raise_authentication_error,
    raise_authorization_error
)
```

### BROKEN Patterns (avoid these)

```python
# ❌ These imports will fail in container environments
from huleedu_service_libs.error_handling import HuleEduError
from huleedu_service_libs.error_handling import create_error_detail_with_context

# ❌ Mixed framework imports cause dependency issues
from huleedu_service_libs.error_handling import register_error_handlers
```

## Core Error Model

```python
from common_core.models.error_models import ErrorDetail
from huleedu_service_libs.error_handling.huleedu_error import HuleEduError

# Core exception with structured data
class HuleEduError(Exception):
    def __init__(self, error_detail: ErrorDetail):
        self.error_detail = error_detail
        super().__init__(error_detail.message)

# Structured error detail
class ErrorDetail(BaseModel):
    error_code: ErrorCode
    message: str
    correlation_id: UUID
    timestamp: datetime
    service: str
    operation: str
    details: dict[str, Any] = Field(default_factory=dict)
```

## Framework-Specific Integration

### FastAPI Services

```python
# Import framework-specific handlers
from huleedu_service_libs.error_handling.fastapi import register_error_handlers

# Setup in main.py
app = FastAPI()
register_error_handlers(app)

# Use core factories in routes
from huleedu_service_libs.error_handling import (
    raise_resource_not_found,
    raise_validation_error,
    raise_authorization_error
)

@app.get("/items/{item_id}")
async def get_item(item_id: str):
    if not item_exists(item_id):
        raise_resource_not_found(
            service="api_gateway_service",
            operation="get_item",
            resource_type="item",
            resource_id=item_id,
            correlation_id=get_correlation_id()
        )
```

### Quart Services

```python
# Import framework-specific handlers
from huleedu_service_libs.error_handling.quart import (
    register_error_handlers,
    create_error_response
)

# Setup in app.py
app = Quart(__name__)
register_error_handlers(app)

# Use core factories in routes
from huleedu_service_libs.error_handling import raise_validation_error

@bp.route("/process", methods=["POST"])
async def process_data():
    try:
        data = await request.get_json()
        if not validate_data(data):
            raise_validation_error(
                service="processing_service",
                operation="process_data",
                field="required_field",
                message="Field validation failed",
                correlation_id=get_correlation_id()
            )
    except HuleEduError as e:
        return create_error_response(e.error_detail)
```

## Common Error Factories

### Resource Errors

```python
from huleedu_service_libs.error_handling import (
    raise_resource_not_found,
    raise_validation_error,
    raise_authorization_error,
    raise_authentication_error
)

# 404 Not Found
raise_resource_not_found(
    service="content_service",
    operation="get_content",
    resource_type="content",
    resource_id="content123",
    correlation_id=correlation_id
)

# 401 Unauthorized  
raise_authentication_error(
    service="api_gateway",
    operation="verify_token",
    message="Invalid JWT token",
    correlation_id=correlation_id
)

# 403 Forbidden
raise_authorization_error(
    service="api_gateway", 
    operation="check_ownership",
    message="Resource access denied",
    correlation_id=correlation_id,
    user_id=user_id,
    resource_id=resource_id
)
```

### Service Integration Errors

```python
from huleedu_service_libs.error_handling import (
    raise_external_service_error,
    raise_timeout_error,
    raise_connection_error
)

# External service failures
raise_external_service_error(
    service="api_gateway",
    operation="proxy_request",
    external_service="downstream_api",
    message="Service unavailable",
    correlation_id=correlation_id,
    status_code=503
)

# Timeout scenarios
raise_timeout_error(
    service="llm_provider",
    operation="generate_response", 
    timeout_seconds=30.0,
    message="LLM request timeout",
    correlation_id=correlation_id
)
```

## Error Response Format

All errors follow the same structured format:

```json
{
  "error": {
    "code": "RESOURCE_NOT_FOUND",
    "message": "content with ID 'content123' not found",
    "correlation_id": "550e8400-e29b-41d4-a716-446655440000",
    "timestamp": "2024-01-15T10:30:45.123Z",
    "service": "content_service",
    "operation": "get_content",
    "details": {
      "resource_type": "content",
      "resource_id": "content123"
    }
  }
}
```

## Testing Error Scenarios

```python
from huleedu_service_libs.error_handling.testing import (
    assert_raises_huleedu_error,
    ErrorDetailMatcher,
    create_test_huleedu_error
)

async def test_resource_not_found():
    """Test error handling for missing resources."""
    
    # Test that error is raised correctly
    with assert_raises_huleedu_error(
        error_code=ErrorCode.RESOURCE_NOT_FOUND,
        service="content_service",
        operation="get_content"
    ):
        await service.get_content("nonexistent")
    
    # Test error details
    try:
        await service.get_content("nonexistent")
    except HuleEduError as e:
        matcher = ErrorDetailMatcher(
            error_code=ErrorCode.RESOURCE_NOT_FOUND,
            message_contains="not found"
        )
        assert matcher.matches(e.error_detail)
```

## Service-Specific Error Factories

Some services have specialized error factories:

```python
# LLM Provider specific errors
from huleedu_service_libs.error_handling.llm_provider_factories import (
    raise_llm_provider_error,
    raise_llm_model_not_found
)

# File validation errors  
from huleedu_service_libs.error_handling.file_validation_factories import (
    raise_content_too_long,
    raise_text_extraction_failed
)

# Class management errors
from huleedu_service_libs.error_handling.class_management_factories import (
    raise_class_not_found,
    raise_student_not_found
)
```

## Migration from Legacy Error Handling

### Before (Framework-coupled)

```python
# Anti-pattern - framework-specific error handling mixed with business logic
from huleedu_service_libs.error_handling import register_fastapi_error_handlers
# ❌ This would fail in Quart services due to unconditional FastAPI imports
```

### After (Framework-separated)

```python
# ✅ Explicit framework imports
# FastAPI services:
from huleedu_service_libs.error_handling.fastapi import register_error_handlers

# Quart services:
from huleedu_service_libs.error_handling.quart import register_error_handlers

# Core error factories (framework-agnostic):
from huleedu_service_libs.error_handling import (
    raise_resource_not_found,
    raise_validation_error,
    # ... other factories
)
```

## Best Practices

1. **Use Framework-Specific Imports**: Always import handlers from the appropriate submodule
2. **Consistent Error Context**: Include service, operation, and correlation_id in all errors
3. **Meaningful Messages**: Write human-readable error messages with context
4. **Proper HTTP Mapping**: Let framework handlers map error codes to HTTP status codes
5. **Test Error Paths**: Use testing utilities to verify error handling behavior
6. **Correlation ID Propagation**: Maintain correlation IDs across service boundaries

## Anti-Patterns to Avoid

1. **Mixed Framework Imports**: Don't import from main `__init__.py` for framework handlers
2. **Generic Exception Handling**: Always use specific error factories
3. **String-based Error Codes**: Use ErrorCode enum values
4. **Missing Context**: Always include correlation_id and operation context
5. **Framework Coupling**: Keep business logic independent of HTTP framework details
