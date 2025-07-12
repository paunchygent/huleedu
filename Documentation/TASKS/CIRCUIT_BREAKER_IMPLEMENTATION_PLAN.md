# Circuit Breaker Implementation Plan for HuleEdu Microservices

## Executive Summary

This document outlines the implementation strategy for adding circuit breaker patterns to critical integration points in the HuleEdu microservices architecture. The circuit breaker pattern will prevent cascading failures and improve system resilience by temporarily blocking calls to failing services.

**Status**: Phase 1 (HTTP Clients) is COMPLETE. This document focuses on implementing the remaining phases.

## Important: What Already Exists

See `Documentation/TASKS/CIRCUIT_BREAKER_REMAINING_PHASES.md` for:
- Detailed list of completed components
- File paths for existing implementations
- Architectural rules to follow
- Specific implementation patterns

## Quick Reference

### Existing Infrastructure
- Circuit Breaker: `services/libs/huleedu_service_libs/resilience/circuit_breaker.py`
- Registry: `services/libs/huleedu_service_libs/resilience/registry.py`
- Wrapper: `services/libs/huleedu_service_libs/resilience/resilient_client.py`
- Error Context: `services/libs/huleedu_service_libs/error_handling/context_manager.py`

### Key Architectural Rules
- `.cursor/rules/040-service-implementation-guidelines.mdc` (Section 4.11)
- `.cursor/rules/020.11-service-libraries-architecture.mdc` (Section 6.6)

## Current State Analysis

### Critical Integration Points Identified

1. **HTTP Service-to-Service Communication**
   - Batch Orchestrator Service → Batch Conductor Service (pipeline resolution)
   - Spell Checker Service → Content Service (content fetching)
   - CJ Assessment Service → Content Service (content fetching)
   - API Gateway → All downstream services

2. **Kafka Event Publishing**
   - All services use `KafkaBus` for event publishing
   - Critical for maintaining event flow integrity
   - Single point of failure if Kafka becomes unavailable

3. **External API Calls**
   - CJ Assessment Service → AI providers (OpenAI, Anthropic, Google, OpenRouter)
   - High latency and potential for rate limiting

## Implementation Strategy

### Core Principles

1. **Protocol-Based Design**: Circuit breakers will be implemented as decorators/wrappers around existing protocol implementations
2. **Dependency Injection**: Integration through Dishka providers maintains clean architecture
3. **Configuration-Driven**: All thresholds and timeouts configurable per service
4. **Observable**: Full metrics and tracing integration

### Phase 1: HTTP Client Circuit Breakers (Week 1)

#### 1.1 Create Resilient Client Wrapper Pattern

**File to Create**: `services/libs/huleedu_service_libs/resilience/resilient_client.py`

```python
from typing import Protocol, TypeVar, Generic
from services.libs.huleedu_service_libs.resilience import CircuitBreaker

T = TypeVar('T', bound=Protocol)

class ResilientClientWrapper(Generic[T]):
    """Generic wrapper to add circuit breaker to any protocol implementation."""
    
    def __init__(self, delegate: T, circuit_breaker: CircuitBreaker):
        self._delegate = delegate
        self._circuit_breaker = circuit_breaker
    
    def __getattr__(self, name):
        """Wrap all methods with circuit breaker."""
        attr = getattr(self._delegate, name)
        if callable(attr):
            async def wrapped(*args, **kwargs):
                return await self._circuit_breaker.call(attr, *args, **kwargs)
            return wrapped
        return attr
```

#### 1.2 Implement for Batch Conductor Client

**File to Modify**: `services/batch_orchestrator_service/di.py`

