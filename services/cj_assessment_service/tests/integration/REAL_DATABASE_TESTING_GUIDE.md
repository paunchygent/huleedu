# Real Database Integration Testing Guide

## Overview

This guide demonstrates the proper approach to integration testing in the CJ Assessment Service, replacing over-mocked internal components with real database implementations while maintaining clear boundaries between what should be real and what should be mocked.

## Problem Statement

The original integration tests suffered from **over-mocking** of internal components:

### ❌ OVER-MOCKED (Problems)
- Per-aggregate repository protocols - Internal database repositories
- Database sessions - SQLAlchemy operations
- Query results - Database query chains
- Entity objects - Database records as `MagicMock()`

### ✅ CORRECTLY MOCKED (Keep These)
- `ContentClientProtocol` - External HTTP service
- `LLMInteractionProtocol` - External LLM providers  
- `CJEventPublisherProtocol` - Kafka event publishing

## Solution Architecture

### Database Strategy
- **Primary**: SQLite in-memory for speed and isolation
- **Secondary**: PostgreSQL via testcontainers for production parity (marked `@pytest.mark.expensive`)

### Test Isolation
- Transaction-based isolation with automatic rollback
- Each test gets a clean database state
- No data leakage between tests

### Repository Implementation
- Real PostgresDataAccess implementation (provides all aggregate repository protocols)
- Real SQLAlchemy queries and operations
- Real database transactions and constraints

## Implementation Files

### Core Infrastructure
- `tests/fixtures/database_fixtures.py` - Database engines, sessions, and repository fixtures
- `tests/fixtures/test_models_db.py` - SQLite-compatible database models
- `tests/fixtures/test_repository_impl.py` - Test repository implementation
- `tests/integration/test_real_database_integration.py` - Example integration tests

### Key Fixtures

#### Database Engines
```python
@pytest.fixture
async def sqlite_engine() -> AsyncGenerator[AsyncEngine, None]:
    """Create SQLite in-memory engine for fast integration tests."""
    
@pytest.fixture
async def postgres_engine(postgres_container: PostgresContainer) -> AsyncGenerator[AsyncEngine, None]:
    """Create PostgreSQL engine for production-parity tests."""
```

#### Database Sessions
```python  
@pytest.fixture
async def db_session(sqlite_engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    """Create isolated database session with automatic rollback."""
    async with session_maker() as session:
        async with session.begin():
            yield session
            # Rollback happens automatically when exiting the context
```

#### Repository Implementations
```python
@pytest.fixture
async def postgres_data_access(
    sqlite_engine: AsyncEngine, test_settings: Settings
) -> AsyncGenerator[PostgresDataAccess, None]:
    """Create real PostgresDataAccess implementation with SQLite backend.

    PostgresDataAccess implements all per-aggregate repository protocols:
    - SessionProviderProtocol
    - CJBatchRepositoryProtocol
    - CJEssayRepositoryProtocol
    - CJComparisonRepositoryProtocol
    - AnchorRepositoryProtocol
    - AssessmentInstructionRepositoryProtocol
    - GradeProjectionRepositoryProtocol
    """
```

#### External Service Mocks
```python
@pytest.fixture
def mock_content_client() -> AsyncMock:
    """Create mock content client for external service."""
    # Uses correlation_id for deterministic content selection
    # Provides realistic essay content based on storage_id
```

## Test Patterns

### 1. Database Isolation Testing
```python
async def test_database_isolation_between_tests(
    self,
    postgres_data_access: PostgresDataAccess,
    db_verification_helpers,
) -> None:
    """Test that database transactions are properly isolated between tests."""
    async with postgres_data_access.session() as session:
        # Verify clean state
        assert await db_verification_helpers.verify_no_data_leakage(session)
        
        # Create test data
        batch = await postgres_data_access.create_new_cj_batch(...)

        # Verify creation
        assert await db_verification_helpers.verify_batch_exists(session, batch.id)

    # Transaction is automatically rolled back
```

### 2. Real Database Operations
```python
async def test_full_batch_lifecycle_with_real_database(
    self,
    postgres_data_access: PostgresDataAccess,
    mock_content_client: ContentClientProtocol,
    mock_event_publisher: CJEventPublisherProtocol,
    mock_llm_interaction: LLMInteractionProtocol,
    test_settings: Settings,
    db_verification_helpers,
) -> None:
    """Test complete batch lifecycle with real database operations."""
    # Process actual event with real database
    result = await process_single_message(
        kafka_msg,
        postgres_data_access,  # REAL database operations
        mock_content_client,  # MOCKED external service
        mock_event_publisher,  # MOCKED external service
        mock_llm_interaction,  # MOCKED external service
        test_settings,
    )

    # Verify real database state
    async with postgres_data_access.session() as session:
        batches = await postgres_data_access.get_essays_for_cj_batch(session, 1)
        assert len(batches) == essay_count
```

### 3. Production Parity Testing
```python
@pytest.mark.expensive
async def test_real_database_operations_with_postgresql(
    self,
    postgres_data_access_real_db: PostgresDataAccess,
    db_verification_helpers,
) -> None:
    """Test with PostgreSQL for production parity.

    Uses PostgresDataAccess with real PostgreSQL testcontainer backend.
    """
    # Uses testcontainers PostgreSQL instance
    # Tests PostgreSQL-specific features
    # Validates production database compatibility
```

## Benefits of This Approach

### 1. True Integration Testing
- **Real Database Operations**: Actual SQLAlchemy queries and transactions
- **Real Data Constraints**: Database foreign keys, constraints, and validations
- **Real Performance**: Actual database query performance characteristics

