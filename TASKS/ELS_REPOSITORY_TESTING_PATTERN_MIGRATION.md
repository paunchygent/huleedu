# Essay Lifecycle Service Repository Testing Pattern Migration - Revised

## Current Status

| Phase | Status | Details |
|-------|--------|---------|
| Phase 0: Domain Model Extraction | ✅ COMPLETED | `EssayState` extracted to `domain_models.py`, all imports updated |
| Phase 1: MockEssayRepository | 🔄 PENDING | Ready for implementation |
| Phase 2: Test Migration | 🔲 NOT STARTED | Awaiting mock repository |
| Phase 3: SQLite Removal | 🔲 NOT STARTED | Awaiting test migration |
| Phase 4: Validation | 🔲 NOT STARTED | Final phase |

## Executive Summary

**Objective**: Migrate Essay Lifecycle Service from SQLite-based testing to the proven three-tier repository pattern established in Batch Orchestrator Service.

**Strategy**: Clean refactor with no backwards compatibility - complete elimination of SQLite implementation in favor of:
- **Mock Repository**: Fast, in-memory unit tests with comprehensive constraint simulation and atomic operation support
- **PostgreSQL Repository**: Production implementation for integration tests and production
- **Docker Environment**: E2E testing with full service stack

**Impact**: 10-50x faster unit test execution, improved concurrency testing, elimination of file-system dependencies, and architectural consistency across services.

**Critical Improvements in Revised Plan**:
- Domain model extraction to eliminate SQLite dependencies
- Enhanced constraint simulation matching PostgreSQL behavior
- Gradual test migration with helper utilities
- Complete session management documentation
- Phase status mapping implementation

## Current State Analysis

### Pre-existing Architectural Smell

The fact that `EssayState` (the domain model) currently resides in `state_store.py` (SQLite infrastructure) reveals a **violation of DDD principles**:

1. **Domain-Infrastructure Coupling**: Domain entities should never depend on infrastructure
2. **Inverted Dependencies**: The domain model is owned by a specific storage implementation
3. **Testing Impedance**: Can't test domain logic without database dependencies

This suggests the original implementation rushed to add SQLite support without proper architectural boundaries. The correct structure should have been:
```
domain/
├── models.py           # EssayState lives here (pure domain)
infrastructure/
├── sqlite/            # SQLite-specific implementation
└── postgresql/        # PostgreSQL-specific implementation
```

This migration provides an opportunity to correct this architectural debt.

### Problems with Current SQLite Approach
- **Performance**: Slow I/O operations in unit tests
- **Reliability**: File-system dependencies create test brittleness
- **Concurrency**: Limited atomic operation testing capabilities
- **Maintenance**: Additional complexity with dual database support
- **CI/CD**: Slower build times due to SQLite I/O overhead

### Files Currently Using SQLite
```
services/essay_lifecycle_service/
├── state_store.py                           # SQLiteEssayStateStore implementation
├── implementations/
│   ├── database_schema_manager.py           # SQLite schema management
│   ├── essay_crud_operations.py             # SQLite CRUD operations
│   └── essay_state_model.py                 # Shared state model
├── tests/unit/
│   ├── test_state_store_impl.py             # SQLite unit tests
│   └── test_repository_performance_optimizations.py  # SQLite performance tests
└── tests/
    └── test_essay_repository_integration.py # Mixed SQLite/PostgreSQL tests
```

## Migration Plan

### Phase 0: Domain Model Extraction (Week 0.5) - COMPLETED ✓

#### 0.1 Extract EssayState Domain Model
**File**: `services/essay_lifecycle_service/domain_models.py`

**Key Decision**: Use Pydantic models instead of dataclasses to maintain consistency with existing codebase patterns.

