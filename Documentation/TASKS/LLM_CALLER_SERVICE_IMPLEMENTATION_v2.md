# 🏗️ LLM Provider Service - Implementation Status

## Service Overview

**Service**: `llm_provider_service`  
**Type**: HTTP API Service (Quart)  
**Purpose**: Centralized LLM provider abstraction  
**Status**: ✅ **PRODUCTION READY** (Pending Cache Refactor)

## Implementation Summary

### ✅ Core Components (Week 1)

**Architecture**:
- Full HuleEdu-compliant structure with protocols, DI, and separation of concerns
- Circuit breaker protection on all external calls
- Redis caching with local fallback (validated in production)
- Kafka event publishing for observability

**Key Files**:
- `config.py`: Comprehensive settings with provider configurations
- `protocols.py`: 5 core protocols for clean architecture
- `di.py`: Dishka provider with resilient service integrations
- `api/llm_routes.py`: Main comparison endpoint with CJ-compatible responses

### ✅ Provider Implementations (Week 2)

| Provider | Status | Features |
|----------|--------|----------|
| **Anthropic** | ✅ Complete | Tool use for structured responses, proper error handling |
| **OpenAI** | ✅ Complete | JSON mode, comprehensive error categorization |
| **Google** | ✅ Complete | Gemini API integration, token tracking |
| **OpenRouter** | ✅ Complete | OpenAI-compatible API, required headers |
| **Mock** | ✅ Complete | Testing without API calls, configurable responses |

### ✅ Resilience Features

**Redis Outage Handling**:
- Graceful degradation with local cache fallback
- Health monitoring shows cache status (`healthy`/`degraded`)
- Automatic recovery when Redis returns
- **Validated**: Service remains operational during Redis outages

**Circuit Breakers**:
- Individual breakers for each LLM provider
- Kafka publisher protection
- Configurable thresholds and recovery timeouts

## 🔄 CRITICAL CACHE REFACTOR REQUIRED

### Executive Summary

**What We're Changing**: Transform the LLM Provider Service from a response-caching system to a queue-based resilience system.

**Why**: Current response caching violates core business requirements:
- **CJ Assessment**: Needs natural judgment variation for valid Bradley-Tracy scoring
- **AI Feedback**: Users pay for fresh AI responses, not cached content

**How**: Replace response caching with request queuing:
- **Production**: Always serve fresh LLM responses, queue during outages
- **Development**: Use mock provider + optional response recorder for API validation
- **Resilience**: Use Redis queue with local fallback, explicit capacity limits

### Critical Insight: Redis Role Transformation

**Current Redis Behavior**:
- Stores LLM **responses** (complete API results)
- Key pattern: `llm-provider-service:cache:llm:{provider}:{content_hash}`
- Purpose: Avoid redundant LLM API calls
- Problem: Returns identical responses, breaking psychometric validity

**New Redis Behavior**:
- Stores **requests** for processing during outages
- Key pattern: `llm-provider-service:queue:requests:{queue_id}`
- Purpose: Resilience during provider outages
- Solution: Every successful request gets fresh LLM response

**The Fundamental Shift**: Redis moves from being a response cache (wrong) to being a request queue (correct). This is the most critical change.

### Task Summary

**Problem Statement**:
The LLM Provider Service currently caches and returns identical responses for identical content, which fundamentally violates the core requirements of both CJ Assessment Service and AI Feedback Service. In CJ Assessment, this creates an artificial "perfect rater" that corrupts the psychometric validity of Bradley-Terry scoring, which relies on natural judgment variation. For AI Feedback Service, users pay for fresh AI-generated feedback, not cached responses from previous requests.

**Current Behavior**:
- Cache is checked BEFORE any provider availability checks
- Identical essay content receives identical cached responses indefinitely
- Provider outages result in stale cached responses being served
- No mechanism to queue requests during outages for later processing

**Desired Outcome**:
- **Production**: Every request receives a fresh LLM response (no response caching)
- **Outages**: Requests are queued with "processing" status, not served from cache
- **Development**: Cached responses available only with explicit opt-in flag
- **Psychometric Validity**: Natural variation in judgments preserved for CJ methodology
- **Service Integrity**: Users receive the fresh AI responses they pay for

