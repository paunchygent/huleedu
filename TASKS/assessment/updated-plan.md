---
id: "updated-plan"
title: "Redis Caching Solution for BCS Duplicate Calls - Updated Plan"
type: "task"
status: "research"
priority: "medium"
domain: "assessment"
service: ""
owner_team: "agents"
owner: ""
program: ""
created: "2025-10-30"
last_updated: "2025-11-17"
related: []
labels: []
---
## Executive Summary

This document outlines the implementation of a Redis caching layer to eliminate duplicate BCS (Batch Conductor Service) calls in the Batch Orchestrator Service (BOS). The solution addresses architectural concerns around error handling, layering, configuration, and resilience.

## Problem Statement

### Current Behavior

- BOS makes two identical calls to BCS for each pipeline request:
  1. **Preflight endpoint** (`batch_routes.py:351`) - validates credits before execution
  2. **Kafka handler** (`client_pipeline_request_handler.py:212`) - executes the pipeline
- These calls occur ~9ms apart and generate duplicate "Phase skipped" events
- While the system handles duplicates via idempotency, this creates unnecessary load

### Root Cause

The preflight and handler operate independently without shared state, leading to redundant BCS resolution calls.

## Solution Architecture

### Design Principles

1. **Cache-aside pattern**: Cache failures never block core operations
2. **Error transparency**: Delegate errors propagate unchanged
3. **Degraded mode support**: Cache serves hits even when circuit breaker is open
4. **Configuration-driven**: All timeouts and flags are tunable
5. **Observability**: Clear logging and metrics for monitoring

### Layering Architecture

```
Request Flow:
    ↓
[CachedBatchConductorClient]     <- Layer 3: Cache (outermost)
    ↓ (cache miss)
[CircuitBreakerBatchConductorClient]  <- Layer 2: Circuit Breaker
    ↓ (if closed)
[BatchConductorClientImpl]        <- Layer 1: Base HTTP client
    ↓
[BCS Service]
```

**Critical**: Cache wraps circuit breaker, not vice versa. This allows:

- Cache hits to be served even when circuit breaker is open
- Reduced pressure on downstream services during degraded states
- Clear separation of caching concerns from resilience concerns

## Implementation Details

### 1. Configuration Updates

**File**: `services/batch_orchestrator_service/config.py`

Add after line 83 (following other BCS configuration):

```python
# BCS Cache Configuration
BCS_CACHE_TTL_SECONDS: int = Field(
    default=10,
    description="TTL for BCS pipeline resolution cache in seconds. "
                "Should be long enough to cover preflight->handler gap but "
                "short enough to avoid stale data issues.",
    ge=1,  # Minimum 1 second
    le=300,  # Maximum 5 minutes
)
BCS_CACHE_ENABLED: bool = Field(
    default=True,
    description="Enable Redis caching for BCS pipeline resolutions. "
                "Disable for debugging or if Redis is unavailable."
)
```

**Rationale**:

- Default 10 seconds covers the typical preflight→handler gap (< 100ms) with margin
- Configurable for production tuning without code changes
- Bounded to prevent misconfiguration (1s - 5m range)
- Feature flag allows quick disable if issues arise

### 2. Cache Implementation

#### 2.1 Metrics registration (must be completed before wiring cache)

**File**: `services/batch_orchestrator_service/metrics.py`

- **Add counters** inside `_create_metrics()` so cache behaviour is observable:

  ```python
  "bos_bcs_cache_hits_total": Counter(
      "bos_bcs_cache_hits_total",
      "Total BCS cache hits served by BOS",
      ["service"],
      registry=REGISTRY,
  ),
  "bos_bcs_cache_misses_total": Counter(
      "bos_bcs_cache_misses_total",
      "Total BCS cache misses in BOS",
      ["service"],
      registry=REGISTRY,
  ),
  "bos_bcs_cache_errors_total": Counter(
      "bos_bcs_cache_errors_total",
      "Total Redis errors encountered by the BCS cache",
      ["service", "operation"],
      registry=REGISTRY,
  ),
  "bos_bcs_cache_corrupted_total": Counter(
      "bos_bcs_cache_corrupted_total",
      "Total corrupted cache entries evicted by the BCS cache",
      ["service"],
      registry=REGISTRY,
  ),
  ```

