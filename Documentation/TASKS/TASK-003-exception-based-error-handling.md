# TASK-003: Implement Pure Exception-Based Error Handling Pattern

**Status**: 95% Complete - Final Verification Phase  
**Priority**: CRITICAL  
**Owner**: Platform Architecture Team  
**Estimated Duration**: 5-7 days (5.5 days completed)  
**Risk Level**: Low (no backwards compatibility needed - pure development stage)

## 🎉 **MIGRATION PROGRESS UPDATE**

**✅ COMPLETED PHASES:**
- **Phase 1-2**: Core Infrastructure ✅ COMPLETE  
- **Phase 2**: CJ Assessment Service Test Migration ✅ COMPLETE
- **Critical Architectural Fix**: Error semantic preservation ✅ COMPLETE

**🔄 CURRENT PHASE:**
- **Phase 3**: Final verification, quality assurance, and documentation

**📊 STATUS**: 27/27 failing tests migrated successfully, all CJ Assessment Service tests passing

## 🔧 **CRITICAL ARCHITECTURAL DISCOVERIES**

During implementation, we identified and resolved a fundamental architectural issue:

**🚨 Issue Discovered**: The LLM Provider Service Client had a catch-all `except Exception:` block that was converting properly classified `HuleEduError` exceptions (with specific error codes like `PARSING_ERROR`, `TIMEOUT`, `CONFIGURATION_ERROR`) into generic `EXTERNAL_SERVICE_ERROR` exceptions, destroying the semantic meaning.

**✅ Solution Implemented**: 
```python
except HuleEduError:
    # Re-raise HuleEduError as-is (preserve error code semantics)
    raise
except Exception as e:
    # Only convert unexpected raw exceptions to structured errors
    raise_external_service_error(...)
```

**📈 Impact**: This fix ensured that error code semantics are preserved throughout the call stack, enabling proper error classification, retry logic, and observability.

**🧪 Test Architecture Fix**: Updated mock retry manager to preserve `HuleEduError` semantics like the real implementation, ensuring tests validate actual behavior rather than incorrect mock behavior.

## 📋 Executive Summary

Implement a **pure exception-based error handling pattern** across the HuleEdu platform using an enhanced ErrorDetail model and HuleEduError as a transport mechanism. This eliminates tuple returns, dramatically reduces boilerplate, and provides world-class observability.

**Key Decision**: No backwards compatibility needed. CJ Assessment Service is the only user of ErrorDetail and will be migrated in a single update.

## 🎯 Core Architecture

### The Three-Layer Pattern

1. **ErrorDetail** (Data): What happened - the canonical error information
2. **HuleEduError** (Transport): How it propagates - exception wrapper
3. **Handlers** (Presentation): How it's shown - API/Kafka boundaries

## 🏗️ Implementation Components

### 1. Enhanced ErrorDetail Model

**Location**: `common_core/src/common_core/models/error_models.py`

```python
"""
Enhanced error models with full observability support.
Replaces both the original ErrorDetail and ErrorContext.
"""
from __future__ import annotations
from datetime import datetime
from typing import Any, Optional
from uuid import UUID
import traceback
from opentelemetry import trace

from pydantic import BaseModel, Field

from common_core.error_enums import ErrorCode


class ErrorDetail(BaseModel):
    """
    The canonical error model for the HuleEdu platform.
    Combines structured data with rich debugging context.
    """
    
    # Core fields
    error_code: ErrorCode
    message: str
    correlation_id: UUID
    timestamp: datetime
    service: str
    
    # Enhanced debugging fields
    operation: str = Field(..., description="Operation being performed")
    stack_trace: Optional[str] = Field(None, description="Python stack trace")
    trace_id: Optional[str] = Field(None, description="OpenTelemetry trace ID")
    span_id: Optional[str] = Field(None, description="OpenTelemetry span ID")
    details: dict[str, Any] = Field(default_factory=dict, description="Additional context")
    
    class Config:
        frozen = True  # Immutable for safety
        
    @classmethod
    def create_with_context(
        cls,
        error_code: ErrorCode,
        message: str,
        service: str,
        operation: str,
        correlation_id: UUID,
        capture_stack: bool = True,
        **additional_details
    ) -> ErrorDetail:
        """
        Factory method that captures full execution context.
        This is the primary way to create ErrorDetail instances.
        """
        # Capture stack trace if requested
        stack_trace = None
        if capture_stack:
            stack_trace = traceback.format_exc()
            # Clean up if no actual exception
            if stack_trace == "NoneType: None\n":
                stack_trace = ''.join(traceback.format_stack()[:-1])
        
        # Get OpenTelemetry context
        trace_id = None
        span_id = None
        current_span = trace.get_current_span()
        
        if current_span and current_span.is_recording():
            span_context = current_span.get_span_context()
            if span_context.is_valid:
                trace_id = format(span_context.trace_id, "032x")
                span_id = format(span_context.span_id, "016x")
        
        return cls(
            error_code=error_code,
            message=message,
            correlation_id=correlation_id,
            timestamp=datetime.utcnow(),
            service=service,
            operation=operation,
            stack_trace=stack_trace,
            trace_id=trace_id,
            span_id=span_id,
            details=additional_details
        )
    
    def to_log_context(self) -> dict[str, Any]:
        """Convert to structured logging context."""
        context = {
            "error.code": self.error_code.value,
            "error.message": self.message,
            "error.service": self.service,
            "error.operation": self.operation,
            "error.timestamp": self.timestamp.isoformat(),
            "correlation_id": str(self.correlation_id),
        }
        
        if self.trace_id:
            context["trace.id"] = self.trace_id
        if self.span_id:
            context["span.id"] = self.span_id
            
        # Flatten details with prefix
        for key, value in self.details.items():
            if isinstance(value, (str, int, float, bool)):
                context[f"error.details.{key}"] = value
            else:
                context[f"error.details.{key}"] = str(value)
            
        return context
```