**Success Metrics**:
- Zero cached responses served in production environments
- 100% of requests during outages are queued, not cached
- CJ Assessment shows expected judgment variation patterns
- Development workflow maintains convenience with opt-in caching

### Current Cache Implementation Details

**Files and Components**:

1. **Cache Manager Protocol** (`protocols.py`):
   - `LLMCacheManagerProtocol` defines cache interface
   - Methods: `get_cached_response()`, `cache_response()`

2. **Cache Implementations**:
   - `RedisCacheRepositoryImpl` (`implementations/redis_cache_repository_impl.py`):
     - Uses Redis with configurable TTL (default 3600 seconds)
     - Cache key: `f"{prefix}:cache:llm:{provider}:{content_hash}"`
     - Content hash includes: prompt, essays, model, temperature
   - `LocalCacheManagerImpl` (`implementations/local_cache_manager_impl.py`):
     - In-memory LRU cache with size/entry limits
     - Fallback when Redis unavailable
   - `ResilientCacheManagerImpl` (`implementations/resilient_cache_manager_impl.py`):
     - Orchestrates Redis + Local fallback
     - Always tries Redis first, falls back to local

3. **Cache Integration** (`implementations/llm_orchestrator_impl.py`):
   - Line ~85: Checks cache before LLM call
   - Line ~120: Caches successful responses
   - Returns cached response immediately if found

4. **Configuration** (`config.py`):
   - `LLM_CACHE_ENABLED`: Default True
   - `LLM_CACHE_TTL`: Default 3600 seconds
   - `LOCAL_CACHE_SIZE_MB`: Default 100MB

**How It Currently Works**:
1. Request arrives with essays + prompt
2. Creates hash from content + model + temperature
3. Checks Redis cache → Local cache
4. If hit: Returns cached response immediately
5. If miss: Calls LLM, caches response, returns it
6. Same content = Same response forever (until TTL)

### Current Cache Design Problem

The current cache implementation **fundamentally breaks** the psychometric validity of CJ Assessment and the value proposition of AI Feedback Service:

**What's Wrong**:

- **Caches full responses** - Returns identical judgments for identical content
- **Breaks CJ methodology** - CJ requires natural variation in judgments, not perfect consistency
- **Violates service contract** - Users pay for fresh AI feedback, not cached responses
- **Misunderstands purpose** - Cache was meant for resilience, not primary response serving

**Psychometric Impact**:

- CJ was designed for human raters with natural inconsistency
- Bradley-Terry modeling expects and accounts for judgment variation
- Perfect consistency creates artificial "super-rater" that doesn't exist
- Corrupts the statistical validity of the assessment

### Correct Queue-Based Design

**Core Principle**: In production, NEVER serve cached LLM responses. Always provide fresh responses or queue for later processing.

**Production Request Flow**:

```text
Request arrives → LLM Provider available?
├─ YES → Fresh LLM call → Return result
└─ NO → Queue request
    ├─ Redis up → Queue in Redis (persistent) → Return 202 + queue_id
    └─ Redis down → Check local queue capacity
        ├─ Below 80% → Queue locally (volatile) → Return 202 + queue_id
        └─ At/above 80% → Return 503 "Queue at capacity"
```

**Key Design Elements**:

1. **NO Response Caching Ever** - Every successful request gets fresh LLM response
2. **Queue for Resilience** - Outages result in queuing, not cached responses
3. **Local Queue Fallback** - In-memory queue when Redis unavailable (with capacity limits)
4. **Explicit Rejection** - Return 503 when queue full, never silently drop requests
5. **Development Testing** - Use mock provider or lightweight response recorder for API validation

**Queue Capacity Management**:

- **High Watermark (80%)**: Start rejecting new requests
- **Low Watermark (60%)**: Resume accepting requests
- **Memory Limits**: Prevent OOM by tracking queue memory usage
- **No LRU Eviction**: Never silently drop queued requests

### Development Testing Strategy

Instead of maintaining complex cache infrastructure for development:

1. **Primary**: Use existing mock provider for day-to-day development
2. **API Validation**: Lightweight response recorder for occasional real API testing
3. **Cost Control**: Only use real providers when validating API changes