```python
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from common_core.domain_enums import ContentType
from common_core.status_enums import EssayStatus
from pydantic import BaseModel, ConfigDict, Field


class EssayState(BaseModel):
    """Domain model for essay state, independent of storage implementation."""
    
    model_config = ConfigDict(
        json_encoders={
            datetime: lambda v: v.isoformat(),
            ContentType: lambda v: v.value,
            EssayStatus: lambda v: v.value,
        },
        validate_assignment=True,
    )
    
    essay_id: str
    batch_id: str | None = None
    current_status: EssayStatus
    processing_metadata: dict[str, Any] = Field(default_factory=dict)
    timeline: dict[str, datetime] = Field(default_factory=dict)
    storage_references: dict[ContentType, str] = Field(default_factory=dict)
    text_storage_id: str | None = None
    student_id: str | None = None
    association_confirmed_at: datetime | None = None
    association_method: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    
    def update_status(self, new_status: EssayStatus, metadata: dict[str, Any]) -> None:
        """Update status with timeline tracking."""
        self.current_status = new_status
        self.timeline[new_status.value] = datetime.now(UTC)
        self.processing_metadata.update(metadata)
        self.updated_at = datetime.now(UTC)
```

#### 0.2 Import Dependency Updates - COMPLETED ✓
**Files Updated**:
- `implementations/essay_repository_postgres_impl.py`: Changed from `state_store` import to `domain_models`
- `state_store.py`: Updated to import from `domain_models`
- `implementations/essay_crud_operations.py`: Updated to import from `domain_models`
- `tests/unit/test_state_store_impl.py`: Updated imports and fixed type issues
- `tests/unit/test_repository_performance_optimizations.py`: Updated imports

**Architectural Note**: Following DDD principles, the repository implementations import the concrete domain model for instantiation. This is acceptable as infrastructure can depend on domain, but not vice versa.

### Phase 1: Implement MockEssayRepository (Week 1)

#### 1.1 Create Enhanced Mock Implementation
**File**: `services/essay_lifecycle_service/implementations/mock_essay_repository.py`

**Requirements**:
- Full `EssayRepositoryProtocol` compliance with all 20+ methods
- Comprehensive constraint simulation matching PostgreSQL
- Enhanced atomic operation support
- Production-like behavior patterns
- Proper session parameter handling

**Important Implementation Notes**:
1. Import the concrete `EssayState` from `domain_models.py` for instantiation
2. Use `_ = session` pattern to acknowledge unused session parameters
3. Copy phase status mappings exactly from PostgreSQL implementation
4. Simulate database constraints using internal data structures

**Complete Implementation Structure**:

```python
from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from common_core.domain_enums import ContentType
from common_core.status_enums import EssayStatus
from sqlalchemy.ext.asyncio import AsyncSession

from services.essay_lifecycle_service.domain_models import EssayState
from services.essay_lifecycle_service.protocols import EssayRepositoryProtocol


class MockEssayRepository(EssayRepositoryProtocol):
    """Mock implementation with full PostgreSQL behavior simulation."""
    
    # Phase status mapping - MUST match PostgreSQL exactly
    PHASE_STATUS_MAPPING = {
        "spellcheck": [
            EssayStatus.AWAITING_SPELLCHECK,
            EssayStatus.SPELLCHECKING_IN_PROGRESS,
            EssayStatus.SPELLCHECKED_SUCCESS,
            EssayStatus.SPELLCHECK_FAILED,
        ],
        "cj_assessment": [
            EssayStatus.AWAITING_CJ_ASSESSMENT,
            EssayStatus.CJ_ASSESSMENT_IN_PROGRESS,
            EssayStatus.CJ_ASSESSMENT_SUCCESS,
            EssayStatus.CJ_ASSESSMENT_FAILED,
        ],
        "nlp": [
            EssayStatus.AWAITING_NLP,
            EssayStatus.NLP_IN_PROGRESS,
            EssayStatus.NLP_SUCCESS,
            EssayStatus.NLP_FAILED,
        ],
        "ai_feedback": [
            EssayStatus.AWAITING_AI_FEEDBACK,
            EssayStatus.AI_FEEDBACK_IN_PROGRESS,
            EssayStatus.AI_FEEDBACK_SUCCESS,
            EssayStatus.AI_FEEDBACK_FAILED,
        ],
        "student_matching": [
            EssayStatus.AWAITING_STUDENT_MATCHING,
            EssayStatus.STUDENT_MATCHING_IN_PROGRESS,
            EssayStatus.STUDENT_MATCHED,
            EssayStatus.STUDENT_MATCHING_FAILED,
        ],
    }
    
    def __init__(self) -> None:
        # Core storage
        self.essays: dict[str, EssayState] = {}
        
        # Constraint simulation (mimics PostgreSQL unique indexes)
        self._unique_constraints: dict[tuple[str, str], str] = {}  # (batch_id, text_storage_id) -> essay_id
        
        # Atomicity simulation
        self._locks: dict[str, asyncio.Lock] = {}
        self._global_lock = asyncio.Lock()  # For operations affecting multiple entities
        
        # Failure simulation
        self._simulate_failures: dict[str, bool] = {}
        
        # Session factory mock (returns None as we don't use real sessions)
        self._session_factory = None
    
    def _get_lock(self, key: str) -> asyncio.Lock:
        """Get or create a lock for a specific resource (simulates row-level locking)."""
        if key not in self._locks:
            self._locks[key] = asyncio.Lock()
        return self._locks[key]
    
    async def get_essay_state(self, essay_id: str) -> EssayState | None:
        """Retrieve essay state by ID."""
        return self.essays.get(essay_id)
    
    async def update_essay_state(
        self,
        essay_id: str,
        new_status: EssayStatus,
        metadata: dict[str, Any],
        session: AsyncSession | None = None,
        storage_reference: tuple[ContentType, str] | None = None,
        correlation_id: UUID | None = None,
    ) -> None:
        """Update essay state with new status and metadata.
        
        Note: Mock implementation ignores session parameter as it uses in-memory storage.
        """
        _ = session  # Explicitly ignore for protocol compliance
        
        async with self._get_lock(essay_id):
            essay = self.essays.get(essay_id)
            if not essay:
                raise ValueError(f"Essay {essay_id} not found")
            
            # Update using domain model method
            essay.update_status(new_status, metadata)
            
            if storage_reference:
                content_type, storage_id = storage_reference
                essay.storage_references[content_type] = storage_id
    
    async def create_essay_state_with_content_idempotency(
        self,
        batch_id: str,
        text_storage_id: str,
        essay_data: dict[str, Any],
        correlation_id: UUID,
        session: AsyncSession | None = None,
    ) -> tuple[bool, str | None]:
        """Create essay state with atomic idempotency check.
        
        Simulates PostgreSQL's partial unique index on (batch_id, text_storage_id).
        """
        _ = session  # Explicitly ignore for protocol compliance
        
        constraint_key = (batch_id, text_storage_id) if text_storage_id else None
        
        # First check without lock (fast path)
        if constraint_key and constraint_key in self._unique_constraints:
            return (False, self._unique_constraints[constraint_key])
        
        # Atomic creation with constraint registration
        async with self._get_lock(f"{batch_id}:{text_storage_id}"):
            # Double-check inside lock (prevents race conditions)
            if constraint_key and constraint_key in self._unique_constraints:
                return (False, self._unique_constraints[constraint_key])
            
            # Create essay
            essay_id = essay_data.get("internal_essay_id", str(uuid4()))
            
            essay = EssayState(
                essay_id=essay_id,
                batch_id=batch_id,
                current_status=EssayStatus(essay_data.get("initial_status", EssayStatus.UPLOADED.value)),
                text_storage_id=text_storage_id,
                processing_metadata={
                    "original_file_name": essay_data.get("original_file_name", ""),
                    "file_size_bytes": essay_data.get("file_size", 0),
                    "content_md5_hash": essay_data.get("content_hash", ""),
                }
            )
            
            # Store essay
            self.essays[essay_id] = essay
            
            # Register constraint
            if constraint_key:
                self._unique_constraints[constraint_key] = essay_id
            
            return (True, essay_id)
    
    async def list_essays_by_batch_and_phase(
        self, batch_id: str, phase_name: str, session: AsyncSession | None = None
    ) -> list[EssayState]:
        """List essays matching batch and phase criteria.
        
        Must match PostgreSQL's phase logic exactly.
        """
        _ = session  # Explicitly ignore for protocol compliance
        
        phase_statuses = self.PHASE_STATUS_MAPPING.get(phase_name, [])
        
        return [
            essay for essay in self.essays.values()
            if essay.batch_id == batch_id 
            and essay.current_status in phase_statuses
        ]
    
    def get_session_factory(self) -> Any:
        """Get the session factory for transaction management.
        
        Returns None for mock implementation.
        """
        return self._session_factory
    
    # ... implement remaining 15+ protocol methods ...
```

#### 1.2 Test Data Builder Pattern
**File**: `services/essay_lifecycle_service/tests/utils/test_data_builders.py`