- **Update `_get_existing_metrics()`** to map the new logical keys so re-imports reuse existing collectors.
- **Ensure `get_metrics()`** returns the counters (including fallback path when metrics already registered) to avoid KeyErrors when the cache wrapper retrieves them.

**File**: `services/batch_orchestrator_service/implementations/cached_batch_conductor_client.py`

```python
"""
Caching wrapper for Batch Conductor Service client.

This module implements a cache-aside pattern for BCS pipeline resolutions,
eliminating duplicate calls between preflight and handler operations.
"""
from __future__ import annotations

import json
from typing import Any

from common_core.pipeline_models import PhaseName
from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.protocols import AtomicRedisClientProtocol
from services.batch_orchestrator_service.config import Settings
from services.batch_orchestrator_service.metrics import get_metrics
from services.batch_orchestrator_service.protocols import BatchConductorClientProtocol

logger = create_service_logger("bos.client.batch_conductor.cache")


class CachedBatchConductorClient(BatchConductorClientProtocol):
    """BCS client with Redis caching for pipeline resolutions.

    This wrapper implements a cache-aside pattern to eliminate duplicate
    BCS calls that occur between preflight credit checks and actual
    pipeline execution.

    Architecture Decisions:
    - Cache wraps the entire client stack (including circuit breaker)
    - Redis failures are non-blocking (cache-aside pattern)
    - Delegate exceptions propagate unchanged
    - Corrupted entries are evicted and treated as misses

    Cache Key Format:
        bcs_resolution:{batch_id}:{pipeline}:{correlation_id}

    This ensures uniqueness per request flow while remaining human-readable
    for debugging purposes.
    """

    def __init__(
        self,
        delegate: BatchConductorClientProtocol,
        redis_client: AtomicRedisClientProtocol,
        settings: Settings,
    ) -> None:
        """Initialize cached BCS client.

        Args:
            delegate: The underlying BCS client (may include circuit breaker)
            redis_client: Redis client for caching operations
            settings: Service settings including cache configuration
        """
        self._delegate = delegate
        self._redis_client = redis_client
        self._cache_ttl = settings.BCS_CACHE_TTL_SECONDS
        self._cache_enabled = settings.BCS_CACHE_ENABLED
        self._service_name = settings.SERVICE_NAME

        metrics = get_metrics()
        self._cache_hits = metrics["bos_bcs_cache_hits_total"].labels(service=self._service_name)
        self._cache_misses = metrics["bos_bcs_cache_misses_total"].labels(service=self._service_name)
        self._cache_errors = metrics["bos_bcs_cache_errors_total"]
        self._cache_corrupted = metrics["bos_bcs_cache_corrupted_total"].labels(
            service=self._service_name
        )

        logger.info(
            "Initialized CachedBatchConductorClient",
            extra={
                "cache_enabled": self._cache_enabled,
                "cache_ttl_seconds": self._cache_ttl,
                "service": self._service_name,
            }
        )

    async def resolve_pipeline(
        self, batch_id: str, requested_pipeline: PhaseName, correlation_id: str
    ) -> dict[str, Any]:
        """Request pipeline resolution with caching.

        Flow:
        1. If caching disabled, bypass to delegate
        2. Check cache (Redis failures are caught and logged)
        3. On hit: return cached result
        4. On miss: call delegate (errors propagate)
        5. Cache successful results (Redis failures don't block)

        Args:
            batch_id: Unique identifier of the target batch
            requested_pipeline: The pipeline phase to resolve
            correlation_id: Request correlation ID for tracing

        Returns:
            BCS response containing resolved pipeline and analysis

        Raises:
            ValueError: If BCS returns invalid response (from delegate)
            aiohttp.ClientError: If HTTP communication fails (from delegate)
            CircuitBreakerError: If circuit breaker is open (from delegate)
        """
        # Bypass if caching disabled
        if not self._cache_enabled:
            self._cache_misses.inc()
            return await self._delegate.resolve_pipeline(
                batch_id, requested_pipeline, correlation_id
            )

        # Generate deterministic cache key
        cache_key = self._generate_cache_key(batch_id, requested_pipeline, correlation_id)

        # Attempt cache retrieval (non-blocking)
        cached_result = await self._safe_cache_get(cache_key, batch_id, correlation_id)
        if cached_result is not None:
            return cached_result

        self._cache_misses.inc()

        # Cache miss - call delegate
        # IMPORTANT: Let delegate exceptions propagate unchanged
        logger.debug(
            "BCS resolution cache miss, calling delegate",
            extra={
                "cache_key": cache_key,
                "batch_id": batch_id,
                "pipeline": requested_pipeline.value,
                "correlation_id": correlation_id,
            }
        )

        result = await self._delegate.resolve_pipeline(
            batch_id, requested_pipeline, correlation_id
        )

        # Cache successful result (best-effort, non-blocking)
        await self._safe_cache_set(cache_key, result, batch_id, correlation_id)

        return result

    async def report_phase_completion(
        self,
        batch_id: str,
        completed_phase: PhaseName,
        success: bool = True,
    ) -> None:
        """Report phase completion without caching.

        This operation is best-effort and doesn't benefit from caching.

        Args:
            batch_id: Unique identifier of the batch
            completed_phase: The phase that completed
            success: Whether the phase succeeded
        """
        # Pass through without caching
        return await self._delegate.report_phase_completion(
            batch_id, completed_phase, success
        )

    def _generate_cache_key(
        self, batch_id: str, pipeline: PhaseName, correlation_id: str
    ) -> str:
        """Generate cache key for pipeline resolution.

        Format: bcs_resolution:{batch_id}:{pipeline}:{correlation_id}

        Args:
            batch_id: Batch identifier
            pipeline: Pipeline phase name
            correlation_id: Correlation ID

        Returns:
            Formatted cache key
        """
        return f"bcs_resolution:{batch_id}:{pipeline.value}:{correlation_id}"

    async def _safe_cache_get(
        self, key: str, batch_id: str, correlation_id: str
    ) -> dict[str, Any] | None:
        """Safely retrieve and parse cached value.

        Handles:
        - Redis connection failures
        - Missing keys (normal cache miss)
        - Corrupted values (evicts and treats as miss)

        Args:
            key: Cache key
            batch_id: Batch ID for logging context
            correlation_id: Correlation ID for logging context

        Returns:
            Parsed cache value or None on any failure
        """
        # Guard Redis get operation
        try:
            cached_value = await self._redis_client.get(key)
        except Exception as e:
            # Redis failure - log and proceed without cache
            logger.warning(
                "Redis get failed during BCS cache lookup",
                extra={
                    "key": key,
                    "batch_id": batch_id,
                    "correlation_id": correlation_id,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
                exc_info=True,
            )
            self._cache_errors.labels(service=self._service_name, operation="get").inc()
            return None

        # Handle cache miss (normal case)
        if cached_value is None:
            return None

        # Guard JSON parsing
        try:
            parsed_result = json.loads(cached_value)

            # Validate it's a dict (basic sanity check)
            if not isinstance(parsed_result, dict):
                raise TypeError(f"Expected dict, got {type(parsed_result).__name__}")

            logger.debug(
                "BCS resolution cache hit",
                extra={
                    "key": key,
                    "batch_id": batch_id,
                    "correlation_id": correlation_id,
                }
            )
            self._cache_hits.inc()
            return parsed_result

        except (json.JSONDecodeError, TypeError, AttributeError) as e:
            # Corrupted cache entry - evict and treat as miss
            logger.warning(
                "Corrupted BCS cache entry detected, evicting",
                extra={
                    "key": key,
                    "batch_id": batch_id,
                    "correlation_id": correlation_id,
                    "error": str(e),
                    "error_type": type(e).__name__,
                }
            )

            self._cache_corrupted.inc()

            # Best-effort eviction
            try:
                await self._redis_client.delete_key(key)
            except Exception:
                self._cache_errors.labels(service=self._service_name, operation="delete").inc()
                pass  # Eviction failure is non-critical

            return None

    async def _safe_cache_set(
        self, key: str, value: dict[str, Any], batch_id: str, correlation_id: str
    ) -> None:
        """Safely cache a value with TTL.

        Redis write failures are logged but don't block operation.

        Args:
            key: Cache key
            value: Value to cache
            batch_id: Batch ID for logging context
            correlation_id: Correlation ID for logging context
        """
        # Guard JSON serialization
        try:
            serialized = json.dumps(value)
        except (TypeError, ValueError) as e:
            logger.error(
                "Failed to serialize BCS response for caching",
                extra={
                    "key": key,
                    "batch_id": batch_id,
                    "correlation_id": correlation_id,
                    "error": str(e),
                }
            )
            return

        # Guard Redis set operation
        try:
            await self._redis_client.setex(key, self._cache_ttl, serialized)
            logger.debug(
                "Cached BCS resolution",
                extra={
                    "key": key,
                    "ttl_seconds": self._cache_ttl,
                    "batch_id": batch_id,
                    "correlation_id": correlation_id,
                }
            )
        except Exception as e:
            # Redis write failure - log but continue
            logger.warning(
                "Redis setex failed during BCS cache write",
                extra={
                    "key": key,
                    "batch_id": batch_id,
                    "correlation_id": correlation_id,
                    "ttl_seconds": self._cache_ttl,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
                exc_info=True,
            )
            self._cache_errors.labels(service=self._service_name, operation="setex").inc()
```