**Response Recorder** (Simple file-based logging):
```python
class DevelopmentResponseRecorder:
    """Records LLM responses to files for development only."""
    
    async def record_response(self, provider: str, request: Any, response: Any):
        if not self.enabled:
            return
        
        # Save to ./llm_response_logs/{provider}_{timestamp}.json
        # Human-readable format for API contract validation
        # Git-ignored directory
```

### Implementation Plan

#### ✅ Phase 1: Transform Redis from Response Cache to Request Queue (COMPLETED)

**Critical First Step**: Redis is currently our main handler - we must transform it carefully to maintain service availability.

- [x] Create new protocols alongside existing cache protocols:
  - `QueueManagerProtocol` for request queuing operations (added to `protocols.py`)
  - `QueueRepositoryProtocol` for storage operations (added to `protocols.py`)
  - Keep `LLMCacheManagerProtocol` temporarily for migration
- [x] Transform Redis implementation:
  - Created `RedisQueueRepositoryImpl` (`implementations/redis_queue_repository_impl.py`)
  - Changed key pattern: `{service}:queue:requests:{queue_id}` instead of cache keys
  - Stores `QueuedRequest` objects instead of responses
  - Added queue-specific operations: enqueue, dequeue, get_queue_size
  - Implemented TTL of 4 hours for queued requests
- [x] Create local queue implementation:
  - Created `LocalQueueManagerImpl` (`implementations/local_queue_manager_impl.py`)
  - No LRU eviction - explicit rejection when full
  - High/low watermark circuit breaker (80%/60%)
  - Memory tracking to prevent OOM
- [x] Created `ResilientQueueManagerImpl` (`implementations/resilient_queue_manager_impl.py`):
  - Primary: Redis queue for persistence
  - Fallback: Local queue with capacity management
  - Consistent behavior across both backends
- [x] Added queue configuration to `config.py`:
  - `QUEUE_MAX_SIZE`, `QUEUE_MAX_MEMORY_MB`
  - `QUEUE_HIGH_WATERMARK`, `QUEUE_LOW_WATERMARK`
  - `QUEUE_REQUEST_TTL_HOURS`
- [x] Wired up DI in `di.py`:
  - Added providers for queue components
  - Maintained cache providers for migration
- [x] Created `DevelopmentResponseRecorder` (`implementations/response_recorder_impl.py`):
  - Simple file-based logging for API validation
  - Added `llm_response_logs/` to `.gitignore`

#### Phase 2: Update LLM Orchestrator Request Flow

- [ ] Modify `llm_orchestrator_impl.py` request handling:
  ```
  Current: Check cache → Return cached OR call LLM
  New: Check provider → Call LLM OR queue request
  ```
- [ ] Implement new flow:
  1. Check LLM provider availability (circuit breaker)
  2. If available → Direct LLM call → Return fresh response
  3. If unavailable → Queue request → Return 202 with queue_id
  4. Never check/return cached responses (remove all cache logic)
- [ ] Add development response recorder:
  - Simple file-based response logging for API validation
  - Only active with `RECORD_LLM_RESPONSES=true` in development
  - Lightweight alternative to complex caching
- [ ] Remove all response caching code:
  - Delete cache manager references
  - Remove cache configuration
  - Clean up imports

#### Phase 3: Queue Processing & Status Management

- [ ] Add queue processor background task:
  - Poll queue for pending requests
  - Process when LLM providers recover
  - Respect request TTL (expire after 4 hours)
  - Update request status throughout lifecycle
- [ ] Implement status tracking:
  - Add `/api/v1/status/{queue_id}` endpoint
  - Track: QUEUED → PROCESSING → COMPLETED/FAILED/EXPIRED
  - Store results temporarily for client retrieval
- [ ] Add Kafka events for observability:
  - Request queued/dequeued
  - Processing started/completed/failed
  - Queue capacity warnings
  - TTL expirations

#### Phase 4: Cleanup - Remove All Cache Infrastructure

- [ ] Delete cache-related files:
  - `implementations/redis_cache_repository_impl.py`
  - `implementations/local_cache_manager_impl.py` 
  - `implementations/resilient_cache_manager_impl.py`
- [ ] Remove cache protocols from `protocols.py`:
  - `LLMCacheManagerProtocol`
  - `CacheRepositoryProtocol`