```python
from typing import Any
from uuid import uuid4

from services.essay_lifecycle_service.protocols import EssayRepositoryProtocol
from services.essay_lifecycle_service.domain_models import EssayState
from common_core.status_enums import EssayStatus

class EssayTestDataBuilder:
    """Builder pattern for creating test scenarios consistently."""
    
    @staticmethod
    async def create_batch_with_phase_distribution(
        repository: EssayRepositoryProtocol,
        batch_id: str,
        phase_distributions: dict[str, int]
    ) -> list[EssayState]:
        """Create essays with specific phase distributions for testing.
        
        Example:
            phase_distributions = {
                "spellcheck": 3,  # 3 essays in spellcheck phase
                "cj_assessment": 2,  # 2 essays in CJ assessment
            }
        """
        essays = []
        
        for phase_name, count in phase_distributions.items():
            # Get valid statuses for this phase
            statuses = MockEssayRepository.PHASE_STATUS_MAPPING.get(phase_name, [])
            if not statuses:
                continue
                
            for i in range(count):
                essay_id = f"{batch_id}-{phase_name}-{i}"
                # Cycle through statuses for variety
                status = statuses[i % len(statuses)]
                
                essay_state = await repository.create_essay_record(
                    essay_id=essay_id,
                    batch_id=batch_id,
                    correlation_id=uuid4()
                )
                
                # Update to target status
                await repository.update_essay_state(
                    essay_id=essay_id,
                    new_status=status,
                    metadata={
                        "current_phase": phase_name,
                        "commanded_phases": [phase_name]
                    },
                    correlation_id=uuid4()
                )
                
                essays.append(essay_state)
        
        return essays
    
    @staticmethod
    async def create_essay_with_full_lifecycle(
        repository: EssayRepositoryProtocol,
        essay_id: str,
        batch_id: str,
        target_status: EssayStatus
    ) -> EssayState:
        """Create an essay and progress it through lifecycle to target status."""
        # Implementation for creating essays with complete history
        pass
```

### Phase 2: Gradual Test Migration (Weeks 2-3)

#### 2.1 Week 2.1: Migrate Simple Unit Tests
**Target Tests**: Basic CRUD operations without complex state management

**Files to Migrate First**:
- `test_state_store_impl.py::test_create_essay_record`
- `test_state_store_impl.py::test_get_essay_state`
- `test_state_store_impl.py::test_update_essay_state`

**Migration Pattern**:
```python
# OLD: SQLite-based test
async def test_create_essay_record(state_store: SQLiteEssayStateStore):
    essay = await state_store.create_essay_record(
        essay_id="test-1", batch_id="batch-1"
    )
    assert essay.essay_id == "test-1"

# NEW: Mock-based test with helper
async def test_create_essay_record(mock_repository: MockEssayRepository):
    essay = await mock_repository.create_essay_record(
        essay_id="test-1", 
        batch_id="batch-1",
        correlation_id=uuid4()  # Now required
    )
    assert essay.essay_id == "test-1"
```

#### 2.2 Week 2.2: Migrate Complex Unit Tests
**Target Tests**: Atomic operations, phase queries, batch operations

**Critical Tests Requiring Special Attention**:
1. **Idempotency Tests**: Must verify constraint simulation
2. **Phase Query Tests**: Must use correct status mappings
3. **Concurrent Operation Tests**: Must verify lock behavior

**Example Migration for Phase Queries**:
```python
# Use test data builder for consistency
async def test_list_essays_by_batch_and_phase(mock_repository: MockEssayRepository):
    # Create test data using builder
    essays = await EssayTestDataBuilder.create_batch_with_phase_distribution(
        repository=mock_repository,
        batch_id="test-batch-1",
        phase_distributions={
            "spellcheck": 2,
            "cj_assessment": 3,
        }
    )
    
    # Test phase queries
    spellcheck_essays = await mock_repository.list_essays_by_batch_and_phase(
        batch_id="test-batch-1",
        phase_name="spellcheck"
    )
    assert len(spellcheck_essays) == 2
```

#### 2.3 Week 2.3: Migrate Integration Tests
**Target**: All tests using PostgreSQL