### 2. Proper Test Isolation
- **Clean State**: Each test starts with an empty database
- **Transaction Rollback**: Automatic cleanup without manual data deletion
- **No Data Leakage**: Tests cannot interfere with each other

### 3. Clear Boundaries
- **Mock External Services**: Services outside our control
- **Real Internal Components**: Components we own and control
- **Realistic Mocks**: External mocks provide realistic data patterns

### 4. Speed and Reliability
- **SQLite Speed**: In-memory database for fast test execution
- **PostgreSQL Accuracy**: Production parity when needed
- **Deterministic Results**: Consistent test outcomes

## Usage Guidelines

### When to Use SQLite (Default)
- Fast integration tests
- CI/CD pipeline execution
- Development testing
- Most integration test scenarios

### When to Use PostgreSQL (Expensive)
- Production parity validation
- PostgreSQL-specific feature testing
- Final validation before deployment
- Complex database interaction testing

### Mock Design Principles

#### External Services (Always Mock)
```python
@pytest.fixture
def mock_content_client() -> AsyncMock:
    """External HTTP service - always mock."""
    # Provides realistic responses
    # Uses correlation_id for deterministic behavior
    # Simulates external service patterns
```

#### Internal Components (Use Real Implementation)
```python
@pytest.fixture
async def postgres_data_access(
    sqlite_engine: AsyncEngine, test_settings: Settings
) -> AsyncGenerator[PostgresDataAccess, None]:
    """Internal repository - use real PostgresDataAccess implementation.

    Provides all per-aggregate repository protocols in one fixture.
    """
    # Real database operations
    # Real transaction handling
    # Real constraint enforcement
```

## Migration from Over-Mocked Tests

### 1. Identify Over-Mocking
- Look for `AsyncMock(spec=<repository protocol>)` in place of real repositories
- Find complex mock chains like `mock_session.execute.return_value.scalar_one_or_none`
- Spot entity objects created as `MagicMock()`

### 2. Replace with Real Implementation
- Replace mocked repositories with `postgres_data_access` fixture
- Use real database sessions from `db_session` fixture or `postgres_data_access.session()`
- Create real database records with repository methods

### 3. Update Test Logic
- Remove mock configuration code
- Use real database verification helpers
- Assert against actual database state

### 4. Maintain External Mocks
- Keep external service mocks unchanged
- Ensure external mocks provide realistic data
- Use parameters meaningfully in mock implementations

## Performance Characteristics

### SQLite Integration Tests
- **Setup Time**: ~0.01s per test
- **Execution Time**: ~0.01s per test
- **Memory Usage**: Minimal (in-memory)
- **Isolation**: Perfect (transaction rollback)

### PostgreSQL Integration Tests
- **Setup Time**: ~2s per test (container startup)
- **Execution Time**: ~0.1s per test
- **Memory Usage**: Higher (Docker container)
- **Isolation**: Good (transaction rollback)

## Best Practices

### 1. Test Organization
- Group related tests in test classes
- Use descriptive test names that indicate the testing approach
- Separate fast (SQLite) from expensive (PostgreSQL) tests

### 2. Fixture Usage
- Prefer `postgres_data_access` over mocked per-aggregate repositories
- Use `db_verification_helpers` for database state assertions
- Apply `@pytest.mark.expensive` for PostgreSQL tests

### 3. Test Data Management
- Use repository methods to create test data
- Rely on transaction rollback for cleanup
- Verify clean state in isolation tests

### 4. Mock Configuration
- Make external service mocks realistic
- Use correlation IDs for deterministic behavior
- Provide meaningful responses based on input parameters

## Common Pitfalls to Avoid

### 1. Don't Over-Mock Internal Components
```python
# ❌ BAD: Mocking internal repositories (deprecated pattern)
repo = AsyncMock(spec=CJBatchRepositoryProtocol)
repo.get_cj_batch_upload.return_value = mock_result

# ❌ ALSO BAD: Mocking per-aggregate repositories
mock_batch_repo = AsyncMock(spec=CJBatchRepositoryProtocol)
mock_essay_repo = AsyncMock(spec=CJEssayRepositoryProtocol)

# ✅ GOOD: Using real PostgresDataAccess implementation
async with postgres_data_access.session() as session:
    result = await postgres_data_access.get_essays_for_cj_batch(session, batch_id)
```

### 2. Don't Ignore Test Isolation
```python
# ❌ BAD: Manual cleanup that can fail
await session.execute(delete(CJBatchUpload))
await session.commit()

# ✅ GOOD: Transaction rollback for isolation
async with session.begin():
    yield session
    # Automatic rollback
```

### 3. Don't Make External Services Too Simple
```python
# ❌ BAD: Unrealistic mock
mock_content_client.fetch_content.return_value = "essay content"

# ✅ GOOD: Realistic mock with variation
async def fetch_content(storage_id: str, correlation_id: Any) -> str:
    # Use correlation_id for deterministic content selection
    content_seed = hash(f"{storage_id}-{correlation_id}") % len(essay_templates)
    return essay_templates[content_seed]
```

## Summary

This approach provides:
- **True Integration Testing**: Real database operations with proper isolation
- **Clear Boundaries**: Mock external services, use real internal components
- **Fast Execution**: SQLite for speed, PostgreSQL for accuracy
- **Reliable Results**: Deterministic test outcomes with proper cleanup
- **Team Adoption**: Reusable patterns and fixtures for consistent testing

The key insight is that integration tests should test integration - the real interactions between components we control, while mocking only the external boundaries we don't control.
