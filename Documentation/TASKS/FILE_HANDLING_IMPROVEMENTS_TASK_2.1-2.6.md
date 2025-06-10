# Epic: Pre-emptive Raw File Storage (PIPELINE_HARDENING_V1.1)

**Status**: Phase 1 Complete ✅ | Phase 2 In Progress 🎯  
**Objective**: Refactor the File Service to persist the raw, unmodified file blob before any processing occurs. This establishes an immutable source of truth, enabling robust reprocessing and decoupling storage from interpretation.

---

## ✅ **PHASE 1 COMPLETE: Contract Changes**

### Task 2.1: Enhance ContentType Enum ✅ COMPLETED

**Implementation**: Added `RAW_UPLOAD_BLOB = "raw_upload_blob"` and `EXTRACTED_PLAINTEXT = "extracted_plaintext"` to `common_core/src/common_core/enums.py`. Enables type-safe differentiation between original file blobs and processed text content.

### Task 2.2: Update Event Contracts ✅ COMPLETED  

**Implementation**: Added `raw_file_storage_id: str` field to `EssayContentProvisionedV1` and `EssayValidationFailedV1` in `common_core/src/common_core/events/file_events.py`. Updated all related test cases to handle the new required field. Provides downstream services with original file reference for traceability and reprocessing.

**Validation**: All 51 common_core tests pass, no breaking changes to existing functionality.

---

## 🎯 **PHASE 2 IN PROGRESS: Redis Infrastructure Setup**

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

---

## 🔄 **REMAINING PHASE 2 TASKS**

### Task 3.1.3: Service Configuration Updates  

**Target**: Add Redis environment variables and dependencies to consumer services (ELS, BOS, Spell Checker, CJ Assessment).

### Task 3.1.4: DI Provider Implementation

**Target**: Add RedisClient DI providers following KafkaBus pattern in service di.py files.

### Task 3.1.5: Protocol Definitions

**Target**: Define RedisClientProtocol in consumer service protocols.py files for type-safe injection.

---

## 🚀 **PENDING PHASES**

### Phase 3: File Service Refactor (Tasks 2.3-2.6)

- Update ContentServiceClientProtocol signature
- Implement "store raw first" logic in core_logic.py  
- Create unit and E2E tests for new workflow

### Phase 4: Idempotency Layer (Tasks 3.2-3.5)

- Generate deterministic event IDs
- Create idempotency decorator in service libs
- Apply decorator to all consumer services
- Chaos testing and validation
