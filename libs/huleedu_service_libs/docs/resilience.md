# Resilience Patterns

Circuit breakers, retries, and fault tolerance patterns for HuleEdu microservices.

## Overview

The resilience utilities provide battle-tested patterns for handling failures in distributed systems. These components help services maintain availability and graceful degradation when dependencies are unavailable or experiencing issues.

### Key Features

- **Circuit Breaker Pattern**: Automatic failure detection and recovery
- **Retry Logic**: Configurable retry strategies with exponential backoff
- **Timeout Management**: Configurable timeouts for external operations
- **Health Monitoring**: Integration with service health checks
- **Graceful Degradation**: Fallback mechanisms for service unavailability
- **Observable Failures**: Structured logging and metrics for failure tracking

## Circuit Breaker

**Module**: `resilience/circuit_breaker.py`  
**Purpose**: Automatic failure detection and service protection

### Basic Usage

```python
from huleedu_service_libs.resilience import CircuitBreaker, CircuitBreakerConfig

# Configure circuit breaker
config = CircuitBreakerConfig(
    failure_threshold=5,        # Trip after 5 failures
    recovery_timeout=60,        # Try recovery after 60 seconds
    success_threshold=3,        # Require 3 successes to close
    timeout=30.0               # 30 second operation timeout
)

# Create circuit breaker for external service
llm_circuit_breaker = CircuitBreaker("llm-provider", config)

async def call_llm_service(prompt: str) -> str:
    async with llm_circuit_breaker:
        # This call is protected by circuit breaker
        response = await llm_client.generate(prompt)
        return response.text
```

### Circuit Breaker States

- **CLOSED**: Normal operation, requests pass through
- **OPEN**: Failure threshold exceeded, requests fail immediately
- **HALF_OPEN**: Recovery testing, limited requests allowed

### Advanced Configuration

```python
from huleedu_service_libs.resilience import CircuitBreakerConfig

# High-availability service (strict)
ha_config = CircuitBreakerConfig(
    failure_threshold=3,        # Trip quickly
    recovery_timeout=30,        # Quick recovery attempts
    success_threshold=5,        # Require more successes
    timeout=10.0,              # Short timeout
    exception_whitelist=[      # Don't count certain errors
        ValidationError,
        AuthenticationError
    ]
)

# Batch processing service (tolerant)
batch_config = CircuitBreakerConfig(
    failure_threshold=10,       # Allow more failures
    recovery_timeout=300,       # Longer recovery window
    success_threshold=2,        # Fewer successes needed
    timeout=120.0,             # Longer operation timeout
    failure_rate_threshold=0.8  # Trip at 80% failure rate
)
```

### Error Handling

```python
from huleedu_service_libs.resilience import CircuitBreakerError, CircuitBreakerState

async def resilient_operation():
    try:
        result = await call_external_service()
        return result
    except CircuitBreakerError as e:
        if e.state == CircuitBreakerState.OPEN:
            logger.warning(
                "Circuit breaker is open, using cached result",
                service="external-service",
                correlation_id=get_correlation_id()
            )
            return get_cached_result()
        else:
            logger.error(
                "Circuit breaker failure",
                state=e.state.value,
                service="external-service",
                correlation_id=get_correlation_id()
            )
            raise ServiceUnavailableError("External service unavailable")
```

## Retry Patterns

**Module**: `resilience/retry.py`  
**Purpose**: Configurable retry logic with backoff strategies

### Basic Retry

```python
from huleedu_service_libs.resilience import retry_with_backoff, RetryConfig

config = RetryConfig(
    max_attempts=3,
    initial_delay=1.0,
    max_delay=30.0,
    backoff_multiplier=2.0,
    jitter=True
)

@retry_with_backoff(config)
async def flaky_operation() -> str:
    # This function will be retried automatically
    response = await external_api_call()
    if response.status != 200:
        raise RetryableError("API returned non-200 status")
    return response.data
```

### Conditional Retry

```python
from huleedu_service_libs.resilience import should_retry

def is_retryable_error(exception: Exception) -> bool:
    """Determine if error should trigger retry."""
    if isinstance(exception, (ConnectionError, TimeoutError)):
        return True
    if isinstance(exception, HTTPError) and exception.status in [502, 503, 504]:
        return True
    return False

@retry_with_backoff(
    config=RetryConfig(max_attempts=5),
    retry_predicate=is_retryable_error
)
async def selective_retry_operation():
    # Only retries on connection/timeout/5xx errors
    return await api_call()
```

### Exponential Backoff