### 3. Dependency Injection Updates

**File**: `services/batch_orchestrator_service/di.py`

Replace the existing `provide_batch_conductor_client` method (lines 310-327):

```python
@provide(scope=Scope.APP)
def provide_batch_conductor_client(
    self,
    http_session: ClientSession,
    settings: Settings,
    circuit_breaker_registry: CircuitBreakerRegistry,
    redis_client: AtomicRedisClientProtocol,  # Added dependency
) -> BatchConductorClientProtocol:
    """Provide BCS HTTP client with circuit breaker and caching.

    Layering Architecture (order matters for degraded mode support):

    1. Base Client (innermost):
       - Handles actual HTTP communication with BCS
       - Raises errors on bad responses

    2. Circuit Breaker (middle):
       - Protects base client from cascading failures
       - Opens on repeated failures, closes after success
       - Raises CircuitBreakerError when open

    3. Cache (outermost):
       - Checks Redis before calling delegate
       - Can serve cached results even when breaker is open
       - Redis failures don't block operations

    This ordering ensures maximum availability: cached results can be
    served even during BCS outages (when circuit breaker is open).

    Args:
        http_session: aiohttp session for HTTP calls
        settings: Service configuration
        circuit_breaker_registry: Registry of circuit breakers
        redis_client: Redis client for caching

    Returns:
        Configured BCS client with appropriate wrappers
    """
    # Layer 1: Base HTTP client
    base_client = BatchConductorClientImpl(http_session, settings)

    # Layer 2: Add circuit breaker protection if enabled
    protected_client: BatchConductorClientProtocol = base_client
    if settings.CIRCUIT_BREAKER_ENABLED:
        circuit_breaker = circuit_breaker_registry.get("batch_conductor")
        if circuit_breaker:
            protected_client = CircuitBreakerBatchConductorClient(
                delegate=base_client,
                circuit_breaker=circuit_breaker
            )
            logger.info(
                "BCS client wrapped with circuit breaker",
                extra={"service": settings.SERVICE_NAME}
            )

    # Layer 3: Add caching layer (outermost) if enabled
    if settings.BCS_CACHE_ENABLED:
        from services.batch_orchestrator_service.implementations.cached_batch_conductor_client import (
            CachedBatchConductorClient
        )

        final_client = CachedBatchConductorClient(
            delegate=protected_client,
            redis_client=redis_client,
            settings=settings
        )
        logger.info(
            "BCS client wrapped with Redis cache",
            extra={
                "cache_ttl": settings.BCS_CACHE_TTL_SECONDS,
                "service": settings.SERVICE_NAME
            }
        )
        return final_client

    return protected_client
```

