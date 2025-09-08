# TASK-043: MyPy Strict Typing Compliance - Full Clean Refactor

## Status: IN PROGRESS

**Created**: 2025-01-30
**Priority**: HIGH
**Type**: REFACTOR / COMPLIANCE

## Problem Statement

The HuleEdu service libraries currently violate strict MyPy typing standards (Rules 050 & 086):

- Multiple `cast()` usages (FORBIDDEN per Rule 050)
- `# type: ignore` comments (FORBIDDEN)
- Dynamic proxy pattern `make_resilient()` that requires cast() to maintain type safety
- Incomplete type annotations in various modules

**Current Violations**:

1. `content_service_client.py:181` - Unnecessary cast(str, storage_id)
2. `logging_utils.py:94` - type: ignore[arg-type] on processors
3. `resilient_client.py:105` - cast(T, wrapper) for dynamic proxy
4. `resilient_kafka_bus.py:127` - Circuit breaker type inference issues

## Architectural Decision: NO BACKWARDS COMPATIBILITY

**Mandate**: "We are still in pure development. We do not want ANY backwards compatibility."

This enables a CLEAN REFACTOR without migration paths, deprecation notices, or interim solutions.

## Solution Architecture

### Core Principle

Replace the generic dynamic proxy pattern with explicit, typed resilient wrappers for each protocol. Every resilient component is explicitly typed with no magic, no cast(), no Any, no type: ignore.

### Dependency Direction Rule

**CRITICAL ARCHITECTURAL PRINCIPLE**:

- Dependency flow: `Services → Shared Libraries → Common Core`
- **NEVER**: `Shared Libraries → Services` (circular dependency anti-pattern)
- **Consequence**: Service-specific protocols require service-specific resilient wrappers

This means:

- **Shared protocols** (HttpClient, ContentService) → Resilient wrappers in shared library ✅
- **Service-specific protocols** (LLMProvider, BatchConductor) → Resilient wrappers in the service itself ✅

### Pattern

```python
# BEFORE (Dynamic Proxy - FORBIDDEN)
def make_resilient(impl: T, circuit_breaker: CircuitBreaker) -> T:
    return cast(T, ResilientClientWrapper(impl, circuit_breaker))  # FORBIDDEN cast()

# AFTER (Typed Wrapper - CLEAN)
class ResilientHttpClient(HttpClientProtocol):
    def __init__(self, delegate: HttpClientProtocol, circuit_breaker: CircuitBreaker):
        self._delegate = delegate
        self._circuit_breaker = circuit_breaker
    
    async def get(self, url: str, ...) -> str:
        return await self._circuit_breaker.call(self._delegate.get, url, ...)
```

## Implementation Plan

### Phase 1: Fix Existing Type Issues

#### 1.1 Fix logging_utils.py Processor Import

```python
# Fix name collision with conditional import
try:
    from structlog.typing import Processor
except ImportError:
    from typing import Protocol
    class Processor(Protocol):
        def __call__(self, logger: Any, name: str, event_dict: Any) -> Any: ...

# Use typed list
processors: list[Processor] = [...]  # No type: ignore needed
```

#### 1.2 CircuitBreaker Overloads (ALREADY APPLIED)

```python
@overload
async def call(self, func: Callable[..., Awaitable[T]], *args, **kwargs) -> T: ...

@overload
async def call(self, func: Callable[..., T], *args, **kwargs) -> T: ...

async def call(self, func: Callable[..., Any], *args, **kwargs) -> Any:
    # Implementation
```

#### 1.3 Fix content_service_client.py Type Narrowing (ALREADY APPLIED)

```python
# Extract with explicit type
storage_id_obj: Any = result.get("storage_id")
if not storage_id_obj or not isinstance(storage_id_obj, str):
    # Error handling
storage_id: str = storage_id_obj  # Type narrowed
return storage_id  # No cast needed
```

### Phase 2: Create Typed Resilient Wrappers

#### 2.1 File Structure

**Shared Library** (for shared protocols only):

```
libs/huleedu_service_libs/src/huleedu_service_libs/resilience/
├── __init__.py              # Export typed wrappers
├── circuit_breaker.py       # Core circuit breaker with overloads
├── http_client.py          # NEW: ResilientHttpClient (shared protocol)
├── content_service.py      # NEW: ResilientContentServiceClient (shared protocol)
├── kafka_bus.py            # EXISTING: ResilientKafkaPublisher (keep as-is)
├── metrics_bridge.py       # EXISTING: Metrics integration
├── registry.py             # EXISTING: Circuit breaker registry
└── resilient_client.py     # DELETE: Generic dynamic proxy
```

**Service-Specific Wrappers** (respect service boundaries):

```
services/llm_provider_service/implementations/
├── resilient_llm_provider.py  # NEW: Service-specific resilient wrapper

services/batch_orchestrator_service/implementations/
├── resilient_batch_client.py  # NEW: If needed for service-specific protocols
```

**CRITICAL**: Shared libraries MUST NOT import from services. Service-specific protocols get service-specific resilient wrappers.

#### 2.2 ResilientHttpClient Implementation

