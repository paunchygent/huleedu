---
id: "048-structured-error-handling-standards"
type: "implementation"
created: 2025-07-09
last_updated: 2025-11-17
scope: "backend"
---
# 048: Error Handling Patterns

## Exception Pattern (Boundary Operations)

```python
# Protocol signatures - return values, not tuples
async def fetch_content(self, content_id: str) -> str:

# Raise exceptions for boundary violations
raise_resource_not_found(
    service="my_service",
    operation="get_item",
    resource_type="Item",
    resource_id=item_id,
    correlation_id=self.correlation_id
)

# Boundary handlers only
try:
    result = await service.operation()
except HuleEduError:
    raise
```

## Result Monad Pattern (Internal Control Flow)

```python
from huleedu_service_libs import Result

# Return Result for recoverable internal operations
async def _hydrate_prompt_text(...) -> Result[str, PromptHydrationFailure]:
    if not storage_id:
        return Result.ok("")

    try:
        text = await client.fetch_content(storage_id)
        return Result.ok(text) if text else Result.err(
            PromptHydrationFailure(reason="empty_content", storage_id=storage_id)
        )
    except HuleEduError:
        return Result.err(
            PromptHydrationFailure(reason="content_service_error", storage_id=storage_id)
        )

# Caller inspects result
result = await _hydrate_prompt_text(...)
if result.is_ok:
    text = result.value
else:
    failure = result.error
    logger.warning(f"Hydration failed: {failure.reason}")

# Error payload: frozen dataclass
@dataclass(frozen=True)
class PromptHydrationFailure:
    reason: str
    storage_id: str | None = None
```

## Usage Decision

- **Result**: Internal operations, recoverable failures, normal control flow
- **Exception**: Boundary operations (HTTP/events), unexpected failures, cross-service violations

## Imports

```python
from huleedu_service_libs import Result
from common_core.error_enums import ErrorCode
from common_core.models.error_models import ErrorDetail
from huleedu_service_libs.error_handling.quart import register_error_handlers
```