### 2. HuleEduError Exception

**Location**: `services/libs/huleedu_service_libs/error_handling/huleedu_error.py`

```python
"""
The standard platform exception that transports ErrorDetail.
"""
from __future__ import annotations

from opentelemetry import trace

from common_core.models.error_models import ErrorDetail


class HuleEduError(Exception):
    """
    The standard platform exception. It wraps the canonical ErrorDetail model
    and integrates with the observability stack.
    """

    def __init__(self, error_detail: ErrorDetail) -> None:
        """
        Initializes the HuleEduError.

        Args:
            error_detail: The canonical, structured error data object.
        """
        super().__init__(error_detail.message)
        self.error_detail = error_detail

        # Auto-record this exception to the current OpenTelemetry span
        current_span = trace.get_current_span()
        if current_span and current_span.is_recording():
            current_span.record_exception(self)
            # Set key error attributes for easy filtering in observability tools
            current_span.set_attribute("error.code", self.error_detail.error_code.value)
            current_span.set_attribute("error.service", self.error_detail.service)
            current_span.set_attribute("error.operation", self.error_detail.operation)

    @property
    def correlation_id(self) -> str:
        """Provides convenient access to the correlation ID for logging."""
        return str(self.error_detail.correlation_id)
```

### 3. Centralized Error Factories

**Location**: `services/libs/huleedu_service_libs/error_handling/factories.py`