```python
# resilience/http_client.py
from typing import Any
from uuid import UUID
from huleedu_service_libs.http_client.protocols import HttpClientProtocol
from huleedu_service_libs.resilience.circuit_breaker import CircuitBreaker

class ResilientHttpClient(HttpClientProtocol):
    """HTTP client with circuit breaker protection."""
    
    def __init__(self, delegate: HttpClientProtocol, circuit_breaker: CircuitBreaker):
        self._delegate = delegate
        self._circuit_breaker = circuit_breaker
    
    async def get(
        self,
        url: str,
        correlation_id: UUID,
        timeout_seconds: int = 10,
        headers: dict[str, str] | None = None,
        **context: Any,
    ) -> str:
        """GET with circuit breaker protection."""
        return await self._circuit_breaker.call(
            self._delegate.get, url, correlation_id, timeout_seconds, headers, **context
        )
    
    async def post(
        self,
        url: str,
        data: bytes | str,
        correlation_id: UUID,
        timeout_seconds: int = 10,
        headers: dict[str, str] | None = None,
        **context: Any,
    ) -> dict[str, Any]:
        """POST with circuit breaker protection."""
        return await self._circuit_breaker.call(
            self._delegate.post, url, data, correlation_id, timeout_seconds, headers, **context
        )
```

#### 2.3 ResilientContentServiceClient Implementation

```python
# resilience/content_service.py
from uuid import UUID
from common_core.domain_enums import ContentType
from huleedu_service_libs.http_client.protocols import ContentServiceClientProtocol
from huleedu_service_libs.resilience.circuit_breaker import CircuitBreaker

class ResilientContentServiceClient(ContentServiceClientProtocol):
    """Content Service client with circuit breaker protection."""
    
    def __init__(self, delegate: ContentServiceClientProtocol, circuit_breaker: CircuitBreaker):
        self._delegate = delegate
        self._circuit_breaker = circuit_breaker
    
    async def fetch_content(
        self,
        storage_id: str,
        correlation_id: UUID,
        essay_id: str | None = None,
    ) -> str:
        """Fetch content with circuit breaker protection."""
        return await self._circuit_breaker.call(
            self._delegate.fetch_content, storage_id, correlation_id, essay_id
        )
    
    async def store_content(
        self,
        content: str,
        content_type: ContentType,
        correlation_id: UUID,
        essay_id: str | None = None,
    ) -> str:
        """Store content with circuit breaker protection."""
        return await self._circuit_breaker.call(
            self._delegate.store_content, content, content_type, correlation_id, essay_id
        )
```

#### 2.4 Service-Specific Resilient Wrapper Example

```python
# services/llm_provider_service/implementations/resilient_llm_provider.py
from uuid import UUID
from huleedu_service_libs.resilience.circuit_breaker import CircuitBreaker
from services.llm_provider_service.protocols import LLMProviderProtocol
from services.llm_provider_service.internal_models import LLMProviderResponse

class ResilientLLMProvider(LLMProviderProtocol):
    """LLM provider with circuit breaker protection.
    
    This is a SERVICE-SPECIFIC wrapper that lives within the LLM Provider Service.
    It imports the service's own protocol and uses the shared CircuitBreaker.
    """
    
    def __init__(self, delegate: LLMProviderProtocol, circuit_breaker: CircuitBreaker):
        self._delegate = delegate
        self._circuit_breaker = circuit_breaker
    
    async def generate_comparison(
        self,
        user_prompt: str,
        essay_a: str,
        essay_b: str,
        correlation_id: UUID,
        system_prompt_override: str | None = None,
        model_override: str | None = None,
        temperature_override: float | None = None,
        max_tokens_override: int | None = None,
    ) -> LLMProviderResponse:
        """Generate comparison with circuit breaker protection."""
        return await self._circuit_breaker.call(
            self._delegate.generate_comparison,
            user_prompt,
            essay_a,
            essay_b,
            correlation_id,
            system_prompt_override,
            model_override,
            temperature_override,
            max_tokens_override
        )
```

**Key Architectural Rule**: Service-specific protocols require service-specific wrappers. The shared library provides the CircuitBreaker mechanism, but each service creates its own typed wrappers for its protocols.

### Phase 3: Update All DI Providers

#### 3.1 api_gateway_service/di.py

```python
# BEFORE
from huleedu_service_libs.resilience.resilient_client import make_resilient
yield make_resilient(client, circuit_breaker)

# AFTER
from huleedu_service_libs.resilience.http_client import ResilientHttpClient
yield ResilientHttpClient(client, circuit_breaker)
```

#### 3.2 libs/huleedu_service_libs/http_client/di_providers.py

```python
# BEFORE
from huleedu_service_libs.resilience.resilient_client import make_resilient
return make_resilient(client, breaker)

# AFTER
from huleedu_service_libs.resilience.content_service import ResilientContentServiceClient
return ResilientContentServiceClient(client, breaker)
```

#### 3.3 batch_orchestrator_service/di.py