- [ ] Clean up `config.py`:
  - Remove all `CACHE_*` settings
  - Remove `LLM_CACHE_*` settings
- [ ] Update `di.py`:
  - Remove cache provider methods
  - Remove cache dependencies
- [ ] Delete cache tests:
  - All cache-related test files
  - Cache mocks and fixtures

#### Phase 5: Update API Contract

- [ ] Add `processing_mode` to request: `immediate` or `queue_if_unavailable`
- [ ] Return `202 Accepted` with queue ID for queued requests
- [ ] Add `/status/{queue_id}` endpoint
- [ ] Document webhook callback option

#### Phase 5: Integration Updates

- [ ] Update CJ Assessment Service to handle async responses
- [ ] Add queue status handling to AI Feedback Service
- [ ] WebSocket integration for real-time updates
- [ ] Frontend status communication

### Technical Specifications

**Queue Data Models**:

```python
class QueuedRequest(BaseModel):
    queue_id: UUID
    request_data: LLMComparisonRequest
    queued_at: datetime
    ttl: timedelta
    priority: int  # Higher for CJ Assessment
    status: QueueStatus  # QUEUED, PROCESSING, COMPLETED, EXPIRED
    retry_count: int = 0
    size_bytes: int  # For memory tracking

class QueueStatus(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    EXPIRED = "expired"
    FAILED = "failed"
```

**Queue Manager Protocol**:

```python
class QueueManagerProtocol(Protocol):
    async def enqueue(self, request: QueuedRequest) -> bool:
        """Returns False if queue full"""
        ...
    
    async def dequeue(self) -> Optional[QueuedRequest]:
        """Get next request to process"""
        ...
    
    async def get_status(self, queue_id: UUID) -> Optional[QueueStatus]:
        ...
    
    async def get_queue_stats(self) -> QueueStats:
        """Current size, capacity, memory usage"""
        ...
```

**Environment-Aware Configuration**:

```python
class Settings(BaseSettings):
    ENVIRONMENT: EnvironmentType  # from common_core.enums
    
    # Queue settings
    QUEUE_MAX_SIZE: int = 1000
    QUEUE_MAX_MEMORY_MB: int = 100
    QUEUE_HIGH_WATERMARK: float = 0.8  # Start rejecting at 80%
    QUEUE_LOW_WATERMARK: float = 0.6   # Resume at 60%
    
    # Development response recording
    RECORD_LLM_RESPONSES: bool = Field(
        default=False,
        description="Record LLM responses to files for API validation (dev only)"
    )
    
    @field_validator("RECORD_LLM_RESPONSES")
    def validate_response_recording(cls, v: bool, values: dict) -> bool:
        """Ensure response recording is only enabled in development."""
        if v and values.get("ENVIRONMENT") != "development":
            raise ValueError("Response recording only allowed in development")
        return v
    
    # Queue persistence
    QUEUE_USE_REDIS: bool = Field(
        default_factory=lambda: os.getenv("ENVIRONMENT") != "DEVELOPMENT"
    )
```

**Queue Full Response**:

```python
class QueueFullError(BaseModel):
    error: str = "Queue at capacity"
    queue_stats: Dict[str, Any] = {
        "current_size": 950,
        "max_size": 1000,
        "usage_percent": 95.0,
        "estimated_wait_hours": "2-4",
        "retry_after_seconds": 300
    }
    status_code: int = 503
```

### Migration Strategy

1. **Deploy queue infrastructure** alongside existing cache
2. **Add feature flags** for gradual rollout
3. **Update consumers** to handle async responses
4. **Disable response caching** in production
5. **Monitor and validate** psychometric properties

### Success Criteria

- [ ] No cached responses served in production
- [ ] CJ Assessment shows natural judgment variation
- [ ] Queue persistence works across restarts
- [ ] Clear status communication to users
- [ ] Development workflow unchanged
- [ ] Zero data loss during outages

## Future Enhancements (Phase 6)

After the cache refactor is complete, these remaining tasks should be addressed:

### Provider Enhancements