**Integration Test Setup**:
```python
# tests/integration/conftest.py
@pytest.fixture
def mock_repository() -> MockEssayRepository:
    """Mock repository for integration tests."""
    return MockEssayRepository()

@pytest.fixture
async def postgres_repository() -> AsyncGenerator[PostgreSQLEssayRepository, None]:
    """PostgreSQL repository with TestContainers."""
    with PostgresContainer("postgres:15") as postgres:
        test_settings = Settings(
            DATABASE_URL=postgres.get_connection_url(driver="postgresql+asyncpg"),
            DATABASE_POOL_SIZE=5,
            DATABASE_MAX_OVERFLOW=0
        )
        
        repository = PostgreSQLEssayRepository(test_settings)
        await repository.initialize_db_schema()
        await repository.run_migrations()
        
        yield repository
        
        await repository.engine.dispose()
```

**Parallel Test Strategy**:
```python
@pytest.mark.parametrize("repository_fixture", [
    "mock_repository",
    "postgres_repository"
])
async def test_repository_behavior(repository_fixture, request):
    """Run same test against both implementations to verify parity."""
    repository = request.getfixturevalue(repository_fixture)
    # Test logic here
```

#### 2.4 Week 2.4: Performance Validation
**Performance Benchmarking Suite**:

```python
# tests/performance/test_mock_repository_performance.py
import time
import asyncio
from statistics import mean, stdev

class TestMockRepositoryPerformance:
    """Validate mock repository meets performance targets."""
    
    async def test_instantiation_time(self):
        """Mock instantiation: <1ms"""
        times = []
        for _ in range(100):
            start = time.perf_counter()
            MockEssayRepository()
            times.append((time.perf_counter() - start) * 1000)
        
        assert mean(times) < 1.0, f"Instantiation too slow: {mean(times):.2f}ms"
    
    async def test_single_essay_crud(self, mock_repository):
        """Single essay CRUD: <0.1ms"""
        times = []
        for i in range(100):
            start = time.perf_counter()
            await mock_repository.create_essay_record(
                essay_id=f"perf-{i}",
                batch_id="batch-1",
                correlation_id=uuid4()
            )
            times.append((time.perf_counter() - start) * 1000)
        
        assert mean(times) < 0.1, f"CRUD too slow: {mean(times):.2f}ms"
    
    async def test_batch_operations(self, mock_repository):
        """Batch operations (100 essays): <10ms"""
        essay_data = [
            {"essay_id": f"batch-{i}", "batch_id": "perf-batch"}
            for i in range(100)
        ]
        
        start = time.perf_counter()
        await mock_repository.create_essay_records_batch(
            essay_data=essay_data,
            correlation_id=uuid4()
        )
        duration = (time.perf_counter() - start) * 1000
        
        assert duration < 10, f"Batch operation too slow: {duration:.2f}ms"
    
    async def test_concurrent_operations(self, mock_repository):
        """Concurrent operations: Linear scaling up to 1000 ops"""
        async def create_essay(i):
            await mock_repository.create_essay_record(
                essay_id=f"concurrent-{i}",
                batch_id="concurrent-batch",
                correlation_id=uuid4()
            )
        
        # Test scaling
        for num_ops in [10, 100, 1000]:
            start = time.perf_counter()
            await asyncio.gather(*[create_essay(i) for i in range(num_ops)])
            duration = time.perf_counter() - start
            
            ops_per_second = num_ops / duration
            assert ops_per_second > 10000, f"Poor scaling at {num_ops} ops"
    
    async def test_memory_footprint(self, mock_repository):
        """Memory footprint: <10MB for 10,000 essays"""
        import tracemalloc
        
        tracemalloc.start()
        
        # Create 10,000 essays
        for i in range(10000):
            await mock_repository.create_essay_record(
                essay_id=f"mem-{i}",
                batch_id=f"mem-batch-{i // 100}",
                correlation_id=uuid4()
            )
        
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        
        # Convert to MB
        peak_mb = peak / 1024 / 1024
        assert peak_mb < 10, f"Memory usage too high: {peak_mb:.2f}MB"
```

### Phase 3: Remove SQLite Implementation (Week 3)

#### 3.1 File Deletion
**Files to Remove**:
```
services/essay_lifecycle_service/
├── state_store.py                           # Complete removal
├── implementations/
│   ├── database_schema_manager.py           # SQLite-specific code
│   ├── essay_crud_operations.py             # SQLite-specific code
│   └── essay_state_model.py                 # ALREADY REMOVED - content moved to domain_models.py
```