```python
"""
Standardized error factories that create and raise HuleEduError exceptions.
"""
from typing import NoReturn, Optional, Any
from uuid import UUID

from common_core.error_enums import ErrorCode, FileValidationErrorCode, ClassManagementErrorCode
from common_core.models.error_models import ErrorDetail
from .huleedu_error import HuleEduError


def raise_validation_error(
    service: str,
    operation: str,
    field: str,
    message: str,
    correlation_id: UUID,
    value: Optional[Any] = None,
    **additional_context
) -> NoReturn:
    """Create and raise a validation error."""
    error_detail = ErrorDetail.create_with_context(
        error_code=ErrorCode.VALIDATION_ERROR,
        message=f"Validation failed for {field}: {message}",
        service=service,
        operation=operation,
        correlation_id=correlation_id,
        field=field,
        value=str(value) if value is not None else None,
        **additional_context
    )
    raise HuleEduError(error_detail)


def raise_resource_not_found(
    service: str,
    operation: str,
    resource_type: str,
    resource_id: str,
    correlation_id: UUID,
    **additional_context
) -> NoReturn:
    """Create and raise a resource not found error."""
    error_detail = ErrorDetail.create_with_context(
        error_code=ErrorCode.RESOURCE_NOT_FOUND,
        message=f"{resource_type} with ID '{resource_id}' not found",
        service=service,
        operation=operation,
        correlation_id=correlation_id,
        resource_type=resource_type,
        resource_id=resource_id,
        **additional_context
    )
    raise HuleEduError(error_detail)


def raise_external_service_error(
    service: str,
    operation: str,
    external_service: str,
    error_message: str,
    correlation_id: UUID,
    status_code: Optional[int] = None,
    **additional_context
) -> NoReturn:
    """Create and raise an external service error."""
    error_detail = ErrorDetail.create_with_context(
        error_code=ErrorCode.EXTERNAL_SERVICE_ERROR,
        message=f"External service '{external_service}' failed: {error_message}",
        service=service,
        operation=operation,
        correlation_id=correlation_id,
        external_service=external_service,
        status_code=status_code,
        **additional_context
    )
    raise HuleEduError(error_detail)


def raise_configuration_error(
    service: str,
    operation: str,
    config_key: str,
    reason: str,
    correlation_id: UUID,
    **additional_context
) -> NoReturn:
    """Create and raise a configuration error."""
    error_detail = ErrorDetail.create_with_context(
        error_code=ErrorCode.CONFIGURATION_ERROR,
        message=f"Configuration error for '{config_key}': {reason}",
        service=service,
        operation=operation,
        correlation_id=correlation_id,
        config_key=config_key,
        **additional_context
    )
    raise HuleEduError(error_detail)


def raise_parsing_error(
    service: str,
    operation: str,
    content_type: str,
    error_message: str,
    correlation_id: UUID,
    **additional_context
) -> NoReturn:
    """Create and raise a parsing error."""
    error_detail = ErrorDetail.create_with_context(
        error_code=ErrorCode.PARSING_ERROR,
        message=f"Failed to parse {content_type}: {error_message}",
        service=service,
        operation=operation,
        correlation_id=correlation_id,
        content_type=content_type,
        **additional_context
    )
    raise HuleEduError(error_detail)


# Service-specific error factories

def raise_file_validation_error(
    service: str,
    operation: str,
    error_code: FileValidationErrorCode,
    file_id: str,
    correlation_id: UUID,
    actual_size: Optional[int] = None,
    expected_size: Optional[int] = None,
    **additional_context
) -> NoReturn:
    """Create and raise a file validation error."""
    messages = {
        FileValidationErrorCode.EMPTY_CONTENT: "File content is empty",
        FileValidationErrorCode.CONTENT_TOO_SHORT: f"File content too short (actual: {actual_size}, minimum: {expected_size})",
        FileValidationErrorCode.CONTENT_TOO_LONG: f"File content too long (actual: {actual_size}, maximum: {expected_size})",
        FileValidationErrorCode.RAW_STORAGE_FAILED: "Failed to store raw file content",
        FileValidationErrorCode.TEXT_EXTRACTION_FAILED: "Failed to extract text from file",
    }
    
    error_detail = ErrorDetail.create_with_context(
        error_code=error_code,  # Accepts enum directly
        message=messages.get(error_code, f"File validation failed: {error_code.value}"),
        service=service,
        operation=operation,
        correlation_id=correlation_id,
        file_id=file_id,
        actual_size=actual_size,
        expected_size=expected_size,
        **additional_context
    )
    raise HuleEduError(error_detail)


# Add similar factories for all error codes...
```

### 4. Quart Error Handler Integration

**Location**: `services/libs/huleedu_service_libs/error_handling/quart_handlers.py`