```python
from services.libs.huleedu_service_libs.resilience import CircuitBreaker, CircuitBreakerRegistry

@provider(scope=Scope.APP)
def provide_circuit_breaker_registry(settings: Settings) -> CircuitBreakerRegistry:
    """Provide centralized circuit breaker registry."""
    registry = CircuitBreakerRegistry()
    
    # Configure circuit breaker for Batch Conductor Service
    if settings.CIRCUIT_BREAKER_ENABLED:
        registry.register(
            "batch_conductor",
            CircuitBreaker(
                name="batch_orchestrator.batch_conductor_client",
                failure_threshold=settings.BCS_CIRCUIT_BREAKER_FAILURE_THRESHOLD,
                recovery_timeout=timedelta(seconds=settings.BCS_CIRCUIT_BREAKER_RECOVERY_TIMEOUT),
                success_threshold=settings.BCS_CIRCUIT_BREAKER_SUCCESS_THRESHOLD,
                expected_exception=aiohttp.ClientError,
            )
        )
    
    return registry

@provider(scope=Scope.APP)
def provide_batch_conductor_client(
    http_session: aiohttp.ClientSession,
    settings: Settings,
    circuit_breaker_registry: CircuitBreakerRegistry,
) -> BatchConductorClientProtocol:
    """Provide batch conductor client with optional circuit breaker."""
    base_client = BatchConductorClientImpl(http_session, settings)
    
    if settings.CIRCUIT_BREAKER_ENABLED:
        circuit_breaker = circuit_breaker_registry.get("batch_conductor")
        if circuit_breaker:
            return ResilientClientWrapper(base_client, circuit_breaker)
    
    return base_client
```

#### 1.3 Add Configuration Settings

**File to Modify**: `services/batch_orchestrator_service/config.py`

```python
class Settings(BaseSettings):
    # Existing settings...
    
    # Circuit Breaker Settings
    CIRCUIT_BREAKER_ENABLED: bool = Field(
        default=True,
        description="Enable circuit breaker protection for external calls"
    )
    
    # Batch Conductor Service Circuit Breaker
    BCS_CIRCUIT_BREAKER_FAILURE_THRESHOLD: int = Field(
        default=5,
        description="Number of failures before opening circuit"
    )
    BCS_CIRCUIT_BREAKER_RECOVERY_TIMEOUT: int = Field(
        default=60,
        description="Seconds to wait before attempting recovery"
    )
    BCS_CIRCUIT_BREAKER_SUCCESS_THRESHOLD: int = Field(
        default=2,
        description="Successful calls needed to close circuit"
    )
```

#### 1.4 Implement Content Service Circuit Breakers

Apply the same pattern to:
- `services/spellchecker_service/protocol_implementations/content_client_impl.py`
- `services/cj_assessment_service/implementations/content_client_impl.py`

### Phase 2: Kafka Producer Circuit Breakers (Week 2)

#### 2.1 Create Resilient Kafka Bus

**File to Create**: `services/libs/huleedu_service_libs/kafka/resilient_kafka_bus.py`

```python
from typing import Optional
from services.libs.huleedu_service_libs.kafka_client import KafkaBus
from services.libs.huleedu_service_libs.resilience import CircuitBreaker

class ResilientKafkaBus(KafkaBus):
    """KafkaBus with optional circuit breaker protection."""
    
    def __init__(
        self,
        *args,
        circuit_breaker: Optional[CircuitBreaker] = None,
        fallback_handler: Optional[FallbackHandler] = None,
        **kwargs
    ):
        super().__init__(*args, **kwargs)
        self.circuit_breaker = circuit_breaker
        self.fallback_handler = fallback_handler
    
    async def publish(
        self,
        topic: str,
        envelope: EventEnvelope[T_EventPayload],
        key: str | None = None,
    ) -> None:
        """Publish with circuit breaker and fallback support."""
        if self.circuit_breaker:
            try:
                await self.circuit_breaker.call(
                    super().publish,
                    topic,
                    envelope,
                    key
                )
            except CircuitBreakerError:
                if self.fallback_handler:
                    await self.fallback_handler.handle_failed_publish(
                        topic, envelope, key
                    )
                else:
                    raise
        else:
            await super().publish(topic, envelope, key)
```