## Test Strategy

### Unit Tests

**File**: `services/batch_orchestrator_service/tests/unit/test_cached_batch_conductor_client.py`

Test cases:

1. **Cache flow**:
   - Cache miss → delegate call → cache set
   - Cache hit returns without calling delegate
   - TTL expiration leads to cache miss

2. **Error handling**:
   - Delegate ValueError propagates unchanged
   - Delegate ClientError propagates unchanged
   - CircuitBreakerError propagates unchanged

3. **Redis failures**:
   - Get failure → calls delegate (non-blocking)
   - Set failure → returns result anyway (non-blocking)
   - Connection timeout → calls delegate

4. **Corruption handling**:
   - Invalid JSON → evict → call delegate
   - Non-dict value → evict → call delegate
   - Null bytes in value → evict → call delegate

5. **Configuration**:
   - Cache disabled bypasses all logic
   - TTL from settings is respected

### Integration Tests

**File**: `services/batch_orchestrator_service/tests/integration/test_cache_circuit_breaker_integration.py`

Test cases:

1. **Layering verification**:
   - Circuit breaker open + cache hit = returns cached value
   - Circuit breaker open + cache miss = raises CircuitBreakerError
   - Circuit breaker closed + cache operations work normally

2. **End-to-end flow**:
   - Preflight call → cache miss → BCS call → cache set
   - Handler call → cache hit → no BCS call
   - Verify only one actual BCS call made