```python
"""
Quart application error handlers for HuleEduError.
"""
from typing import Dict
from enum import Enum

from quart import Quart, jsonify, g
from opentelemetry.trace import Status, StatusCode

from common_core.error_enums import ErrorCode
from .huleedu_error import HuleEduError
from huleedu_service_libs.logging_utils import get_logger

logger = get_logger(__name__)

# Error code to HTTP status mapping
ERROR_TO_STATUS: Dict[str, int] = {
    ErrorCode.VALIDATION_ERROR.value: 400,
    ErrorCode.MISSING_REQUIRED_FIELD.value: 400,
    ErrorCode.INVALID_REQUEST.value: 400,
    ErrorCode.AUTHENTICATION_ERROR.value: 401,
    ErrorCode.INVALID_API_KEY.value: 401,
    ErrorCode.RESOURCE_NOT_FOUND.value: 404,
    ErrorCode.RATE_LIMIT.value: 429,
    ErrorCode.QUOTA_EXCEEDED.value: 429,
    ErrorCode.SERVICE_UNAVAILABLE.value: 503,
    ErrorCode.CIRCUIT_BREAKER_OPEN.value: 503,
}


def register_error_handlers(app: Quart) -> None:
    """
    Register centralized error handlers for a Quart application.
    This should be called once during app initialization.
    """
    
    @app.errorhandler(HuleEduError)
    async def handle_huleedu_error(error: HuleEduError):
        """Handle HuleEduError exceptions and convert to JSON responses."""
        # Log full context for observability
        logger.error(
            "Request failed with HuleEduError",
            extra=error.error_detail.to_log_context(),
            exc_info=True
        )
        
        # Update OpenTelemetry span if available
        if hasattr(g, 'current_span') and g.current_span:
            g.current_span.set_status(
                Status(StatusCode.ERROR, error.error_detail.message)
            )
        
        # Determine HTTP status code
        error_code_value = (
            error.error_detail.error_code.value 
            if isinstance(error.error_detail.error_code, Enum)
            else error.error_detail.error_code
        )
        status_code = ERROR_TO_STATUS.get(error_code_value, 500)
        
        # Build error response
        response_body = {
            "error": {
                "code": error_code_value,
                "message": error.error_detail.message,
                "correlation_id": str(error.error_detail.correlation_id),
                "service": error.error_detail.service,
                "operation": error.error_detail.operation,
            }
        }
        
        # Add trace ID if available for debugging
        if error.error_detail.trace_id:
            response_body["error"]["trace_id"] = error.error_detail.trace_id
        
        return jsonify(response_body), status_code
    
    @app.errorhandler(Exception)
    async def handle_unexpected_error(error: Exception):
        """Handle unexpected exceptions that aren't HuleEduError."""
        logger.error(
            "Unexpected error occurred",
            exc_info=True
        )
        
        # Try to get correlation ID from request context
        correlation_id = getattr(g, 'correlation_id', 'unknown')
        
        return jsonify({
            "error": {
                "code": ErrorCode.UNKNOWN_ERROR.value,
                "message": "An unexpected error occurred",
                "correlation_id": correlation_id
            }
        }), 500
```

### 5. Testing Utilities

**Location**: `services/libs/huleedu_service_libs/error_handling/testing.py`

```python
"""Testing utilities for exception-based error handling."""
import pytest
from typing import Type, Optional, Dict, Any, Callable
from contextlib import contextmanager

from common_core.error_enums import ErrorCode
from .huleedu_error import HuleEduError


@contextmanager
def assert_raises_huleedu_error(
    error_code: ErrorCode,
    service: str,
    operation: str,
    message_contains: Optional[str] = None,
    correlation_id: Optional[str] = None,
    detail_contains: Optional[Dict[str, Any]] = None
):
    """
    Context manager for testing HuleEduError exceptions.
    
    Example:
        with assert_raises_huleedu_error(
            error_code=ErrorCode.VALIDATION_ERROR,
            service="my_service",
            operation="validate_input",
            message_contains="invalid format"
        ):
            validate_user_input(bad_data)
    """
    with pytest.raises(HuleEduError) as exc_info:
        yield exc_info
        
    # Validate error properties
    error = exc_info.value
    assert error.error_detail.error_code == error_code
    assert error.error_detail.service == service
    assert error.error_detail.operation == operation
    
    if message_contains:
        assert message_contains in error.error_detail.message
        
    if correlation_id:
        assert str(error.error_detail.correlation_id) == correlation_id
        
    if detail_contains:
        for key, value in detail_contains.items():
            assert key in error.error_detail.details
            assert error.error_detail.details[key] == value
```

## 📊 Implementation Plan

### Phase 1: Core Library Updates (Day 1-2)

1. **Delete ErrorContext** from `context_manager.py`
2. **Implement Enhanced ErrorDetail** in `common_core`
3. **Update HuleEduError** to use ErrorDetail
4. **Create All Factory Functions**
5. **Implement Quart Handlers**
6. **Create Testing Utilities**
7. **Update all exports** in `__init__.py` files

### Phase 2: CJ Assessment Service Migration (Day 3-4)

Since CJ Assessment is the only service using ErrorDetail, we'll do a complete migration:

1. **Update app.py**:

   ```python
   from huleedu_service_libs.error_handling import register_error_handlers
   
   app = Quart(__name__)
   register_error_handlers(app)  # One-line integration
   ```

2. **Remove ALL Tuple Returns**:
   - Update all protocol definitions
   - Change all function signatures
   - Remove `Optional[ErrorDetail]` returns

