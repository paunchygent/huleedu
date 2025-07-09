# Class Management Service - Async Session Management & Production Readiness

## Task Overview

**Objective**: Debug and fix critical async session management issues in the Class Management Service, replacing skeleton code with production-ready implementation.

**Service Purpose**: The Class Management Service serves as the authoritative source of truth for classes, students, and their relationships within the HuleEdu ecosystem. It provides synchronous CRUD operations via REST API and publishes state change events to Kafka for ecosystem notifications.

**Repository**: `/Users/olofs_mba/Documents/Repos/huledu-reboot/services/class_management_service/`

**Related Rules**: 
- [042-async-patterns-and-di.mdc](/.cursor/rules/042-async-patterns-and-di.mdc) - Async patterns and DI
- [020.9-class-management-service.mdc](/.cursor/rules/020.9-class-management-service.mdc) - Service architecture
- [053-sqlalchemy-standards.mdc](/.cursor/rules/053-sqlalchemy-standards.mdc) - Database patterns

## Root Cause Analysis

### Primary Issue: Async Session Management Anti-Pattern

**Problem**: SQLAlchemy `MissingGreenlet` errors during database operations, particularly in retrieval operations.

**Root Cause**: The Class Management Service implemented a fundamentally flawed DI pattern that violated SQLAlchemy's async context requirements:

1. **SESSION-scoped AsyncSession injection**: Repository received pre-created session instances from DI container
2. **Cross-context session usage**: Sessions created in DI container async context were used in repository async context
3. **Double transaction management**: Both DI provider and repository attempted to manage transactions

**Technical Details**:
- `MissingGreenlet` occurs when SQLAlchemy async sessions are accessed outside their originating async context (greenlet)
- The pattern `AsyncSession` → Repository constructor violates the "session-per-operation" principle
- Working services (CJ Assessment, Spell Checker) use repository-managed sessions, not DI-injected sessions

## PHASE 1: Critical Issues (Blocking Production) - ✅ COMPLETED

### 1.1 Fix Student API DetachedInstanceError - ✅ RESOLVED

**Status**: ✅ COMPLETED - All student endpoints now functional

**Issue**: Student creation and retrieval operations failed with `DetachedInstanceError` due to incomplete eager loading in `create_student` method.

**Root Cause**: The `create_student` method populated student.classes relationship but didn't eager load it before session closure, causing DetachedInstanceError when service layer accessed the relationship.

**Files Modified**:
- `services/class_management_service/implementations/class_repository_postgres_impl.py` (lines 195-196)

**Technical Solution Applied**:
```python
async def create_student(self, user_id: str, student_data: CreateStudentRequest) -> U:
    # ... existing logic ...
    await session.flush()
    
    # CRITICAL: Eager load classes relationship before session closes
    await session.refresh(new_student, ['classes'])
    return cast(U, new_student)
```

**Validation Successful**:
```bash
# Student Creation - Working ✅
curl -X POST localhost:5002/v1/classes/students \
  -H "Content-Type: application/json" \
  -H "X-User-ID: test-user" \
  -d '{"person_name": {"first_name": "Test", "last_name": "Student"}, "email": "test@example.com"}'
# Response: {"full_name": "Test Student", "id": "92b221b0-4bb0-47aa-89d8-78d0d7e19b0b"}

# Student Retrieval - Working ✅
curl -X GET localhost:5002/v1/classes/students/92b221b0-4bb0-47aa-89d8-78d0d7e19b0b \
  -H "X-User-ID: test-user"
# Response: {"class_ids": [], "email": "test@example.com", "first_name": "Test", ...}
```

### 1.2 Complete Repository Error Handling - ✅ COMPLETED

**Status**: ✅ COMPLETED - All repository methods now have comprehensive error handling

**Issue**: Only `create_class` had comprehensive error handling with metrics recording. Student methods lacked proper error reporting and observability.

**Files Modified**:
- `services/class_management_service/implementations/class_repository_postgres_impl.py` (all student methods)