**Note**: The `essay_state_model.py` file's content has already been extracted to `domain_models.py` in Phase 0.

#### 3.2 Import Cleanup
**Files Requiring Import Updates**:
- All test files importing `SQLiteEssayStateStore`
- Service configuration and factory files
- Documentation and example code

**Search and Replace Operations**:
```bash
# Remove SQLite imports
grep -r "from.*SQLiteEssayStateStore" services/essay_lifecycle_service/
grep -r "import.*state_store" services/essay_lifecycle_service/

# Remove SQLite references
grep -r "SQLite" services/essay_lifecycle_service/
grep -r "aiosqlite" services/essay_lifecycle_service/
```

#### 3.3 Configuration Cleanup
**File**: `services/essay_lifecycle_service/config.py`
```python
# REMOVE: SQLite-specific settings
SQLITE_DATABASE_PATH: str = Field(default="./essay_lifecycle.db")
USE_SQLITE: bool = Field(default=False)

# KEEP: PostgreSQL settings only
DATABASE_URL: str = Field(...)
DATABASE_POOL_SIZE: int = Field(default=10)
```

#### 3.4 Dependency Management
**File**: `pyproject.toml`
```toml
# REMOVE from dependencies:
aiosqlite = "^0.19.0"

# KEEP: PostgreSQL and testing dependencies
asyncpg = "^0.28.0"
testcontainers = "^3.7.0"
```

#### 3.5 Documentation Updates
**Files to Update**:
- `services/essay_lifecycle_service/README.md`
- `.windsurf/rules/070-testing-and-quality-assurance.md`
- Root `README.md` (testing strategy section)

**Documentation Changes**:
```markdown
# OLD: Development Setup
For development, the service can use SQLite for faster iteration...

# NEW: Development Setup  
For unit testing, the service uses an in-memory mock repository.
For integration testing, use TestContainers with PostgreSQL.
```

### Phase 4: Validation and Quality Assurance (Week 4)

#### 4.1 Test Suite Validation
**Comprehensive Test Execution**:
```bash
# Unit tests (should be <1s)
pdm run pytest services/essay_lifecycle_service/tests/unit/ -v

# Integration tests (with TestContainers)
pdm run pytest services/essay_lifecycle_service/tests/integration/ -v

# E2E tests (full Docker stack)
pdm run pytest tests/functional/ -k essay_lifecycle -v
```

#### 4.2 Performance Benchmarking
**Metrics to Validate**:
- Unit test execution time: <1 second for full suite
- Memory usage: <100MB for unit test suite
- CI/CD pipeline time reduction: >50% improvement
- Test determinism: 100% reproducible across runs

#### 4.3 Protocol Compliance Verification
**Validation Script**: `scripts/validate_repository_compliance.py`
```python
async def validate_protocol_compliance():
    """Ensure MockEssayRepository and PostgreSQLEssayRepository behave identically"""
    mock_repo = MockEssayRepository()
    postgres_repo = PostgreSQLEssayRepository(test_settings)
    
    # Test identical behavior for same inputs
    test_cases = [
        create_essay_record_test,
        update_essay_state_test,
        atomic_operations_test,
        # ... all protocol methods
    ]
```

#### 4.4 Migration Verification Checklist
- [ ] All SQLite files removed from codebase
- [ ] No remaining SQLite imports or references
- [ ] All unit tests use MockEssayRepository
- [ ] All integration tests use PostgreSQLEssayRepository  
- [ ] E2E tests use Docker/production stack
- [ ] Test execution time improved by >50%
- [ ] 100% test pass rate maintained
- [ ] Documentation updated and accurate
- [ ] Dependencies cleaned up in pyproject.toml

## Risk Mitigation

### 1. Session Management Ambiguity
**Risk**: Mock doesn't use SQLAlchemy sessions but protocol requires them
**Mitigation**: 
- Document session parameter handling clearly in mock implementation
- Use explicit `_ = session` pattern to acknowledge parameter
- Add docstring notes about mock behavior differences