```python
# Manual retry control
from huleedu_service_libs.resilience import ExponentialBackoff

backoff = ExponentialBackoff(
    initial_delay=0.5,
    max_delay=60.0,
    multiplier=2.0,
    jitter=True
)

async def manual_retry_operation():
    for attempt in range(5):
        try:
            return await risky_operation()
        except RetryableError as e:
            if attempt == 4:  # Last attempt
                raise
            
            delay = backoff.next_delay(attempt)
            logger.warning(
                "Operation failed, retrying",
                attempt=attempt + 1,
                delay_seconds=delay,
                error=str(e)
            )
            await asyncio.sleep(delay)
```

## Timeout Management

**Module**: `resilience/timeout.py`  
**Purpose**: Configurable timeouts with context management

### Operation Timeouts

```python
from huleedu_service_libs.resilience import timeout_operation

async def time_bounded_operation():
    async with timeout_operation(30.0):  # 30 second timeout
        # Long-running operation
        result = await complex_computation()
        return result
```

### Service-Specific Timeouts

```python
class LLMService:
    def __init__(self):
        self.timeouts = {
            "generation": 120.0,    # 2 minutes for text generation
            "embedding": 30.0,      # 30 seconds for embeddings
            "validation": 10.0      # 10 seconds for validation
        }
    
    async def generate_text(self, prompt: str) -> str:
        async with timeout_operation(self.timeouts["generation"]):
            return await self._generate(prompt)
    
    async def create_embedding(self, text: str) -> list[float]:
        async with timeout_operation(self.timeouts["embedding"]):
            return await self._embed(text)
```

## Fallback Patterns

### Service Degradation

```python
from huleedu_service_libs.resilience import with_fallback

class ContentService:
    async def get_content_with_enrichment(self, content_id: str) -> dict:
        # Try enhanced content first
        try:
            return await self._get_enriched_content(content_id)
        except ServiceUnavailableError:
            logger.warning("Enrichment service unavailable, using basic content")
            return await self._get_basic_content(content_id)
    
    @with_fallback(fallback_value={"recommendations": []})
    async def get_recommendations(self, user_id: str) -> dict:
        # Falls back to empty recommendations if service fails
        return await recommendation_service.get_recommendations(user_id)
```

### Cached Fallbacks

```python
async def get_with_cache_fallback(key: str) -> dict:
    try:
        # Try primary data source
        async with timeout_operation(10.0):
            return await primary_service.get_data(key)
    except (TimeoutError, ServiceUnavailableError):
        # Fall back to cache
        cached_data = await redis_client.get(f"cache:{key}")
        if cached_data:
            logger.info("Using cached fallback", key=key)
            return json.loads(cached_data)
        
        # Final fallback
        logger.warning("No cached data available", key=key)
        return {"error": "Data temporarily unavailable"}
```

## Health-Aware Operations

### Dependency Health Checks

```python
from huleedu_service_libs.resilience import HealthAwareCircuitBreaker

class ServiceManager:
    def __init__(self):
        self.llm_breaker = HealthAwareCircuitBreaker(
            "llm-service",
            health_check_url="http://llm-service:8080/health",
            health_check_interval=30.0
        )
    
    async def process_with_llm(self, data: dict) -> dict:
        if not await self.llm_breaker.is_healthy():
            logger.warning("LLM service unhealthy, using local processing")
            return await self._local_processing(data)
        
        async with self.llm_breaker:
            return await self._llm_processing(data)
```

## Integration Patterns

### Service Client with Resilience

```python
from huleedu_service_libs.resilience import ResilientHttpClient

class ExternalServiceClient:
    def __init__(self):
        self.client = ResilientHttpClient(
            base_url="https://api.external.com",
            circuit_breaker_config=CircuitBreakerConfig(
                failure_threshold=5,
                recovery_timeout=60
            ),
            retry_config=RetryConfig(
                max_attempts=3,
                initial_delay=1.0
            ),
            timeout=30.0
        )
    
    async def get_data(self, resource_id: str) -> dict:
        # Automatically retries, respects circuit breaker, times out
        response = await self.client.get(f"/data/{resource_id}")
        return response.json()
```

### Worker Resilience

```python
class ResilientEventProcessor:
    def __init__(self):
        self.llm_breaker = CircuitBreaker("llm-service", ha_config)
        
    async def process_essay_event(self, envelope: EventEnvelope):
        try:
            async with self.llm_breaker:
                result = await llm_service.process_essay(envelope.data)
                await self._publish_success(result)
        except CircuitBreakerError:
            # Service unavailable, queue for later processing
            await self._queue_for_retry(envelope)
        except Exception as e:
            logger.error("Processing failed", error=str(e))
            await self._handle_processing_error(envelope, e)
```