**Pattern Applied Successfully**:
```python
async def create_student(self, user_id: str, student_data: CreateStudentRequest) -> U:
    start_time = time.time()
    operation = "create_student"
    table = "students"
    success = True
    
    try:
        async with self.session() as session:
            # Database operations
            await session.flush()
            await session.refresh(new_student, ['classes'])
            return cast(U, new_student)
    except Exception as e:
        success = False
        error_type = e.__class__.__name__
        self._record_error_metrics(error_type, operation)
        logger.error(f"Failed to create student: {error_type}: {e}")
        raise
    finally:
        duration = time.time() - start_time
        self._record_operation_metrics(operation, table, duration, success)
```

**Methods Enhanced**:
- `create_student()` - Full error handling and metrics
- `get_student_by_id()` - Added error handling and metrics
- `update_student()` - Added error handling and metrics  
- `delete_student()` - Added error handling and metrics
- `associate_essay_to_student()` - Added error handling and metrics

### 1.3 Fix Redis Lifecycle Management - ✅ COMPLETED

**Status**: ✅ COMPLETED - Redis connections properly managed via app lifecycle

**Issue**: Redis client lifecycle relied on container cleanup instead of proper app lifecycle integration, risking connection leaks in production.

**Files Modified**:
- `services/class_management_service/di.py` (lines 146-151, 175-186, 207-223)
- `services/class_management_service/startup_setup.py` (lines 46-53)

**Technical Solution Applied**:
```python
# In di.py - Proper shutdown handler registration
@provide(scope=Scope.APP)
async def provide_redis_client(self, settings: Settings) -> AtomicRedisClientProtocol:
    redis_client = RedisClient(
        client_id=f"{settings.SERVICE_NAME}-redis",
        redis_url=settings.REDIS_URL,
    )
    await redis_client.start()
    
    # Register shutdown finalizer to prevent connection leaks
    async def _shutdown_redis() -> None:
        await redis_client.stop()
    
    # Store shutdown function for cleanup
    if not hasattr(self, '_redis_shutdown_handlers'):
        self._redis_shutdown_handlers = []
    self._redis_shutdown_handlers.append(_shutdown_redis)
    
    return cast(AtomicRedisClientProtocol, redis_client)

async def shutdown_resources(self) -> None:
    """Shutdown Redis and other async resources managed by this provider."""
    if hasattr(self, '_redis_shutdown_handlers'):
        for shutdown_handler in self._redis_shutdown_handlers:
            try:
                await shutdown_handler()
            except Exception as e:
                logger.error(f"Failed to shutdown Redis connection: {e}")
        self._redis_shutdown_handlers.clear()

# In startup_setup.py - Integrated with app lifecycle
async def shutdown_services() -> None:
    """Gracefully shutdown all services."""
    try:
        from services.class_management_service.di import shutdown_container_resources
        await shutdown_container_resources()
        logger.info("Container resources shutdown completed")
    except Exception as e:
        logger.error(f"Error during container resource shutdown: {e}")
    
    logger.info("Class Management Service shutdown completed")
```

## PHASE 2: Architecture Improvements (Post-Critical)

### 2.1 Standardize Session Management Pattern

**Status**: ✅ COMPLETED - Class operations working correctly

**Achievement**: Successfully implemented repository-managed session pattern that matches working services.

**Pattern Implemented**:
```python
# Repository constructor receives AsyncEngine, not AsyncSession
def __init__(self, engine: AsyncEngine, metrics: Optional[DatabaseMetricsProtocol] = None):
    self.engine = engine
    self.metrics = metrics
    self.async_session_maker = async_sessionmaker(engine, expire_on_commit=False)

# Async context manager for session management
@asynccontextmanager
async def session(self) -> AsyncGenerator[AsyncSession, None]:
    session = self.async_session_maker()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()

# Usage in repository methods
async def create_class(self, user_id: str, class_data: CreateClassRequest) -> T:
    async with self.session() as session:
        # Database operations use session parameter
        # Repository calls flush(), context manager handles commit()
        await session.flush()
        return result
```

### 2.2 Course Validation Implementation

**Status**: ✅ COMPLETED - Production-ready course validation

**Achievement**: Replaced skeleton code with comprehensive course validation system.

**Files Implemented**:
- `services/class_management_service/exceptions.py` - Custom exception classes
- `services/class_management_service/alembic/versions/20250708_0002_seed_courses.py` - Course seeding migration