```python
# BEFORE
from huleedu_service_libs.resilience.resilient_client import make_resilient
return make_resilient(base_client, circuit_breaker)

# AFTER
from huleedu_service_libs.resilience.content_service import ResilientContentServiceClient
return ResilientContentServiceClient(base_client, circuit_breaker)
```

#### 3.4 llm_provider_service/di.py (4 locations)

```python
# BEFORE (all 4 providers)
from huleedu_service_libs.resilience.resilient_client import make_resilient
return make_resilient(base_provider, circuit_breaker)

# AFTER (import from SERVICE'S OWN implementations)
from services.llm_provider_service.implementations.resilient_llm_provider import ResilientLLMProvider
return ResilientLLMProvider(base_provider, circuit_breaker)
```

### Phase 4: Delete Generic Proxy

1. **DELETE** `libs/huleedu_service_libs/src/huleedu_service_libs/resilience/resilient_client.py`
2. **UPDATE** `libs/huleedu_service_libs/src/huleedu_service_libs/resilience/__init__.py`:

   ```python
   # REMOVE
   from .resilient_client import make_resilient, ResilientClientWrapper
   
   # ADD (shared wrappers only - no service-specific imports!)
   from .http_client import ResilientHttpClient
   from .content_service import ResilientContentServiceClient
   # Note: ResilientLLMProvider is NOT exported here - it lives in the service
   ```

### Phase 5: Update Tests

#### 5.1 Rename/Split test_resilient_client.py

```
# FROM
libs/huleedu_service_libs/tests/test_resilient_client.py

# TO
libs/huleedu_service_libs/tests/test_resilient_http_client.py
libs/huleedu_service_libs/tests/test_resilient_content_service.py
libs/huleedu_service_libs/tests/test_resilient_llm_provider.py
```

#### 5.2 Update Test Implementations

```python
# BEFORE
resilient_service = make_resilient(mock_service, circuit_breaker)

# AFTER (example for HTTP client)
resilient_service = ResilientHttpClient(mock_service, circuit_breaker)
```

#### 5.3 Update Integration Tests

- batch_orchestrator_service/tests/integration/test_circuit_breaker_integration.py
- Replace all `make_resilient()` calls with appropriate typed wrappers

### Phase 6: Documentation Updates

Remove `make_resilient` references from:

- `.cursor/rules/020.11-service-libraries-architecture.mdc`
- `.cursor/rules/040-service-implementation-guidelines.mdc`
- `.windsurf/rules/` (parallel copies)

## Acceptance Criteria

### Type Safety

- ✅ ZERO `cast()` usage in resilience modules
- ✅ ZERO `# type: ignore` comments  
- ✅ ZERO `Any` returns from resilient wrappers
- ✅ All functions have complete type annotations

### MyPy Compliance

```bash
# Library check - MUST PASS with zero errors
cd libs/huleedu_service_libs
mypy src/huleedu_service_libs --show-error-codes --config-file pyproject.toml

# Root check - MUST PASS
pdm run typecheck-all
```

### Functional Requirements

- ✅ All existing tests pass with typed wrappers
- ✅ Circuit breaker behavior unchanged
- ✅ Correlation ID and context propagation preserved
- ✅ All services start and run correctly

### Code Quality

- ✅ Each wrapper has clear docstrings
- ✅ Consistent naming: `ResilientXxxClient`, `ResilientXxxProvider`
- ✅ No backwards compatibility code
- ✅ Clean compile-time breaks where `make_resilient` was used

## Validation Commands

```bash
# 1. Type checking
cd libs/huleedu_service_libs
mypy src/huleedu_service_libs --show-error-codes --config-file pyproject.toml

# 2. Root type check
cd /Users/olofs_mba/Documents/Repos/huledu-reboot
pdm run typecheck-all

# 3. Verify no forbidden patterns
grep -r "cast(" libs/huleedu_service_libs/src/huleedu_service_libs/resilience/
grep -r "# type: ignore" libs/huleedu_service_libs/src/huleedu_service_libs/
grep -r "make_resilient" services/  # Should only appear in comments/docs

# 4. Run tests
pdm run test-unit
```

## Implementation Order

1. Fix logging_utils.py Processor import collision
2. Create three typed wrapper modules
3. Update resilience/**init**.py exports
4. Update all DI providers (compile-time breaks expected)
5. Delete resilient_client.py
6. Update and split tests
7. Update documentation
8. Final validation

## Benefits Achieved

1. **Type Safety**: Complete compile-time verification, no runtime surprises
2. **DDD Alignment**: Each bounded context has its own resilient adapter
3. **Maintainability**: Explicit code is easier to understand and debug
4. **Performance**: No dynamic proxy overhead
5. **Developer Experience**: Better IDE support, clearer error messages

## Notes

- This is a BREAKING CHANGE by design - no backwards compatibility
- Compile-time errors are expected and desired when deleting make_resilient
- ResilientKafkaPublisher remains unchanged (already properly typed)
- Streaming methods in LLM providers may need special circuit breaker handling

---
**Task Created By**: Claude (MyPy Compliance Initiative)
**Reviewed By**: User (NO BACKWARDS COMPATIBILITY mandate confirmed)