- [ ] **Update Other Providers for Structured Responses**:
  - [ ] OpenAI: Implement structured output with function calling or JSON mode enhancements
  - [ ] Google: Use Gemini's structured generation features
  - [ ] OpenRouter: Adapt based on underlying model capabilities
  - [ ] Ensure all providers return consistent structured format

### Performance & Monitoring

- [ ] **Performance Benchmarking**:
  - [ ] Measure latency overhead of service hop vs direct calls
  - [ ] Document acceptable performance thresholds
  - [ ] Optimize connection pooling and timeouts
  - [ ] Load test with concurrent CJ assessments

- [ ] **Enhanced Observability**:
  - [ ] Add detailed tracing for queue processing
  - [ ] Implement SLO monitoring for response times
  - [ ] Create dashboards for provider health metrics
  - [ ] Alert on queue depth and processing delays

### Service Cleanup

- [ ] **Remove Legacy Code from CJ Assessment**:
  - [ ] Delete old provider implementations after validation period
  - [ ] Remove unused LLM-related configuration
  - [ ] Update tests to reflect new architecture
  - [ ] Archive migration documentation

### Documentation & Training

- [ ] **Comprehensive Documentation**:
  - [ ] API migration guide for other services
  - [ ] Queue-based resilience pattern documentation
  - [ ] Runbook for handling provider outages
  - [ ] Performance tuning guide

## Integration Status

### ✅ CJ Assessment Service Integration

**Phase 1-3 Complete**:

- `LLMProviderServiceClient` implemented
- DI updated to use centralized service
- Configuration added for service URL
- Docker dependencies configured

**Phase 4 Complete**:

- ✅ DI wiring fixed - each provider gets correct implementation
- ✅ Anthropic tool use implemented for structured responses
- ✅ Integration tests passing (with cache design issues noted above)

## Key Learnings

1. **Import Patterns**: Full module paths required (`services.llm_provider_service.xxx`)
2. **Event System**: All events must be in `ProcessingEvent` enum
3. **DI Patterns**: Multiple providers of same type need special handling
4. **Protocol Compliance**: Return types must match protocol contracts exactly
5. **Cache Design**: Must align with service purpose, not just technical capability
6. **Psychometric Validity**: Technical decisions must respect assessment methodology

## Current Status

**✅ Completed (Phase 1)**:

- Queue infrastructure deployed alongside cache
- Redis transformed to store requests (not responses)
- Local queue with capacity management
- Development response recorder
- All 4 LLM providers with structured responses
- Mock provider for testing
- Health monitoring and metrics
- CJ Assessment integration functional

**⚠️ Critical Issues (Still Present)**:

- Response caching still active in orchestrator
- Cache checked before provider availability
- No queue processing when providers unavailable
- Dead code: entire cache infrastructure

**📋 Remaining Work**:

### Phase 2: Orchestrator Update (PRIORITY)
- Update `llm_orchestrator_impl.py` to use queue
- Remove cache checks from main flow
- Implement provider availability check first
- Add queue logic for unavailable providers

### Phase 3: Queue Processing
- Background task for processing queued requests
- Status tracking and updates
- TTL enforcement
- Result storage and retrieval

### Phase 4: Dead Code Removal
**Files to Delete**:
- `implementations/redis_cache_repository_impl.py`
- `implementations/local_cache_manager_impl.py`
- `implementations/resilient_cache_manager_impl.py`

**Code to Remove**:
- Cache protocols in `protocols.py`
- Cache configuration in `config.py`
- Cache providers in `di.py`
- Cache references in `llm_orchestrator_impl.py`

### Phase 5: API Updates
- Add `/api/v1/status/{queue_id}` endpoint
- Update response models for 202 Accepted
- Add queue statistics endpoint

### Phase 6: Integration
- Update consuming services for async responses
- Add retry logic for queue status checks

## Test Categories for Full Refactor

### 1. **Queue Infrastructure Tests** (Phase 1 - Ready to Write)
```python
# test_redis_queue_repository.py
- test_enqueue_dequeue_priority_order()
- test_ttl_expiration()
- test_memory_tracking()
- test_concurrent_access()
- test_queue_persistence()

# test_local_queue_manager.py
- test_capacity_limits()
- test_watermark_behavior()
- test_memory_limits()
- test_no_silent_eviction()
- test_thread_safety()

# test_resilient_queue_manager.py
- test_redis_fallback_to_local()
- test_recovery_when_redis_returns()
- test_combined_statistics()
- test_migration_tracking()
```