## Monitoring and Metrics

### Circuit Breaker Metrics

```python
from prometheus_client import Counter, Gauge, Histogram

# Circuit breaker metrics
circuit_breaker_state = Gauge(
    "circuit_breaker_state",
    "Circuit breaker state (0=closed, 1=open, 2=half_open)",
    ["service", "breaker_name"]
)

circuit_breaker_trips = Counter(
    "circuit_breaker_trips_total",
    "Total circuit breaker trips",
    ["service", "breaker_name"]
)

operation_duration = Histogram(
    "resilient_operation_duration_seconds",
    "Duration of resilient operations",
    ["service", "operation", "outcome"]
)
```

### Failure Tracking

```python
async def monitored_operation():
    start_time = time.time()
    outcome = "success"
    
    try:
        async with circuit_breaker:
            result = await external_operation()
            return result
    except CircuitBreakerError:
        outcome = "circuit_breaker_open"
        raise
    except TimeoutError:
        outcome = "timeout"
        raise
    except Exception:
        outcome = "error"
        raise
    finally:
        duration = time.time() - start_time
        operation_duration.labels(
            service="content_service",
            operation="external_call",
            outcome=outcome
        ).observe(duration)
```

## Configuration

### Environment Variables

- `CIRCUIT_BREAKER_ENABLED`: Enable/disable circuit breakers globally
- `DEFAULT_TIMEOUT`: Default operation timeout in seconds
- `RETRY_MAX_ATTEMPTS`: Default maximum retry attempts
- `CIRCUIT_BREAKER_FAILURE_THRESHOLD`: Default failure threshold
- `CIRCUIT_BREAKER_RECOVERY_TIMEOUT`: Default recovery timeout

### Service-Specific Configuration

```python
# In settings.py
from pydantic import BaseSettings

class ResilienceSettings(BaseSettings):
    circuit_breaker_enabled: bool = True
    default_timeout: float = 30.0
    llm_service_timeout: float = 120.0
    batch_operation_timeout: float = 300.0
    
    retry_max_attempts: int = 3
    retry_initial_delay: float = 1.0
    retry_max_delay: float = 60.0
    
    circuit_breaker_failure_threshold: int = 5
    circuit_breaker_recovery_timeout: int = 60
```

## Testing

### Circuit Breaker Testing

```python
import pytest
from huleedu_service_libs.resilience import CircuitBreaker, CircuitBreakerState

async def test_circuit_breaker_opens_after_failures():
    config = CircuitBreakerConfig(failure_threshold=3)
    breaker = CircuitBreaker("test-service", config)
    
    # Trigger failures
    for _ in range(3):
        with pytest.raises(Exception):
            async with breaker:
                raise ConnectionError("Service down")
    
    # Circuit breaker should now be open
    assert breaker.state == CircuitBreakerState.OPEN
    
    # Next call should fail immediately
    with pytest.raises(CircuitBreakerError):
        async with breaker:
            pass  # This won't execute
```

### Retry Testing

```python
from unittest.mock import AsyncMock

async def test_retry_success_after_failures():
    mock_operation = AsyncMock()
    mock_operation.side_effect = [
        ConnectionError("Fail 1"),
        ConnectionError("Fail 2"),
        "Success"  # Third attempt succeeds
    ]
    
    @retry_with_backoff(RetryConfig(max_attempts=3))
    async def operation():
        return await mock_operation()
    
    result = await operation()
    assert result == "Success"
    assert mock_operation.call_count == 3
```

## Best Practices

1. **Configure Appropriately**: Set thresholds based on service characteristics
2. **Monitor Circuit Breakers**: Track state changes and trip events
3. **Implement Fallbacks**: Always have degraded functionality available
4. **Use Appropriate Timeouts**: Set timeouts based on operation complexity
5. **Selective Retries**: Only retry on transient errors
6. **Structured Logging**: Log all resilience events with context
7. **Test Failure Scenarios**: Verify resilience patterns work correctly
8. **Graceful Degradation**: Design for partial functionality

## Anti-Patterns to Avoid

1. **Ignoring Circuit Breaker State**: Always handle CircuitBreakerError
2. **Retrying Non-Retryable Errors**: Don't retry validation or auth errors
3. **Infinite Retries**: Always set maximum attempt limits
4. **Missing Fallbacks**: Provide alternative responses for failures
5. **Synchronous Fallbacks**: Keep fallback operations async
6. **Resource Leaks**: Properly handle timeouts and cleanup
7. **Generic Error Handling**: Use specific exception types
8. **Missing Observability**: Track and monitor all resilience events
