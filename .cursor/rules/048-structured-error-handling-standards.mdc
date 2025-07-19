---
description: Exception-based error handling pattern
globs: 
alwaysApply: false
---
# 048: Exception-Based Error Handling

## Architecture

```python
# Data (common_core) - PURE, NO METHODS
class ErrorDetail(BaseModel):
    error_code: ErrorCode
    message: str
    correlation_id: UUID
    timestamp: datetime
    service: str
    operation: str
    # ... only fields

# Transport (service libs)
class HuleEduError(Exception):
    def __init__(self, error_detail: ErrorDetail)

# Creation (service libs)
raise_validation_error(service="x", operation="y", field="z", message="...", correlation_id=uuid)
```

## Patterns

```python
# PROTOCOL SIGNATURES
async def fetch_content(self, content_id: str) -> str:  # NOT tuple

# RAISING ERRORS
raise_resource_not_found(
    service="my_service",
    operation="get_item", 
    resource_type="Item",
    resource_id=item_id,
    correlation_id=self.correlation_id
)

# BOUNDARY HANDLERS ONLY
try:
    result = await service.operation()
except HuleEduError:
    # Already logged by exception
    raise
```

## Prohibited

```python
# NEVER
return None, ErrorDetail(...)
return result, None
ErrorDetail.create_with_context()  # Use factory
error_message: str fields
```

## Imports

```python
# Core error handling (framework-agnostic) - USE MAIN MODULE
from common_core.error_enums import ErrorCode
from common_core.models.error_models import ErrorDetail

# Framework-specific error handlers - USE FRAMEWORK SUBMODULES
# FastAPI services:
from huleedu_service_libs.error_handling.fastapi import register_error_handlers

# Quart services:  
from huleedu_service_libs.error_handling.quart import register_error_handlers, create_error_response
```
