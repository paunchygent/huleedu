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
- **MUST** override Dishka providers in tests to inject mocks for protocol dependencies.
- **Pattern**: Use `make_async_container` with a test `Provider` that binds the protocol to a mock.
- **Example**: `provider.provide(provide(lambda: AsyncMock(spec=MyProtocol), scope=Scope.APP))`

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

## 8. Performance Testing Strategy

### 8.1. Testing Strategy Matrix

| Test Type         | Infrastructure | LLM Provider | Purpose                    | Example Use Case |
|------------------|----------------|--------------|----------------------------|------------------|
| Unit Tests       | Mock          | Mock         | Fast feedback             | Business logic validation |
| Integration      | Real          | Mock         | Infrastructure validation | Database/Queue performance |
| Performance      | Real          | Mock         | Meaningful metrics        | Redis pipeline benchmarks |
| E2E             | Real          | Real         | Full system validation    | End-to-end workflows |

### 8.2. Infrastructure vs Mock Testing Guidelines

#### Real Infrastructure Testing
- **WHEN**: Testing infrastructure performance, reliability, and resource usage
- **COMPONENTS**: Use real Redis, Kafka, PostgreSQL via testcontainers
- **BENEFITS**: Realistic performance metrics, actual network latency, real resource consumption
- **EXAMPLE**: Redis queue performance with 0.3ms operation times

#### Mock LLM Provider Testing
- **WHEN**: Performance testing that needs meaningful data without API costs
- **IMPLEMENTATION**: Use `MockProviderImpl` with `performance_mode=True`
- **BENEFITS**: Avoids API costs while providing realistic response patterns
- **PATTERN**: Mock errors disabled in performance mode for consistent results

### 8.3. Performance Testing Patterns

#### Testcontainer Configuration
```python
@pytest.fixture(scope="class")
def redis_container() -> Generator[RedisContainer, None, None]:
    """Provide a Redis container for testing."""
    with RedisContainer("redis:7-alpine") as container:
        yield container

@pytest.fixture(scope="class")
def kafka_container() -> Generator[KafkaContainer, None, None]:
    """Provide a Kafka container for testing."""
    with KafkaContainer("confluentinc/cp-kafka:7.4.0") as container:
        yield container
```

#### Performance-Optimized Mock Providers
```python
@provide(scope=Scope.APP)
async def provide_llm_provider_map(self, settings: Settings) -> Dict[LLMProviderType, LLMProviderProtocol]:
    """Provide performance-optimized mock providers."""
    mock_provider = MockProviderImpl(
        settings=settings, 
        seed=42, 
        performance_mode=True  # Disables error simulation
    )
    return {
        LLMProviderType.MOCK: mock_provider,
        LLMProviderType.ANTHROPIC: mock_provider,
        # ... other providers
    }
```

#### DI Container Cleanup Pattern
```python
@pytest.fixture
async def infrastructure_di_container(settings: Settings) -> AsyncGenerator[Any, None]:
    """DI container with real infrastructure cleanup."""
    container = make_async_container(TestProvider(settings))
    
    try:
        yield container
    finally:
        # CRITICAL: Clean up all infrastructure components
        async with container() as request_container:
            for client_type in [QueueRedisClientProtocol, RedisClientProtocol]:
                try:
                    client = await request_container.get(client_type)
                    if hasattr(client, 'stop'):
                        await client.stop()
                except Exception as e:
                    print(f"⚠ Failed to stop {client_type.__name__}: {e}")
```

### 8.4. Performance Benchmarking Standards

#### Realistic Performance Targets
- **Redis Operations**: < 0.1s per operation (achieved: 0.3ms)
- **Queue Throughput**: < 0.2s per retrieval  
- **Batch Operations**: < 0.15s per request
- **Concurrent Operations**: < 0.2s average response time
- **E2E Pipeline**: P95 < 5.0s, 90% success rate

#### Performance Metrics Collection
```python
class PerformanceMetrics:
    """Collects and analyzes performance metrics."""
    
    def add_measurement(self, response_time: float, status_code: int, error: Optional[str] = None) -> None:
        """Add a performance measurement."""
        
    def get_statistics(self) -> Dict[str, Any]:
        """Get comprehensive performance statistics including P95, P99, error rates."""
```

### 8.5. Test Isolation and Resource Management

#### Queue Cleanup Between Tests
```python
@pytest.fixture(autouse=True)
async def clean_redis_queue(redis_container: RedisContainer) -> None:
    """Clean Redis queue between tests for isolation."""
    client = redis_container.get_client()
    await client.flushdb()
    yield
```

#### Resource Cleanup Patterns
- **MUST** use `try/finally` blocks for resource cleanup
- **PATTERN**: Print warnings for cleanup failures (don't fail tests)
- **SCOPE**: Use appropriate fixture scopes (`class` for containers, `function` for DI)

### 8.6. Performance Test Categories

#### Load Testing
- **Pattern**: Sustained request rates over time
- **Metrics**: Requests per second, P95/P99 response times
- **Example**: 2 req/s for 15 seconds with real infrastructure

#### Stress Testing  
- **Pattern**: Concurrent operations with varying load
- **Metrics**: Success rates, resource utilization
- **Example**: 25 concurrent Redis operations

#### Endurance Testing
- **Pattern**: Mixed workload types over extended periods
- **Metrics**: Performance degradation over time
- **Example**: Mixed quick/detailed/batch workloads

### 8.7. Bulk Operation Testing Patterns

#### Concurrent Data Generation
```python
class BulkTestDataGenerator:
    """Generate test data with global uniqueness for concurrent operations."""
    
    @staticmethod
    def generate_unique_requests(count: int) -> List[RequestModel]:
        """Generate requests with UUID suffixes for concurrent safety."""
        unique_suffix = str(uuid.uuid4()).replace('-', '')[:8]
        # Pattern ensures no conflicts across concurrent test execution
```

#### Bulk Workflow Testing Structure
- **Single Entity Bulk**: Test realistic batch sizes per operation
- **Multi-Entity Workflows**: Multiple related entities in sequence
- **Concurrent Bulk Operations**: Parallel bulk operations across users
- **Constraint Validation**: Database integrity under bulk load
- **Memory Efficiency**: Large batch memory patterns

#### Bulk Performance Test Architecture
```python
# Bulk performance test structure
tests/performance/
├── conftest.py                    # Bulk operation fixtures
├── test_single_bulk_*.py         # Individual bulk operation patterns  
├── test_concurrent_bulk_*.py     # Concurrent bulk operation patterns
├── test_database_bulk_*.py       # Database bulk operation patterns
```

---
**Fix underlying issues, don't simplify tests.**
===
