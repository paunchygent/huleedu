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
async def mock_http_context_manager(mock_response: AsyncMock) -> Any:
    yield mock_response
```

### 3.3. Protocol and DI Testing Patterns
- Mock protocol-based services using test doubles implementing the same `typing.Protocol`.
- Override Dishka providers in tests to inject mocks/fakes.
- Unit test all protocol implementations for both success and error; integration tests must cover full orchestration flows.

## 4. Execution Rules
- **Command**: `pdm run pytest` (always use PDM)
- **Debug**: `pdm run pytest -s` for print statements
- **FORBIDDEN**: Simplifying tests to make them pass - fix underlying issues

## 5. Type Checking Standards
- **REQUIRED**: Run `pdm run typecheck-all` from repository root
- **FORBIDDEN**: Creating `py.typed` marker files for internal modules
- **REQUIRED**: Add missing type stubs to `pyproject.toml` MyPy external libraries section
- **Pattern**: Use `ignore_missing_imports = true` in MyPy overrides for libraries without stubs

**Root execution is mandatory for**:
- Proper absolute import resolution in monorepo architecture
- Cross-service protocol compliance validation  
- Complete dependency graph type checking

## 6. Anti-Patterns
- **FORBIDDEN**: `try/except pass` blocks hiding model rebuilding failures
- **FORBIDDEN**: Mocking at wrong abstraction levels
- **FORBIDDEN**: Using `AsyncMock()` directly for async context managers


## 7. Common Test Patterns

### 7.1. DI Container Failures (`NoFactoryError`)
- **Symptom**: `dishka.exceptions.NoFactoryError` during test execution.
- **Cause**: A new dependency was added to the application, but not to the test DI container.
- **Fix**: `MUST` add the required [Provider](cci:2://file:///Users/olofs_mba/Documents/Repos/huledu-reboot/services/class_management_service/tests/test_api_integration.py:56:8-76:17) to the `make_async_container()` call in the test fixture.
  ```python
  # services/.../tests/test_api_integration.py
  container = make_async_container(TestProvider(), NewDependencyProvider())

### 7.2. Prometheus Metric Conflicts
- **Symptom**: ValueError: Duplicated timeseries in CollectorRegistry.
- **Cause**: Prometheus's global registry is not cleared between test runs.
- **Fix**: MUST add a pytest fixture with autouse=True to unregister all collectors before each test.
```python
# tests/conftest.py or relevant test file
@pytest.fixture(autouse=True)
def _clear_prometheus_registry():
    collectors = list(REGISTRY._collector_to_names.keys())
    for collector in collectors:
        REGISTRY.unregister(collector)
    yield
```

See [051-pydantic-v2-standards.mdc](mdc:051-pydantic-v2-standards.mdc) Section 8.2 for Pydantic testing patterns.

---
**Fix underlying issues, don't simplify tests.**
===
