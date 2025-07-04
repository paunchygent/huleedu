# LLM Provider Service - Cost Tracking Implementation TODO

## Overview
Implement downstream cost tracking event publishing for Result Aggregator Service to handle persistent cost storage, billing, and analytics.

## Current State
✅ **Completed:**
- Cost estimation in orchestrator (`_estimate_cost` method)
- Cost data in `LLMRequestCompletedV1` events
- Real-time cost metrics via Prometheus
- `LLMCostTrackingV1` event model added to common_core
- Event enum and topic mapping configured

## TODO: Implement Cost Tracking Event Publishing

### 1. Add Cost Tracking Event Publisher Method
**File:** `services/llm_provider_service/protocols.py`
```python
# Add to LLMEventPublisherProtocol
async def publish_llm_cost_tracking(
    self,
    correlation_id: UUID,
    provider: LLMProviderType,
    model: str,
    request_type: str,
    cost_estimate_usd: float,
    token_usage: Dict[str, int],
    request_timestamp: datetime,
    response_time_ms: int,
    cached: bool = False,
    cache_cost_savings_usd: float = 0.0,
    user_id: str | None = None,
    organization_id: str | None = None,
    service_name: str = "unknown",
    metadata: Dict[str, Any] | None = None,
) -> None:
```

### 2. Implement Cost Tracking Publisher
**File:** `services/llm_provider_service/implementations/event_publisher_impl.py`
```python
async def publish_llm_cost_tracking(self, ...):
    """Publish cost tracking event for downstream billing/analytics."""
    cost_data = LLMCostTrackingV1(
        correlation_id=correlation_id,
        provider=provider,
        model=model,
        request_type=request_type,
        cost_estimate_usd=cost_estimate_usd,
        token_usage=token_usage,
        request_timestamp=request_timestamp,
        response_time_ms=response_time_ms,
        cached=cached,
        cache_cost_savings_usd=cache_cost_savings_usd,
        user_id=user_id,
        organization_id=organization_id,
        service_name=service_name,
        metadata=metadata or {},
    )
    
    envelope = EventEnvelope(
        event_type=ProcessingEvent.LLM_COST_TRACKING.value,
        event_timestamp=datetime.now(timezone.utc),
        source_service=self.settings.SERVICE_NAME,
        correlation_id=correlation_id,
        data=cost_data,
    )
    
    topic = topic_name(ProcessingEvent.LLM_COST_TRACKING)
    await self.kafka_bus.publish(topic, envelope)
```

### 3. Add Cost Tracking to Orchestrator
**File:** `services/llm_provider_service/implementations/llm_orchestrator_impl.py`

**Add to successful LLM requests** (after `publish_llm_request_completed`):
```python
# Publish cost tracking event for Result Aggregator Service
await self.event_publisher.publish_llm_cost_tracking(
    correlation_id=correlation_id,
    provider=provider,
    model=result.model,
    request_type="comparison",
    cost_estimate_usd=cost_estimate_value,
    token_usage=token_usage_dict,
    request_timestamp=datetime.fromtimestamp(start_time, tz=timezone.utc),
    response_time_ms=response_time_ms,
    cached=False,
    cache_cost_savings_usd=0.0,
    service_name="llm_provider_service",  # Could be passed from caller
    metadata=overrides,
)
```

**Add to cached responses** (after cache hit logic):
```python
# Calculate cost savings from cache hit
estimated_cost = self._estimate_cost(provider, cached_response.get("token_usage")) or 0.0

await self.event_publisher.publish_llm_cost_tracking(
    correlation_id=correlation_id,
    provider=provider,
    model=cached_response.get("model", "unknown"),
    request_type="comparison",
    cost_estimate_usd=0.0,  # No cost for cached response
    token_usage=cached_response.get("token_usage", {}),
    request_timestamp=datetime.fromtimestamp(start_time, tz=timezone.utc),
    response_time_ms=response_time_ms,
    cached=True,
    cache_cost_savings_usd=estimated_cost,
    service_name="llm_provider_service",
    metadata={
        "cache_key": cache_key,
        "cached": True,
    },
)
```

### 4. Add Required Imports
**Files:** `event_publisher_impl.py`, `llm_orchestrator_impl.py`
```python
from datetime import datetime, timezone
from common_core.events.llm_provider_events import LLMCostTrackingV1
from common_core.event_enums import ProcessingEvent
```

## Planned Metrics Service Integration (Future)

### TODO: Add Cost Tracking Consumer
**File:** `services/system_metrics_service/`
```python
# Add Kafka consumer for LLMCostTrackingV1 events
# Store cost data in PostgreSQL with:
# - Per-user cost tracking
# - Per-organization billing
# - Provider cost breakdown
# - Cache efficiency metrics
# - Historical cost trends
```

### Cost Storage Schema (Suggested)
```sql
CREATE TABLE llm_cost_tracking (
    id UUID PRIMARY KEY,
    correlation_id UUID NOT NULL,
    provider VARCHAR(50) NOT NULL,
    model VARCHAR(100) NOT NULL,
    request_type VARCHAR(50) NOT NULL,
    cost_estimate_usd DECIMAL(10,6) NOT NULL,
    token_usage JSONB NOT NULL,
    user_id VARCHAR(255),
    organization_id VARCHAR(255),
    service_name VARCHAR(100) NOT NULL,
    request_timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    response_time_ms INTEGER NOT NULL,
    cached BOOLEAN DEFAULT FALSE,
    cache_cost_savings_usd DECIMAL(10,6) DEFAULT 0.0,
    metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes for cost analysis
CREATE INDEX idx_llm_cost_user_date ON llm_cost_tracking(user_id, request_timestamp);
CREATE INDEX idx_llm_cost_org_date ON llm_cost_tracking(organization_id, request_timestamp);
CREATE INDEX idx_llm_cost_provider_date ON llm_cost_tracking(provider, request_timestamp);
```

## Benefits

1. **Separation of Concerns**: LLM Provider handles infrastructure, System Metrics Service handles persistence
2. **Real-time + Historical**: Redis for live limits, PostgreSQL for billing/analytics  
3. **Multi-tenant Ready**: Organization-level cost tracking built-in
4. **Cache ROI Analysis**: Track cost savings from caching strategy
5. **Service Attribution**: Know which service is driving costs

## Priority: HIGH
This enables proper cost management and billing for the LLM infrastructure.