#### 2.2 Implement Fallback Handler

**File to Create**: `services/libs/huleedu_service_libs/kafka/fallback_handler.py`

```python
class LocalQueueFallbackHandler:
    """Queue events locally when Kafka is unavailable."""
    
    def __init__(self, max_queue_size: int = 1000):
        self.max_queue_size = max_queue_size
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=max_queue_size)
        self._recovery_task: Optional[asyncio.Task] = None
    
    async def handle_failed_publish(
        self,
        topic: str,
        envelope: EventEnvelope,
        key: Optional[str]
    ) -> None:
        """Queue failed message for later retry."""
        try:
            await self._queue.put_nowait({
                "topic": topic,
                "envelope": envelope,
                "key": key,
                "timestamp": datetime.utcnow()
            })
            logger.warning(
                f"Queued message for topic {topic}. Queue size: {self._queue.qsize()}"
            )
        except asyncio.QueueFull:
            logger.error(
                f"Fallback queue full. Dropping message for topic {topic}"
            )
            raise
```

### Phase 3: External API Circuit Breakers (Week 2-3)

#### 3.1 Implement for AI Provider Clients

**Files to Modify**:
- `services/cj_assessment_service/implementations/anthropic_provider_impl.py`
- `services/cj_assessment_service/implementations/openai_provider_impl.py`
- `services/cj_assessment_service/implementations/google_provider_impl.py`
- `services/cj_assessment_service/implementations/openrouter_provider_impl.py`

Apply circuit breaker pattern with provider-specific configurations:

```python
# In CJ Assessment Service DI
@provider(scope=Scope.APP)
def provide_ai_providers_with_circuit_breakers(
    settings: Settings,
    circuit_breaker_registry: CircuitBreakerRegistry,
) -> Dict[str, LLMProviderProtocol]:
    """Provide AI providers with circuit breaker protection."""
    providers = {}
    
    # Configure provider-specific circuit breakers
    for provider_name in ["anthropic", "openai", "google", "openrouter"]:
        circuit_breaker = CircuitBreaker(
            name=f"cj_assessment.{provider_name}_provider",
            failure_threshold=3,  # Lower threshold for external APIs
            recovery_timeout=timedelta(seconds=120),  # Longer recovery
            expected_exception=(aiohttp.ClientError, APIError),
        )
        circuit_breaker_registry.register(provider_name, circuit_breaker)
    
    # Wrap providers with circuit breakers
    # ... implementation details
```

### Phase 4: Monitoring and Alerting (Week 3)

#### 4.1 Add Prometheus Metrics

**File to Create**: `services/libs/huleedu_service_libs/observability/circuit_breaker_metrics.py`

```python
from prometheus_client import Counter, Gauge, Histogram

# Circuit breaker state gauge
circuit_breaker_state = Gauge(
    'circuit_breaker_state',
    'Current state of circuit breaker (0=closed, 1=open, 2=half-open)',
    ['service_name', 'circuit_name']
)

# Call metrics
circuit_breaker_calls_total = Counter(
    'circuit_breaker_calls_total',
    'Total circuit breaker calls by result',
    ['service_name', 'circuit_name', 'result']  # result: success, failure, blocked
)

# Fallback metrics
circuit_breaker_fallback_total = Counter(
    'circuit_breaker_fallback_total',
    'Total fallback actions triggered',
    ['service_name', 'circuit_name', 'fallback_type']
)

# Recovery metrics
circuit_breaker_recovery_attempts = Counter(
    'circuit_breaker_recovery_attempts',
    'Recovery attempts in half-open state',
    ['service_name', 'circuit_name', 'result']
)
```

#### 4.2 Update Grafana Dashboards

Add circuit breaker panels to service dashboards:
- Circuit state visualization
- Failure rate trends
- Recovery success rates
- Fallback queue sizes

#### 4.3 Configure Alerts