### Functional Test Verification

**Existing test**: `tests/functional/test_e2e_cj_after_nlp_with_pruning.py`

Expected log output after implementation:

```
22:08:57.970 - BCS resolution cache miss, calling delegate
22:08:57.981 - Cached BCS resolution
22:08:58.054 - BCS resolution cache hit
```

Metrics to verify:

- BCS actual calls: 1 (down from 2)
- Cache hits: 1
- Cache misses: 1
- Duplicate "Phase skipped" events: 0 (down from duplicate set)

## Rollout Plan

### Phase 1: Development Testing

1. Implement code changes
2. Run unit tests
3. Run integration tests
4. Verify in local Docker environment

### Phase 2: Staging Deployment

1. Deploy with `BCS_CACHE_ENABLED=true`, `BCS_CACHE_TTL_SECONDS=10`
2. Monitor Redis memory usage
3. Verify cache hit rates via logs
4. Check for any error spikes

### Phase 3: Production Deployment

1. Deploy with feature flag off initially (`BCS_CACHE_ENABLED=false`)
2. Enable for small percentage of traffic
3. Monitor metrics:
   - Cache hit ratio (target: ~50% for duplicate calls)
   - Redis latency (should be < 5ms)
   - Error rates (should not increase)
4. Gradually increase to 100% if metrics are healthy

### Rollback Strategy

If issues arise:

1. Set `BCS_CACHE_ENABLED=false` (immediate effect)
2. No code changes or deployments required
3. Cache entries expire naturally per TTL

## Monitoring & Observability

### Metrics to Track

1. **Cache effectiveness**:
   - `bos_bcs_cache_hits_total` (counter)
   - `bos_bcs_cache_misses_total` (counter)
   - `bos_bcs_cache_hit_ratio` (gauge)

2. **Cache health**:
   - `bos_redis_errors_total{operation="get"}` (counter)
   - `bos_redis_errors_total{operation="set"}` (counter)
   - `bos_cache_corrupted_entries_total` (counter)

3. **Performance**:
   - `bos_bcs_resolution_duration_seconds{cached="true"}` (histogram)
   - `bos_bcs_resolution_duration_seconds{cached="false"}` (histogram)

### Alerts

1. **High cache miss ratio**: If hit ratio < 30% for 5 minutes (indicates TTL too short)
2. **Redis connection failures**: If error rate > 1% for 5 minutes
3. **High corruption rate**: If > 10 corrupted entries per minute (indicates serialization issue)

## Risk Analysis

### Risks and Mitigations

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Redis outage | Cache misses only | Low | Cache-aside pattern ensures operations continue |
| Cache key collision | Wrong data served | Very Low | Correlation ID in key ensures uniqueness |
| TTL too short | Duplicate calls persist | Medium | Configurable TTL, monitor hit rates |
| TTL too long | Stale data served | Low | 10s default is conservative, max 5m limit |
| Memory exhaustion | Redis OOM | Very Low | TTL ensures automatic cleanup |
| Serialization failure | Cache write fails | Low | Non-blocking, logged, operations continue |

## Success Criteria

1. **Functional**: Duplicate BCS calls eliminated (verified via logs)
2. **Performance**: No increase in p99 latency for pipeline requests
3. **Reliability**: No increase in error rates
4. **Observability**: Cache hit ratio > 40% for duplicate scenarios
5. **Operational**: Can disable via config without deployment

## Production Metrics

### Required for Deployment

**Prometheus Metrics Integration**: Add cache observability metrics following existing patterns

- `bos_bcs_cache_hits_total` (counter)
- `bos_bcs_cache_misses_total` (counter)
- Implementation follows existing metrics patterns in `services/batch_orchestrator_service/metrics.py`

## Conclusion

This solution provides a robust, production-ready approach to eliminating duplicate BCS calls through intelligent caching. The architecture prioritizes availability and error transparency while maintaining operational flexibility through configuration. The implementation follows established patterns in the codebase and integrates cleanly with existing infrastructure.