**Business Logic**:
- Validates course codes against predefined `CourseCode` enum
- Enforces single course per class despite API accepting list
- Provides specific error codes for validation failures
- Proper database relationship management

## PHASE 3: Testing & Documentation (Future)

### 3.1 Comprehensive Test Coverage

**Status**: ⏳ PENDING - No automated tests for new implementation

**Requirements**:
- Unit tests for all repository methods
- Integration tests for API endpoints
- Contract tests for event publishing
- Performance tests for async session management

**Files Needed**:
- `services/class_management_service/tests/integration/test_repository_async_patterns.py`
- `services/class_management_service/tests/api/test_student_endpoints.py`

### 3.2 Documentation Updates

**Status**: ⏳ PENDING - README needs implementation details

**Requirements**:
- Document async session management patterns
- Update API documentation with course validation rules
- Add troubleshooting guide for DetachedInstanceError

**Files Affected**:
- `services/class_management_service/README.md`

## Key Lessons Learned

### Critical Architectural Insights

1. **DI Session Anti-Pattern**: Direct `AsyncSession` injection into repositories violates async context boundaries
2. **Correct Pattern**: Inject `AsyncEngine`, let repositories manage sessions with async context managers
3. **Transaction Boundaries**: Repository methods should `flush()`, DI providers handle `commit()`
4. **Eager Loading**: SQLAlchemy relationships require `selectinload()` to prevent `DetachedInstanceError`

### Working vs. Failing Patterns

**❌ Anti-Pattern (Caused MissingGreenlet)**:
```python
# DI Provider
@provide(scope=Scope.REQUEST)
async def provide_session(self, sessionmaker) -> AsyncSession:
    async with sessionmaker() as session:
        yield session

# Repository
def __init__(self, session: AsyncSession):
    self.session = session  # Session from different async context
```

**✅ Correct Pattern**:
```python
# DI Provider
@provide(scope=Scope.APP)
def provide_repository(self, engine: AsyncEngine) -> Repository:
    return Repository(engine)

# Repository
def __init__(self, engine: AsyncEngine):
    self.async_session_maker = async_sessionmaker(engine)
    
@asynccontextmanager
async def session(self) -> AsyncGenerator[AsyncSession, None]:
    # Session created and used in same async context
```

### Production Deployment Checklist

**Phase 1 - Critical Issues (COMPLETED ✅)**:
- [x] Fix all Student API DetachedInstanceError issues
- [x] Implement proper Redis lifecycle management
- [x] Add comprehensive error handling to all repository methods
- [x] Validate all API endpoints are functional
- [x] Verify no connection leaks in service logs

**Architecture Compliance**:
- [x] Repository-managed sessions (not DI-injected)
- [x] Proper async context management
- [x] Course validation with business rules
- [x] Event publishing for state changes
- [x] Metrics and observability integration

**Phase 2 - Ready for Next Steps**:
- [ ] Run comprehensive test suite
- [ ] Performance testing under load
- [ ] Integration testing with downstream services
- [ ] Documentation updates

## Success Metrics

**Technical Metrics**:
- Zero `MissingGreenlet` errors in production logs
- All API endpoints return appropriate HTTP status codes
- Database connection pool remains stable
- Event publishing success rate > 99%

**Business Metrics**:
- Class creation/retrieval latency < 200ms
- Course validation error rate < 1%
- Zero data consistency issues
- Student management functionality fully operational

## File References

**Core Implementation**:
- `services/class_management_service/implementations/class_repository_postgres_impl.py` - Repository with async session management
- `services/class_management_service/di.py` - DI providers with APP-scoped repository
- `services/class_management_service/api/class_routes.py` - Class API endpoints
- `services/class_management_service/api/student_routes.py` - Student API endpoints (needs fixes)

**Configuration & Setup**:
- `services/class_management_service/startup_setup.py` - Service initialization
- `services/class_management_service/config.py` - Environment configuration
- `services/class_management_service/models_db.py` - Database models and relationships

**Supporting Files**:
- `services/class_management_service/exceptions.py` - Custom exception classes
- `services/class_management_service/protocols.py` - Type-safe interfaces
- `services/class_management_service/metrics.py` - Observability integration