Already implemented in Phase 4 of observability enhancement:
- High error rate alerts
- Circuit breaker open alerts
- Fallback queue overflow alerts

### Phase 5: Testing and Validation (Week 3-4)

#### 5.1 Unit Tests

**File to Create**: `services/libs/huleedu_service_libs/resilience/tests/test_circuit_breaker.py`

```python
async def test_circuit_breaker_opens_after_threshold():
    """Test circuit opens after failure threshold."""
    circuit_breaker = CircuitBreaker(failure_threshold=3)
    failing_func = AsyncMock(side_effect=Exception("Service unavailable"))
    
    # First 3 calls should fail
    for _ in range(3):
        with pytest.raises(Exception):
            await circuit_breaker.call(failing_func)
    
    # 4th call should be blocked
    with pytest.raises(CircuitBreakerError):
        await circuit_breaker.call(failing_func)
    
    assert circuit_breaker.state == CircuitState.OPEN
```

#### 5.2 Integration Tests

**File to Create**: `tests/integration/test_circuit_breaker_integration.py`

Test scenarios:
1. Service failure and recovery
2. Kafka outage with fallback
3. External API rate limiting
4. Cascading failure prevention

#### 5.3 Chaos Engineering Tests

Create scripts to simulate failures:
- Network partitions
- Service crashes
- Slow responses
- Kafka broker failures

## Implementation Timeline

### Week 1: Foundation and HTTP Clients
- [ ] Implement resilient client wrapper pattern
- [ ] Add circuit breakers to Batch Conductor client
- [ ] Add circuit breakers to Content Service clients
- [ ] Configure settings and DI providers

### Week 2: Kafka and External APIs
- [ ] Implement resilient Kafka bus
- [ ] Create fallback handlers
- [ ] Add circuit breakers to AI provider clients
- [ ] Update service configurations

### Week 3: Monitoring and Testing
- [ ] Implement Prometheus metrics
- [ ] Update Grafana dashboards
- [ ] Write unit tests
- [ ] Create integration tests

### Week 4: Validation and Rollout
- [ ] Run chaos engineering tests
- [ ] Performance testing
- [ ] Documentation updates
- [ ] Gradual rollout plan

## Success Metrics

1. **Availability**: >99.9% service availability during downstream failures
2. **Recovery Time**: <2 minutes to recover from transient failures
3. **Error Reduction**: 50% reduction in cascading failures
4. **Performance**: <5ms overhead from circuit breaker logic

## Configuration Reference

### Environment Variables

```bash
# Global circuit breaker settings
CIRCUIT_BREAKER_ENABLED=true

# Service-specific settings
BCS_CIRCUIT_BREAKER_FAILURE_THRESHOLD=5
BCS_CIRCUIT_BREAKER_RECOVERY_TIMEOUT=60
BCS_CIRCUIT_BREAKER_SUCCESS_THRESHOLD=2

# Kafka circuit breaker
KAFKA_CIRCUIT_BREAKER_FAILURE_THRESHOLD=10
KAFKA_CIRCUIT_BREAKER_RECOVERY_TIMEOUT=30
KAFKA_FALLBACK_QUEUE_SIZE=1000

# External API circuit breakers
API_CIRCUIT_BREAKER_FAILURE_THRESHOLD=3
API_CIRCUIT_BREAKER_RECOVERY_TIMEOUT=120
```

## Rollback Plan

If issues arise during implementation:

1. **Feature Flag**: Use `CIRCUIT_BREAKER_ENABLED=false` to disable
2. **Gradual Rollback**: Disable per-service via configuration
3. **Monitoring**: Watch error rates and latency metrics
4. **Fallback Removal**: Remove fallback handlers if causing issues

## Next Steps

1. Review and approve implementation plan
2. Create implementation tickets in project tracker
3. Assign team members to each phase
4. Schedule weekly sync meetings
5. Begin Phase 1 implementation