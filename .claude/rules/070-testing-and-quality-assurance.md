---
id: "070-testing-and-quality-assurance"
type: "testing"
created: 2025-05-25
last_updated: 2025-11-17
scope: "all"
child_rules: ["070.1-performance-testing-methodology"]
---

# 070: Testing and Quality Assurance
## 1. Testing Pyramid
- **Unit Tests**: Individual components in isolation (high coverage)
- **Contract Tests**: **CRITICAL** - Verify Pydantic contracts between services
- **Integration Tests**: Limited scope component interactions
- **E2E Tests**: Major user flows (use sparingly)

## 2. Core Rules
- **Runner (Standard)**: `pdm run pytest-root <path-or-nodeid>`
- **Anywhere (Alias)**: `pyp <path-or-nodeid>` after `source scripts/dev-aliases.sh`
- **Force Root Project**: `pdmr pytest-root <path-or-nodeid>` from any dir
- **Naming**: `test_*.py` files, `test_*` functions
- **Isolation**: Tests must be independent
- **Debug**: add `-s` to the runner, e.g. `pdm run pytest-root -s <path>`
- **FORBIDDEN**: Mixing abstraction levels in same test
- **FORBIDDEN**: Simplifying tests to make them pass - fix underlying issues
- **Timeouts**: Individual test timeouts MUST be ≤ 60 seconds. For event-driven flows, default to 30 seconds and synchronize via Kafka events (no polling). If a test needs more, split it or improve determinism instead of increasing the timeout.

## 3. DI/Protocol Testing Patterns
- **MUST** override Dishka providers in tests to inject mocks for protocol dependencies
- **Pattern**: Use `make_async_container` with test `Provider` that binds protocol to mock
- **Example**: `provider.provide(provide(lambda: AsyncMock(spec=MyProtocol), scope=Scope.APP))`

```python
# DI Container test pattern
container = make_async_container(TestProvider(), NewDependencyProvider())

# Async context manager mocking
@asynccontextmanager
async def mock_http_context_manager(mock_response: AsyncMock) -> Any:
    yield mock_response
```

## 4. Type Checking Standards
- **REQUIRED**: Run `pdm run typecheck-all` from repository root
- **FORBIDDEN**: Creating `py.typed` marker files for internal modules
- **REQUIRED**: Add missing type stubs to `pyproject.toml` MyPy external libraries section
- **Pattern**: Use `ignore_missing_imports = true` in MyPy overrides for libraries without stubs

**Root execution mandatory for**:
- Proper absolute import resolution in monorepo architecture
- Cross-service protocol compliance validation  
- Complete dependency graph type checking

## 5. Common Failure Patterns

### 5.1. DI Container Failures (`NoFactoryError`)
- **Cause**: New dependency added to application, not to test DI container
- **Fix**: Add required `Provider` to `make_async_container()` call in test fixture

### 5.2. Prometheus Metric Conflicts
- **Symptom**: `ValueError: Duplicated timeseries in CollectorRegistry`
- **Fix**: Add pytest fixture with `autouse=True` to unregister all collectors before each test
```python
@pytest.fixture(autouse=True)
def _clear_prometheus_registry():
    collectors = list(REGISTRY._collector_to_names.keys())
    for collector in collectors:
        REGISTRY.unregister(collector)
    yield
```

## 6. Database Configuration Standards

### 6.1. DATABASE_URL Pattern Requirements
- **MANDATORY**: All database configuration **MUST** use UPPERCASE `DATABASE_URL` pattern
- **Environment Variables**: `DATABASE_URL`, `SERVICE_DATABASE_URL`, `DATABASE_URL_CJ`
- **Settings Access**: `settings.DATABASE_URL` (not `settings.database_url`)

### 6.2. Test Database Configuration
```python
# ✅ CORRECT - Test settings with UPPERCASE DATABASE_URL
class TestSettings(Settings):
    def __init__(self, database_url: str) -> None:
        super().__init__()
        object.__setattr__(self, '_database_url', database_url)

    @property  
    def DATABASE_URL(self) -> str:
        return object.__getattribute__(self, '_database_url')
```

### 6.3. Anti-Patterns
```python
# ❌ FORBIDDEN
settings.database_url  # Wrong for environment variables
create_async_engine(DATABASE_URL)  # Wrong - missing settings.
Database_URL  # Wrong - use DATABASE_URL

# ✅ CORRECT
create_async_engine(settings.DATABASE_URL)
os.environ["SERVICE_DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
```

## 7. Anti-Patterns
- **FORBIDDEN**: `try/except pass` blocks hiding model rebuilding failures
- **FORBIDDEN**: Mocking at wrong abstraction levels
- **FORBIDDEN**: Using `AsyncMock()` directly for async context managers

---
**Fix underlying issues, don't simplify tests.**
