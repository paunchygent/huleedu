---
trigger: model_decision
description: "Testing and QA standards. Follow when writing, maintaining, or reviewing tests to ensure comprehensive coverage and maintainable test suites."
---

---

description:
globs:
alwaysApply: true
---

# 070: Testing and Quality Assurance

## 1. Testing Pyramid

- **Unit Tests**: Individual components in isolation (high coverage)
- **Contract Tests**: **CRITICAL** - Verify Pydantic contracts between services
- **Integration Tests**: Limited scope component interactions
- **E2E Tests**: Major user flows (use sparingly)

## 2. Core Rules

- **Runner**: `pdm run pytest`
- **Naming**: `test_*.py` files, `test_*` functions
- **Isolation**: Tests must be independent
- **FORBIDDEN**: Mixing abstraction levels in same test

## 3. Testing Patterns

### 3.1. Dependency Injection

```python
async def process_function(
    core_data, external_dependencies,
    injectable_func_1: Callable, injectable_func_2: Callable,
) -> bool:
```

### 3.2. Async Context Manager Mocking

```python
@asynccontextmanager
async def fake_aiokafka_consumer(records: list[bytes]):
    yield FakeConsumer(records)  # implements aiokafka-like API
```

### 3.3. Protocol and DI Testing Patterns

- Override Dishka providers in tests to inject mocks/fakes.
- Example override helper:

```python
from dishka import make_async_container, Provider, Scope, provide

class TestOverrides(Provider):
    @provide(scope=Scope.APP)
    def content_client(self) -> ContentClientProtocol:  # mock impl
        return FakeContentClient()

container = make_async_container(ServiceProvider(), TestOverrides())
```

- When testing Quart routes:

```python
test_app = create_app()  # factory returns Quart app
QuartDishka(app=test_app, container=container)  # inject mocks
```

- Verifying Prometheus metrics in unit tests:

```python
import prometheus_client

+def test_metric_increment():
    registry = prometheus_client.CollectorRegistry()
    counter = Counter("pairs_total", "desc", registry=registry)
    counter.inc()
    sample = registry.get_sample_value("pairs_total")
    assert sample == 1
```

### 3.3. Protocol and DI Testing Patterns

- Mock protocol-based services using test doubles implementing the same `typing.Protocol`.
- Override Dishka providers in tests to inject mocks/fakes.
- Unit test all protocol implementations for both success and error; integration tests must cover full orchestration flows.

```python
@asynccontextmanager
async def mock_http_context_manager(mock_response: AsyncMock) -> Any:
    yield mock_response
```

## 4. Execution Rules

- **Command**: `pdm run pytest` (always use PDM)
- **Debug**: `pdm run pytest -s` for print statements
- **FORBIDDEN**: Simplifying tests to make them pass - fix underlying issues

## 5. Type Checking Standards

- **FORBIDDEN**: Creating `py.typed` marker files for internal modules
- **REQUIRED**: Add missing type stubs to `pyproject.toml` MyPy external libraries section
- **Pattern**: Use `ignore_missing_imports = true` in MyPy overrides for libraries without stubs

## 5. Anti-Patterns

- **FORBIDDEN**: `try/except pass` blocks hiding model rebuilding failures
- **FORBIDDEN**: Mocking at wrong abstraction levels
- **FORBIDDEN**: Using `AsyncMock()` directly for async context managers

See [051-pydantic-v2-standards.mdc](mdc:051-pydantic-v2-standards.mdc) Section 8.2 for Pydantic testing patterns.

---

**Fix underlying issues, don't simplify tests.**
===