### 2. Incomplete Atomic Operation Simulation
**Risk**: `asyncio.Lock` only provides in-process atomicity
**Mitigation**:
- Implement constraint simulation with `_unique_constraints` dict
- Use double-check locking pattern inside critical sections
- Add explicit tests for race condition scenarios

### 3. Missing Domain Model Dependencies
**Risk**: `EssayState` currently lives in SQLite module
**Mitigation**:
- Extract to `domain_models.py` in Phase 0
- Update all imports before starting mock implementation
- Ensure domain model is storage-agnostic

### 4. Complex Query Method Accuracy
**Risk**: Phase queries might not match PostgreSQL logic
**Mitigation**:
- Copy `PHASE_STATUS_MAPPING` exactly from PostgreSQL implementation
- Add comprehensive tests comparing mock vs PostgreSQL results
- Use parametrized tests to verify identical behavior

### 5. Test Data Migration Complexity
**Risk**: Existing test scenarios hard to recreate
**Mitigation**:
- Create `EssayTestDataBuilder` for consistent test data
- Manual migration with clear patterns
- Gradual migration approach over 4 sub-phases

## Success Criteria

### Quantitative Metrics
- **Test Execution Time**: <1 second for full unit test suite
- **CI/CD Improvement**: >50% reduction in test execution time
- **Memory Usage**: <100MB for unit test suite
- **Test Determinism**: 100% reproducible results
- **Performance Benchmarks**:
  - Mock instantiation: <1ms
  - Single essay CRUD: <0.1ms
  - Batch operations (100 essays): <10ms
  - Concurrent operations: Linear scaling up to 1000 operations
  - Memory footprint: <10MB for 10,000 essays

### Qualitative Metrics
- **Code Maintainability**: Simplified test setup and teardown
- **Developer Experience**: Faster feedback loops
- **Architectural Consistency**: Aligned with BOS patterns
- **Test Reliability**: Elimination of file-system dependencies
- **Protocol Compliance**: 100% behavioral parity between mock and PostgreSQL

## Timeline Summary - Revised

| Phase | Duration | Key Deliverables |
|-------|----------|------------------|
| Phase 0 | Week 0.5 | Domain model extraction |
| Phase 1 | Week 1 | Enhanced MockEssayRepository with constraints |
| Phase 2.1 | Week 2.1 | Simple unit test migration |
| Phase 2.2 | Week 2.2 | Complex unit test migration |
| Phase 2.3 | Week 2.3 | Integration test migration |
| Phase 2.4 | Week 2.4 | Performance validation |
| Phase 3 | Week 3 | SQLite removal and cleanup |
| Phase 4 | Week 4 | Validation and documentation |

**Total Duration**: 5.5 weeks (expanded for gradual migration)
**Team Size**: 2-3 developers
**Risk Level**: Low (comprehensive mitigation strategies)

## Post-Migration Benefits

### Immediate Benefits
- 10-50x faster unit test execution
- Elimination of file-system test dependencies
- Improved CI/CD pipeline performance
- Better concurrency testing capabilities

### Long-term Benefits
- Consistent repository patterns across services
- Easier onboarding for new developers
- Reduced maintenance overhead
- Foundation for advanced testing patterns

## Important Notes on Cascading Changes

### Import Path Changes
After Phase 0 completion, all code must import `EssayState` from the new location:

```python
# OLD - DO NOT USE
from services.essay_lifecycle_service.implementations.essay_state_model import EssayState
from services.essay_lifecycle_service.state_store import EssayState

# NEW - USE THIS
from services.essay_lifecycle_service.domain_models import EssayState
```

### Type Checking Considerations
When using `get_essay_state()` which returns `EssayState | None`, ensure proper None checks:

```python
# Will cause mypy errors
essay_state = await repository.get_essay_state("id")
essay_state.current_status  # Error: essay_state might be None

# Correct approach
essay_state = await repository.get_essay_state("id")
assert essay_state is not None  # or if essay_state is not None:
essay_state.current_status  # Now safe
```

### Repository Implementation Notes
1. Both mock and PostgreSQL repositories must import the concrete `EssayState` from `domain_models.py`
2. This is architecturally sound - infrastructure depends on domain, not vice versa
3. The protocol still provides the abstraction layer for service boundaries

## Additional Implementation Details

### Protocol Compliance Verification Script
**File**: `scripts/validate_els_repository_compliance.py`