### 2. **Orchestrator Tests** (Phase 2)
```python
# test_llm_orchestrator_queue.py
- test_provider_check_before_queue()
- test_queue_when_provider_unavailable()
- test_no_cache_check_in_production()
- test_fresh_responses_always()
- test_queue_full_handling()
```

### 3. **Queue Processing Tests** (Phase 3)
```python
# test_queue_processor.py
- test_background_processing()
- test_ttl_enforcement()
- test_status_transitions()
- test_result_storage()
- test_retry_logic()
```

### 4. **API Integration Tests** (Phase 5)
```python
# test_queue_api.py
- test_202_accepted_response()
- test_queue_status_endpoint()
- test_queue_stats_endpoint()
- test_invalid_queue_id()
```

### 5. **End-to-End Tests**
```python
# test_e2e_queue_flow.py
- test_full_queue_lifecycle()
- test_provider_outage_scenario()
- test_redis_outage_scenario()
- test_both_outages_scenario()
```

### 6. **Performance Tests**
```python
# test_queue_performance.py
- test_high_volume_queuing()
- test_memory_usage_under_load()
- test_priority_ordering_performance()
- test_concurrent_queue_operations()
```

## Dead Code to Remove

### Cache Infrastructure (After Phase 2 Completion)
```
implementations/
├── redis_cache_repository_impl.py      # DELETE
├── local_cache_manager_impl.py         # DELETE  
├── resilient_cache_manager_impl.py     # DELETE
```

### Cache Configuration
- `config.py`: Remove `LLM_CACHE_*` settings
- `protocols.py`: Remove `LLMCacheManagerProtocol`, `LLMCacheRepositoryProtocol`
- `di.py`: Remove cache provider methods

## Implementation Roadmap

### Current Reality
- ✅ **Phase 1 Complete**: Queue infrastructure exists alongside cache
- ❌ **Cache Still Active**: `llm_orchestrator_impl.py` checks cache first (line ~108)
- ⚠️ **No Queue Usage**: Queue components created but not integrated

### What Actually Needs to Happen

**Phase 2: Fix Orchestrator (CRITICAL)**
```python
# Remove this (line ~108):
cached_response = await self.cache_manager.get_cached_response(cache_key)
if cached_response:
    return cached_response

# Replace with:
if not self._is_provider_available(provider):
    queued_request = await self.queue_manager.enqueue(request)
    if queued_request:
        return 202, queue_id
    else:
        return 503, "Queue at capacity"
```

**Phase 3: Add Queue Processing**
- Background task to process queued requests
- Check provider availability periodically
- Process queue when providers recover

**Phase 4: Remove Dead Code**
- Delete all cache implementations
- Remove cache from DI
- Clean up imports

## Technical Decisions

- **Mock First**: Early testing capability ✅
- **Event Everything**: Full observability from day one ✅
- **Cache by Default**: ❌ **WRONG** - Must refactor for queue-based resilience
- **Tool Use**: Anthropic's recommended approach for JSON structure ✅
- **Resilient Architecture**: Multiple fallback layers ✅

## API Endpoints

| Endpoint | Purpose | Status |
|----------|---------|--------|
| `POST /api/v1/comparison` | Generate comparison | ✅ Working (needs cache refactor) |
| `GET /api/v1/providers` | List providers | ✅ Working |
| `POST /api/v1/providers/{provider}/test` | Test provider | ✅ Working |
| `GET /healthz` | Health check | ✅ Working |
| `GET /metrics` | Prometheus metrics | ✅ Working |
| `GET /api/v1/status/{queue_id}` | Queue status | 🔄 Planned |

## Migration Benefits

- **Centralized Management**: All LLM logic in one place ✅
- **Cost Control**: Single point for tracking and limits ✅
- **Better Observability**: Unified metrics and monitoring ✅
- **Simplified Services**: CJ Assessment focuses on core logic ✅
- **Easier Updates**: Add providers without touching consumers ✅
- **Psychometric Validity**: Proper handling of judgment variation 🔄 (after refactor)