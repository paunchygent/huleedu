# Epic: Pre-emptive Raw File Storage (PIPELINE_HARDENING_V1.1)

**Status**: Phase 1 Complete ✅ | Phase 2 Complete ✅ | Phase 3 Complete ✅ | Phase 4 Complete ✅  
**Objective**: Refactor the File Service to persist the raw, unmodified file blob before any processing occurs. This establishes an immutable source of truth, enabling robust reprocessing and decoupling storage from interpretation.

---

## ✅ **PHASE 1 COMPLETE: Contract Changes**

### Task 2.1: Enhance ContentType Enum ✅ COMPLETED

**Implementation**: Added `RAW_UPLOAD_BLOB = "raw_upload_blob"` and `EXTRACTED_PLAINTEXT = "extracted_plaintext"` to `common_core/src/common_core/enums.py`. Enables type-safe differentiation between original file blobs and processed text content.

### Task 2.2: Update Event Contracts ✅ COMPLETED  

**Implementation**: Added `raw_file_storage_id: str` field to `EssayContentProvisionedV1` and `EssayValidationFailedV1` in `common_core/src/common_core/events/file_events.py`. Updated all related test cases to handle the new required field. Provides downstream services with original file reference for traceability and reprocessing.

**Validation**: All 51 common_core tests pass, no breaking changes to existing functionality.

---

## ✅ **PHASE 2 COMPLETE: Redis Infrastructure Setup**

### Task 3.1.1: Redis Docker Infrastructure ✅ COMPLETED

**Implementation**: Added redis:7-alpine service to docker-compose.yml with production-ready configuration:

```yaml
redis:
  image: redis:7-alpine
  container_name: huleedu_redis
  command: redis-server --appendonly yes --maxmemory 256mb --maxmemory-policy allkeys-lru
  healthcheck:
    test: ["CMD", "redis-cli", "ping"]
```

**Features**: Data persistence (AOF), memory management, health monitoring, internal network integration. Added `redis_data` volume for durability.

**Validation**: ✅ Container startup successful, ✅ Health check returns PONG, ✅ Network connectivity confirmed.

### Task 3.1.2: Service Library Redis Client ✅ COMPLETED

**Implementation**: Created `huleedu_service_libs/redis_client.py` following exact KafkaBus patterns:

```python
class RedisClient:
    async def start(self) -> None: # Lifecycle management
    async def stop(self) -> None:
    async def set_if_not_exists(self, key: str, value: Any, ttl_seconds: Optional[int] = None) -> bool:
    async def delete_key(self, key: str) -> int:
```

**Features**: Async lifecycle, connection verification via ping(), structured logging, timeout handling, type-safe operations for idempotency patterns.

**Dependencies**: Added `redis[hiredis]>=5.0.0` to service libs, configured mypy overrides for Redis imports.

### Task 3.1.3: Service Configuration Updates ✅ COMPLETED

**Implementation**: Added Redis environment variables to CJ Assessment and Spell Checker services:

```python
# services/cj_assessment_service/config.py & services/spell_checker_service/config.py
REDIS_URL: str = "redis://localhost:6379"  # Development/test default
```

**Features**: Environment variable override support via `env_prefix`, consistent with Kafka configuration patterns.

**Validation**: ✅ Configuration loads correctly, ✅ Docker override via environment variables supported.

### Task 3.1.4: DI Provider Implementation ✅ COMPLETED

**Implementation**: Added RedisClient providers to both service DI configurations following KafkaBus pattern:

```python
@provide(scope=Scope.APP)
async def provide_redis_client(self, settings: Settings) -> RedisClientProtocol:
    redis_client = RedisClient(
        client_id=f"{settings.SERVICE_NAME}-redis",
        redis_url=settings.REDIS_URL
    )
    await redis_client.start()
    return redis_client
```

**Features**: APP scope lifecycle management, proper async startup/shutdown, settings injection, protocol-based DI.

**Validation**: ✅ DI container resolution working, ✅ Redis client lifecycle managed correctly.

### Task 3.1.5: Protocol Definitions ✅ COMPLETED

**Implementation**: Added RedisClientProtocol to both service protocols.py files:

```python
class RedisClientProtocol(Protocol):
    async def set_if_not_exists(self, key: str, value: Any, ttl_seconds: Optional[int] = None) -> bool: ...
    async def delete_key(self, key: str) -> int: ...
```

**Features**: Type-safe injection interface, idempotency operation support, consistent with established protocol patterns.

**Validation**: ✅ Protocol compliance verified, ✅ Type checking passes, ✅ DI injection working.

### Task 3.1.6: Integration Testing ✅ COMPLETED

**Implementation**: Created comprehensive test suites for both services:

- **CJ Assessment**: `services/cj_assessment_service/tests/test_redis_integration.py` (3 tests)
- **Spell Checker**: `services/spell_checker_service/tests/test_redis_integration.py` (4 tests)

**Test Coverage**:

- ✅ DI container injection and lifecycle management
- ✅ Redis client protocol compliance verification  
- ✅ Idempotency pattern validation (SETNX operations)
- ✅ Connection management and error handling