```python
import asyncio
from uuid import uuid4
from typing import Any

from services.essay_lifecycle_service.implementations.mock_essay_repository import MockEssayRepository
from services.essay_lifecycle_service.implementations.essay_repository_postgres_impl import PostgreSQLEssayRepository
from services.essay_lifecycle_service.domain_models import EssayState
from common_core.status_enums import EssayStatus

async def validate_protocol_compliance():
    """Ensure MockEssayRepository and PostgreSQLEssayRepository behave identically."""
    
    # Initialize repositories
    mock_repo = MockEssayRepository()
    # postgres_repo would be initialized with test container in real test
    
    # Test case generators
    test_cases = [
        # Basic CRUD
        ("create_essay", lambda r: r.create_essay_record(
            essay_id="test-1", batch_id="batch-1", correlation_id=uuid4()
        )),
        
        # Idempotency with constraints
        ("idempotency", lambda r: r.create_essay_state_with_content_idempotency(
            batch_id="batch-1",
            text_storage_id="text-123",
            essay_data={"internal_essay_id": "essay-1"},
            correlation_id=uuid4()
        )),
        
        # Phase queries
        ("phase_query", lambda r: r.list_essays_by_batch_and_phase(
            batch_id="batch-1", phase_name="spellcheck"
        )),
        
        # Atomic updates
        ("atomic_update", lambda r: r.update_essay_state(
            essay_id="test-1",
            new_status=EssayStatus.SPELLCHECKED_SUCCESS,
            metadata={"result": "success"},
            correlation_id=uuid4()
        )),
    ]
    
    # Run tests and compare results
    for test_name, test_func in test_cases:
        print(f"Testing {test_name}...")
        mock_result = await test_func(mock_repo)
        # postgres_result = await test_func(postgres_repo)
        # assert mock_result == postgres_result
```

### Key Implementation Notes

1. **Constraint Simulation Details**:
   - The `_unique_constraints` dict simulates PostgreSQL's partial unique index
   - Only non-NULL `text_storage_id` values are enforced for uniqueness
   - This matches the production database behavior exactly

2. **Lock Granularity**:
   - Individual essay operations use `essay_id` as lock key
   - Batch operations use `batch_id` as lock key
   - Constraint checks use compound keys like `"{batch_id}:{text_storage_id}"`

3. **Session Parameter Handling**:
   - All methods accepting `session` parameter must include `_ = session`
   - This makes it explicit that the mock ignores sessions
   - Prevents linting warnings about unused parameters

4. **Phase Status Mapping Accuracy**:
   - The `PHASE_STATUS_MAPPING` must be copied exactly from PostgreSQL implementation
   - Any changes to production phase logic must be reflected in mock
   - Consider extracting to shared constants module

## Lessons Learned from Phase 0 Implementation

### 1. Pydantic vs Dataclasses
- Initially considered dataclasses for domain models
- Chose Pydantic to maintain consistency with existing codebase
- Pydantic provides built-in validation and serialization needed for the domain model

### 2. Import Dependencies
- Domain models should be in a standalone module, not embedded in infrastructure
- Infrastructure (repositories) can import domain models - this follows DDD principles
- The protocol provides the abstraction, concrete types are needed for instantiation

### 3. Type Checking Challenges
- Methods returning `T | None` require explicit None checks before use
- Avoid reusing variable names when types change (e.g., from `T` to `T | None`)
- Run `pdm run typecheck-all` after any import changes

### 4. File Organization
- `domain_models.py` at service root level, not in implementations/
- Clear separation between domain, infrastructure, and application layers

## Conclusion

This revised migration plan addresses all identified pain points and provides a comprehensive approach to migrating ELS from SQLite to the three-tier repository pattern. The key improvements include:

1. **Domain Model Extraction** - Eliminates SQLite dependencies upfront (COMPLETED)
2. **Enhanced Constraint Simulation** - Matches PostgreSQL behavior precisely
3. **Gradual Migration Approach** - Reduces risk and complexity
4. **Comprehensive Testing Tools** - Builders and performance benchmarks
5. **Clear Documentation** - Session handling, lock patterns, and compliance verification

By following this plan, the Essay Lifecycle Service will achieve the same testing performance and architectural consistency as the Batch Orchestrator Service, while maintaining 100% test coverage and behavioral accuracy.