3. **Replace Error Returns with Factories**:

   ```python
   # Before
   return None, ErrorDetail(...)
   
   # After
   raise_validation_error(
       service="cj_assessment_service",
       operation="validate_essay",
       field="content",
       message="Essay content too short",
       correlation_id=correlation_id
   )
   ```

4. **Update Tests**:

   ```python
   # Before
   result, error = await process_essay(...)
   assert error is not None
   assert error.error_code == ErrorCode.VALIDATION_ERROR
   
   # After
   with assert_raises_huleedu_error(
       error_code=ErrorCode.VALIDATION_ERROR,
       service="cj_assessment_service",
       operation="process_essay"
   ):
       await process_essay(...)
   ```

### Phase 3: New Service Template (Day 5)

Create a template for all new services showing the pattern:

```python
# app.py
from quart import Quart
from huleedu_service_libs.error_handling import register_error_handlers

app = Quart(__name__)
register_error_handlers(app)

@app.route("/api/v1/resource/<id>")
async def get_resource(id: str):
    try:
        # Clean business logic - no error handling
        resource = await resource_service.get_by_id(id)
        return jsonify(resource.model_dump()), 200
    except HuleEduError as e:
        # Handled by register_error_handlers
        raise

# service.py
async def get_by_id(self, id: str) -> Resource:
    # No tuple returns, no error checking
    entity = await self.repository.find_by_id(id)
    if not entity:
        raise_resource_not_found(
            service="my_service",
            operation="get_by_id",
            resource_type="Resource",
            resource_id=id,
            correlation_id=self.correlation_id
        )
    return self._entity_to_model(entity)
```

## ✅ Benefits

### Immediate Benefits

- **66% Code Reduction**: 15 lines → 5 lines in typical functions
- **Zero Boilerplate**: No error propagation code
- **Type Safety**: Clean return types `-> Student` not `-> tuple[...]`
- **Better IDE Support**: Autocomplete works properly

### Long-term Benefits

- **Full Stack Traces**: Know exactly where errors originate
- **Automatic Context**: OpenTelemetry integration built-in
- **Consistent Errors**: Every error has the same structure
- **Better Monitoring**: Single error type to track and alert on

## 🚨 Migration Notes

### What Changes for Developers

1. **No More Tuple Returns**:

   ```python
   # Old
   async def get_user(id: str) -> tuple[User | None, ErrorDetail | None]:
   
   # New
   async def get_user(id: str) -> User:
   ```

2. **Use Factory Functions**:

   ```python
   # Old
   return None, ErrorDetail(error_code=ErrorCode.NOT_FOUND, ...)
   
   # New
   raise_resource_not_found(...)
   ```

3. **Simpler Tests**:

   ```python
   # Old
   result, error = await my_function()
   assert error is not None
   
   # New
   with pytest.raises(HuleEduError):
       await my_function()
   ```

### What Stays the Same

- Error codes (same enums)
- Correlation IDs (same propagation)
- Logging (same structured logs)
- Monitoring (same metrics)

## 📈 Success Metrics

- [x] **ErrorContext completely removed** ✅ COMPLETE
- [x] **Enhanced ErrorDetail deployed** ✅ COMPLETE 
- [x] **All factories implemented** ✅ COMPLETE
- [x] **CJ Assessment migrated (zero tuple returns)** ✅ COMPLETE - All 27 tests migrated successfully
- [ ] **New service template created** 🔄 PENDING VERIFICATION
- [ ] **Developer documentation updated** 🔄 PENDING VERIFICATION

## 🔍 **FINAL VERIFICATION CHECKLIST**

**Quality Assurance Requirements:**
- [ ] Zero MyPy type errors: `pdm run typecheck-all`
- [ ] Zero Ruff linting issues: `pdm run lint-all` 
- [ ] Zero test failures: `pdm run test-all`
- [ ] Zero test warnings: Complete test suite clean
- [ ] Complete tuple removal audit in CJ Assessment Service

**Documentation Requirements:**
- [ ] Service template with exception-based patterns created
- [ ] Developer documentation updated with new patterns
- [ ] Migration notes verified and complete
- [ ] All key files properly documented

## 🔗 Key Files

- `common_core/src/common_core/models/error_models.py` - Enhanced ErrorDetail
- `services/libs/huleedu_service_libs/error_handling/huleedu_error.py` - HuleEduError
- `services/libs/huleedu_service_libs/error_handling/factories.py` - Error factories
- `services/libs/huleedu_service_libs/error_handling/quart_handlers.py` - Quart integration

This architecture provides a world-class error handling system that is simple, powerful, and observable.