**Validation**: ✅ All 7 tests passing, ✅ Redis connectivity confirmed, ✅ Idempotency patterns working correctly.

### Task 3.1.7: Complete ELS and BOS Integration ✅ COMPLETED

**Implementation**: Successfully added Redis integration to Essay Lifecycle Service and Batch Orchestrator Service following established patterns:

**Essay Lifecycle Service (ELS)**:

- Added `REDIS_URL: str = "redis://localhost:6379"` to configuration
- Added `RedisClientProtocol` to protocols.py with `set_if_not_exists()` and `delete_key()` operations
- Added Redis provider to `CoreInfrastructureProvider` with APP scope lifecycle management
- Created comprehensive test suite: `services/essay_lifecycle_service/tests/test_redis_integration.py` (4 tests)

**Batch Orchestrator Service (BOS)**:

- Added `REDIS_URL: str = "redis://localhost:6379"` to configuration
- Added `RedisClientProtocol` to protocols.py with matching interface
- Added Redis provider to `CoreInfrastructureProvider` following KafkaBus pattern
- Created comprehensive test suite: `services/batch_orchestrator_service/tests/test_redis_integration.py` (4 tests)

**Validation**: ✅ All 15 Redis integration tests passing across all services (CJ Assessment, Spell Checker, ELS, BOS)

- ✅ DI container injection and lifecycle management
- ✅ Redis client protocol compliance verification
- ✅ Idempotency pattern validation (SETNX operations)
- ✅ Connection management and error handling

**Architecture Compliance**:
✅ Follows established KafkaBus patterns
✅ Protocol-based DI for testability
✅ APP scope lifecycle management
✅ Environment variable configuration
✅ Structured logging integration
✅ Type-safe operations

---

## ✅ **PHASE 3 COMPLETE: File Service Refactor**

### Task 2.3: Update ContentServiceClientProtocol ✅ COMPLETED

**Implementation**: Updated `ContentServiceClientProtocol` in `services/file_service/protocols.py` to accept `ContentType` parameter:

```python
async def store_content(self, content_bytes: bytes, content_type: ContentType) -> str:
    """
    Store content in Content Service and return storage ID.
    
    Args:
        content_bytes: Raw binary content to store
        content_type: Type of content being stored (RAW_UPLOAD_BLOB, EXTRACTED_PLAINTEXT, etc.)
    """
```

**Features**: Enables differentiation between raw file blobs and processed text content, maintains consistency with ELS content client patterns.

### Task 2.4: Implement "Store Raw First" Logic ✅ COMPLETED

**Implementation**: Refactored `process_single_file_upload()` in `services/file_service/core_logic.py` to implement pre-emptive raw storage workflow:

```python
# NEW WORKFLOW:
# 1. Store raw file blob immediately
raw_file_storage_id = await content_client.store_content(
    file_content, ContentType.RAW_UPLOAD_BLOB
)

# 2. Extract and validate text
text = await text_extractor.extract_text(file_content, file_name)
validation_result = await content_validator.validate_content(text, file_name)

# 3. Store extracted plaintext (if valid)
text_storage_id = await content_client.store_content(
    text.encode("utf-8"), ContentType.EXTRACTED_PLAINTEXT
)

# 4. Populate raw_file_storage_id in ALL events
event = EssayContentProvisionedV1(
    raw_file_storage_id=raw_file_storage_id,  # ← CRITICAL FIX
    text_storage_id=text_storage_id,
    # ... other fields
)
```

**Key Changes**:

- ✅ Raw file blob stored FIRST (establishes immutable source of truth)
- ✅ Both success and failure events contain `raw_file_storage_id`
- ✅ Extracted plaintext stored with `ContentType.EXTRACTED_PLAINTEXT`
- ✅ Enhanced logging with storage operation traceability
- ✅ Return values include both storage IDs for debugging

### Task 2.5: Unit Tests ✅ COMPLETED

**Implementation**: Created comprehensive unit test suite `services/file_service/tests/unit/test_core_logic_raw_storage.py` with 4 test cases:

- ✅ `test_process_single_file_stores_raw_blob_first()` - Validates storage order and ContentType usage
- ✅ `test_extraction_failure_includes_raw_storage_id()` - Validates failure events contain raw storage ID
- ✅ `test_validation_failure_includes_raw_storage_id()` - Validates business rule failures include raw storage ID  
- ✅ `test_success_event_includes_both_storage_ids()` - Validates success events contain both storage IDs

**Test Results**: All 4 unit tests passing, validates complete workflow coverage including error scenarios.

### Task 2.6: E2E Tests ✅ COMPLETED

**Implementation**: Created E2E test suite `tests/functional/test_file_service_raw_storage_e2e.py` with 2 comprehensive tests:

- ✅ `test_file_service_events_contain_raw_storage_id()` - End-to-end validation of success event structure
- ✅ `test_file_service_validation_failure_contains_raw_storage_id()` - End-to-end validation of failure event structure

**Features**:

- Real File Service HTTP API integration
- Kafka event consumption and validation  
- Pydantic model structure verification
- Both success and failure path coverage

---

## ✅ **PHASE 4 COMPLETE: Idempotency Infrastructure**

### Task 3.2: Generate Deterministic Event ID ✅ COMPLETED

**Implementation**: Created `common_core/src/common_core/events/utils.py` with `generate_deterministic_event_id()` function for stable, content-based event hashing critical to idempotency guarantees.

**Technical Details**:

```python
def generate_deterministic_event_id(msg_value: bytes) -> str:
    # Hash stable 'data' payload only, ignoring transient envelope metadata
    # Handles JSON key order independence via sort_keys=True
    # Fallback to raw message hash for malformed/non-UTF8 content
    return hashlib.sha256(stable_string.encode('utf-8')).hexdigest()
```

**Validation**: 12 comprehensive unit tests covering edge cases (malformed JSON, non-UTF8 bytes, missing data field, key order independence). All tests passing with full exception handling.

### Task 3.3: Create Idempotency Decorator ✅ COMPLETED

**Implementation**: Successfully created `services/libs/huleedu_service_libs/idempotency.py` with production-ready idempotency decorator following established service library patterns.

**Technical Features**:

- DRY decorator pattern using `@idempotent_consumer(redis_client, ttl_seconds=86400)`
- Redis SETNX operations with configurable TTL for duplicate detection
- Deterministic event ID generation using existing `common_core.events.utils`
- Fail-open approach: processes without idempotency protection if Redis fails
- Proper error handling with automatic key cleanup on processing failures
- Structured logging for duplicate detection and debugging
- Type-safe integration with central RedisClientProtocol

**Unit Tests**: Created comprehensive test suite `services/libs/huleedu_service_libs/tests/test_idempotency.py` with 8 test scenarios:

- ✅ First-time event processing with real handlers (not mocks)
- ✅ Duplicate event detection and skipping
- ✅ Processing failure recovery with key cleanup
- ✅ Redis failure fallback behavior
- ✅ Default TTL application (24 hours)
- ✅ Deterministic key generation validation
- ✅ Call tracking verification without mocking business logic

**Validation**: All 8 unit tests passing, follows testing best practices (real handler functions, only external dependencies mocked).

### 🏗️ **ARCHITECTURAL REFINEMENT COMPLETED**

**Lead Architect Feedback Implementation**: Successfully implemented the recommended architectural refinement to centralize `RedisClientProtocol` and eliminate technical debt.

**Changes Made**:

1. **Central Protocol Creation**: Created `services/libs/huleedu_service_libs/protocols.py` with canonical `RedisClientProtocol`
2. **Type Safety Enhancement**: Updated idempotency decorator to use `RedisClientProtocol` instead of `Any` type workaround
3. **DRY Compliance**: Removed 4 duplicate protocol definitions across services → 1 authoritative source
4. **Service Migration**: Updated all 4 services (BOS, ELS, CJ Assessment, Spell Checker) to import from central location:
   - Updated `di.py` files to import from `huleedu_service_libs.protocols`
   - Updated `protocols.py` files to remove duplicate definitions
   - Updated test files to use central protocol

**Quality Assurance**:
- ✅ All 23 tests passing (8 idempotency + 15 Redis integration)
- ✅ Zero linting errors across all modified files
- ✅ MyPy type checking passes with full type safety
- ✅ No breaking changes to existing functionality

**Benefits Achieved**:
- **Type Safety**: Eliminated `Any` workaround, achieved full type safety
- **Maintainability**: Single source of truth for Redis protocol interface
- **Consistency**: All services use identical protocol definition
- **Encapsulation**: Protocol belongs with its implementation in service libs

---

## ✅ **PHASE 4 VALIDATION RESULTS**

**Breaking Change Fixed**: The File Service now successfully populates the required `raw_file_storage_id` field in all events, resolving the Pydantic validation failures that were breaking the pipeline.

**Implementation Quality**:

- ✅ 4/4 unit tests passing - Validates core workflow logic
- ✅ Protocol compliance - Follows established patterns from ELS
- ✅ Type safety - Full ContentType enum integration
- ✅ Error handling - Raw storage preserved even on processing failures
- ✅ Audit trail - Immutable source of truth established for all uploaded files
- ✅ Logging enhancement - Complete traceability of storage operations

**Pipeline Status**: The File Service is now compatible with Phase 1 contract changes and should restore full pipeline functionality.

**Infrastructure Status**: Redis infrastructure and idempotency decorator are production-ready and architecturally sound, ready for application to consumer services.

---

## 🚀 **NEXT STEPS**

### Phase 5: Apply Idempotency to Consumers (Task 3.4)

- Apply `@idempotent_consumer` decorator to all 4 consumer services
- Update consumer loops to handle duplicate detection
- Validate idempotency behavior in integration tests

### Phase 6: End-to-End Validation (Task 3.5)

- Create comprehensive E2E idempotency tests
- Chaos testing with intentional duplicate events
- Performance validation under load
