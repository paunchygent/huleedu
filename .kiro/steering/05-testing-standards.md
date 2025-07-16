---
inclusion: always
---

# Testing Standards and Patterns

## Test Organization

### Test Directory Structure
```
tests/
├── unit/              # Fast, isolated unit tests
├── integration/       # Tests with external dependencies
├── contract/          # Inter-service contract tests
├── functional/        # End-to-end workflow tests
└── fixtures/          # Shared test data and fixtures
```

### Test Categories and Markers
- `@pytest.mark.unit` - Fast, isolated tests
- `@pytest.mark.integration` - Tests requiring external services
- `@pytest.mark.expensive` - Tests that incur costs (LLM calls)
- `@pytest.mark.slow` - Long-running tests
- `@pytest.mark.e2e` - End-to-end pipeline tests

## Testing Patterns

### Protocol-Based Testing
```python
# Test against protocols, not implementations
async def test_content_storage(content_service: ContentServiceProtocol):
    result = await content_service.store_content("test content")
    assert result.content_id is not None
```

### Dependency Injection in Tests
```python
# Use DI container for test setup
@pytest.fixture
async def content_service():
    container = make_test_container()
    async with container() as request_container:
        yield await request_container.get(ContentServiceProtocol)
```

### Event Testing Patterns
```python
# Test event publishing and consumption
async def test_event_processing():
    event = EssayContentProvisionedV1(
        essay_id="test-123",
        text_storage_id="content-456"
    )
    
    await event_processor.process_event(event)
    
    # Verify side effects
    assert await repository.get_essay("test-123") is not None
```

### Mock External Dependencies
```python
# Mock external services in tests
@pytest.fixture
def mock_llm_service():
    with patch('implementations.llm_service.LLMService') as mock:
        mock.return_value.generate_comparison.return_value = ComparisonResult(
            winner="essay_1",
            confidence=0.85
        )
        yield mock
```

## Test Data Management

### Fixture Patterns
```python
@pytest.fixture
async def sample_essay():
    return Essay(
        id="test-essay-123",
        content="This is a test essay content.",
        language="en",
        metadata={"author": "test-student"}
    )

@pytest.fixture
async def clean_database():
    # Setup clean database state
    yield
    # Cleanup after test
```

### Test Database Patterns
- Use SQLite for fast unit tests
- Use TestContainers for integration tests requiring PostgreSQL
- Ensure test isolation with proper cleanup
- Use transactions for rollback-based cleanup when possible

## Async Testing Standards

### Async Test Configuration
```python
# pytest.ini configuration for async tests
[tool.pytest.ini_options]
asyncio_mode = "auto"
```

### Async Fixture Patterns
```python
@pytest.fixture
async def async_client():
    async with httpx.AsyncClient() as client:
        yield client
```

## Performance and Load Testing

### Performance Test Markers
```python
@pytest.mark.performance
async def test_high_throughput_processing():
    # Test with high load
    pass
```

### Memory and Resource Testing
- Monitor memory usage in long-running tests
- Test resource cleanup and connection pooling
- Verify graceful shutdown behavior