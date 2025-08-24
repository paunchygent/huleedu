# Entitlements Service Implementation Plan

## Executive Summary

**Purpose**: Rate limiting and credit management for LLM-powered features to protect platform from API cost overruns while enabling B2B/B2C revenue models.

**Core Economics**: Differentiate between free operations (internal processing) and paid operations (external LLM API calls) with credit-based consumption tracking.

**Integration**: Gateway-facing synchronous API with asynchronous event publishing for usage analytics and cross-service coordination.

## Architecture Alignment

### Service Pattern

- **Integrated Pattern**: Follow Email Service model with `app.py` managing HTTP + Kafka lifecycle
- **Event Publishing**: EventRelayWorker for outbox pattern with reliable event delivery
- **Configuration**: Policy manifest in YAML with Redis caching for zero-downtime updates
- **DI**: Dishka with Protocol interfaces following established patterns

### Core Principle

**Optimistic Credit Flow**: Check credits → Process operation → Record consumption (with failure logging for admin resolution)

## Service Structure

```
services/entitlements_service/
  app.py                    # Integrated Quart + Kafka lifecycle (@app.before_serving)
  startup_setup.py          # DI init, policy loader, EventRelayWorker startup
  config.py                 # Settings with ENTITLEMENTS_ prefix
  protocols.py              # CreditManager, PolicyLoader, RateLimiter protocols
  di.py                     # Providers (APP/REQUEST scopes)
  models_db.py              # SQLAlchemy models
  kafka_consumer.py         # EntitlementsKafkaConsumer class
  event_processor.py        # Usage recording, credit balance events
  api/
    health_routes.py        # /healthz, /metrics
    entitlements_routes.py  # /v1/entitlements/* endpoints
    admin_routes.py         # /v1/admin/credits/* (dev/admin only)
  implementations/
    credit_manager_impl.py  # Core credit logic with dual system
    policy_loader_impl.py   # YAML loading with Redis cache
    rate_limiter_impl.py    # Redis-based sliding window
    outbox_manager.py       # Transactional outbox
  policies/
    default.yaml            # Default costs, limits, signup bonuses
  alembic/
  README.md
  tests/
```

## Database Schema

```sql
-- Credit balances per subject (user or org)
CREATE TABLE credit_balances (
    subject_type VARCHAR(10) NOT NULL, -- 'user' or 'org'
    subject_id VARCHAR(255) NOT NULL,
    balance INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (subject_type, subject_id)
);

-- Detailed audit trail for credit operations
CREATE TABLE credit_operations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    subject_type VARCHAR(10) NOT NULL,
    subject_id VARCHAR(255) NOT NULL,
    metric VARCHAR(100) NOT NULL,        -- 'cj_assessment', 'ai_feedback'
    amount INTEGER NOT NULL,             -- Credits consumed
    batch_id VARCHAR(255),               -- For correlation with processing
    consumed_from VARCHAR(10) NOT NULL,  -- 'user' or 'org' (which balance used)
    correlation_id VARCHAR(255) NOT NULL,
    operation_status VARCHAR(20) DEFAULT 'completed', -- 'completed', 'failed', 'pending'
    created_at TIMESTAMP DEFAULT NOW()
);

-- Rate limiting sliding windows
CREATE TABLE rate_limit_buckets (
    subject_id VARCHAR(255) NOT NULL,
    metric VARCHAR(100) NOT NULL,
    window_start TIMESTAMP NOT NULL,
    count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (subject_id, metric, window_start)
);

-- Outbox for reliable event publishing
CREATE TABLE event_outbox (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    aggregate_type VARCHAR(100) NOT NULL,
    aggregate_id VARCHAR(255) NOT NULL,
    event_type VARCHAR(200) NOT NULL,
    event_data JSONB NOT NULL,
    topic VARCHAR(200) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    published_at TIMESTAMP NULL
);

-- Indexes
CREATE INDEX idx_credit_operations_subject ON credit_operations(subject_type, subject_id);
CREATE INDEX idx_credit_operations_correlation ON credit_operations(correlation_id);
CREATE INDEX idx_rate_limit_window ON rate_limit_buckets(window_start);
CREATE INDEX idx_outbox_unpublished ON event_outbox(published_at, topic, created_at) WHERE published_at IS NULL;
```

## Core Models (Pydantic)

```python
# libs/common_core/src/common_core/entitlements_models.py

from __future__ import annotations
from pydantic import BaseModel
from typing import Literal, Optional
from datetime import datetime

SubjectType = Literal["org", "user"]

class SubjectRefV1(BaseModel):
    type: SubjectType
    id: str  # uuid

class CreditCheckRequestV1(BaseModel):
    user_id: str
    org_id: Optional[str] = None
    metric: str
    amount: int = 1

class CreditCheckResponseV1(BaseModel):
    allowed: bool
    reason: Optional[str] = None
    required_credits: int
    available_credits: int
    source: Optional[str] = None  # "user" or "org"

class CreditConsumptionV1(BaseModel):
    user_id: str
    org_id: Optional[str] = None
    metric: str
    amount: int
    batch_id: Optional[str] = None
    correlation_id: str

class CreditBalanceChangedV1(BaseModel):
    subject: SubjectRefV1
    delta: int  # negative for consumption, positive for addition
    new_balance: int
    reason: str
    correlation_id: str

class RateLimitExceededV1(BaseModel):
    subject: SubjectRefV1
    metric: str
    limit: int
    window_seconds: int
    correlation_id: str

class UsageRecordedV1(BaseModel):
    subject: SubjectRefV1
    metric: str
    amount: int = 1
    timestamp: datetime
    correlation_id: str
```

## Policy Manifest System

### Configuration File

```yaml
# services/entitlements_service/policies/default.yaml

costs:
  # Free internal processing
  batch_create: 0
  spellcheck: 0
  nlp_analysis: 0
  
  # Paid LLM operations (per essay)
  cj_assessment: 10
  ai_feedback: 5

rate_limits:
  # Operations per time window
  batch_create: 60/hour
  cj_assessment: 100/day
  ai_feedback: 200/day

signup_bonuses:
  user: 50    # Credits for new individual users
  org: 500    # Credits for new organizations

cache_ttl: 300  # Policy cache TTL in Redis (5 minutes)
```

### Policy Loader Implementation

```python
# services/entitlements_service/implementations/policy_loader_impl.py

class PolicyLoaderImpl:
    def __init__(self, redis_client, config_path: str = "policies/default.yaml"):
        self.redis = redis_client
        self.config_path = config_path
        self.cache_key = "entitlements:policies:v1"
    
    async def load_policies(self) -> dict:
        """Load policies from file and cache in Redis."""
        with open(self.config_path) as f:
            policies = yaml.safe_load(f)
        await self.redis.set(self.cache_key, json.dumps(policies))
        return policies
    
    async def get_cost(self, metric: str) -> int:
        """Get credit cost for a metric."""
        policies = await self._get_cached_policies()
        return policies.get("costs", {}).get(metric, 0)
    
    async def get_rate_limit(self, metric: str) -> tuple[int, int]:
        """Get rate limit as (count, window_seconds)."""
        policies = await self._get_cached_policies()
        limit_str = policies.get("rate_limits", {}).get(metric, "unlimited")
        if limit_str == "unlimited":
            return 0, 0
        # Parse "60/hour" or "100/day"
        count, period = limit_str.split("/")
        window_seconds = {"hour": 3600, "day": 86400}[period]
        return int(count), window_seconds
```

## API Endpoints

### Core Entitlements API

**POST /v1/entitlements/check-credits**

```python
{
    "user_id": "uuid",
    "org_id": "uuid",  # optional
    "metric": "cj_assessment", 
    "amount": 15       # essays in batch
}

Response:
{
    "allowed": true,
    "required_credits": 150,
    "available_credits": 500,
    "source": "org"
}
```

**POST /v1/entitlements/consume-credits**

```python
{
    "user_id": "uuid",
    "org_id": "uuid",
    "metric": "cj_assessment",
    "amount": 150,
    "batch_id": "batch_uuid",
    "correlation_id": "correlation_uuid"
}

Response: 
{
    "success": true,
    "new_balance": 350,
    "consumed_from": "org"
}
```

**GET /v1/entitlements/balance/{user_id}**

```python
Response:
{
    "user_balance": 100,
    "org_balance": 350,  # if user belongs to org
    "org_id": "uuid"     # if applicable
}
```

### Admin API (Development/Admin Only)

**POST /v1/admin/credits/adjust**

```python
{
    "subject_type": "user",  # or "org"
    "subject_id": "uuid",
    "amount": 500,           # positive to add, negative to deduct
    "reason": "manual_adjustment"
}
```

**GET /v1/admin/credits/operations?subject_id=uuid&limit=100**

```python
Response:
{
    "operations": [
        {
            "metric": "cj_assessment",
            "amount": 150,
            "batch_id": "uuid",
            "consumed_from": "org",
            "created_at": "2025-01-01T12:00:00Z"
        }
    ]
}
```

## Core Business Logic

### Credit Resolution (Dual System)

```python
class CreditManagerImpl:
    async def check_credits(self, user_id: str, org_id: str | None, 
                          metric: str, amount: int) -> CreditCheckResponseV1:
        # Get cost from policy
        cost_per_unit = await self.policy_loader.get_cost(metric)
        total_cost = cost_per_unit * amount
        
        if total_cost == 0:  # Free operation
            return CreditCheckResponseV1(
                allowed=True, 
                required_credits=0, 
                available_credits=0
            )
        
        # Check rate limits first
        if not await self._check_rate_limit(user_id, metric, amount):
            return CreditCheckResponseV1(
                allowed=False,
                reason="rate_limit_exceeded",
                required_credits=total_cost,
                available_credits=0
            )
        
        # Check credits: org first, then user
        if org_id:
            org_balance = await self._get_balance("org", org_id)
            if org_balance >= total_cost:
                return CreditCheckResponseV1(
                    allowed=True,
                    required_credits=total_cost,
                    available_credits=org_balance,
                    source="org"
                )
        
        # Fallback to user credits
        user_balance = await self._get_balance("user", user_id)
        if user_balance >= total_cost:
            return CreditCheckResponseV1(
                allowed=True,
                required_credits=total_cost,
                available_credits=user_balance,
                source="user"
            )
        
        return CreditCheckResponseV1(
            allowed=False,
            reason="insufficient_credits",
            required_credits=total_cost,
            available_credits=user_balance
        )
    
    async def consume_credits(self, consumption: CreditConsumptionV1) -> bool:
        # Determine source (same logic as check_credits)
        source, subject_id = await self._resolve_credit_source(
            consumption.user_id, consumption.org_id, consumption.metric, consumption.amount
        )
        
        try:
            # Deduct credits
            await self._deduct_balance(source, subject_id, total_cost)
            
            # Record detailed operation
            await self._record_operation(
                subject_type=source,
                subject_id=subject_id,
                metric=consumption.metric,
                amount=total_cost,
                batch_id=consumption.batch_id,
                consumed_from=source,
                correlation_id=consumption.correlation_id,
                status="completed"
            )
            
            # Publish balance changed event
            await self._publish_balance_changed(source, subject_id, -total_cost, consumption.correlation_id)
            
            return True
            
        except Exception as e:
            # Log credit debt for admin resolution (optimistic approach)
            await self._record_operation(
                subject_type=source,
                subject_id=subject_id,
                metric=consumption.metric,
                amount=total_cost,
                batch_id=consumption.batch_id,
                consumed_from=source,
                correlation_id=consumption.correlation_id,
                status="failed"
            )
            logger.error(f"Credit consumption failed: {e}, correlation_id: {consumption.correlation_id}")
            return False
```

## Integration Patterns

### Gateway Integration

```python
# API Gateway before expensive operations

# 1. Check entitlements
check_response = await entitlements_client.check_credits(
    user_id=token.user_id,
    org_id=token.org_id,
    metric="cj_assessment",
    amount=essay_count
)

if not check_response.allowed:
    return JSONResponse({
        "error": "insufficient_credits",
        "required": check_response.required_credits,
        "available": check_response.available_credits
    }, status_code=402)

# 2. Process batch (may take minutes)
batch_result = await batch_orchestrator.process_batch(batch_id)

# 3. Record consumption
await entitlements_client.consume_credits(
    user_id=token.user_id,
    org_id=token.org_id,
    metric="cj_assessment", 
    amount=essay_count,
    batch_id=batch_id,
    correlation_id=correlation_id
)
```

### Event Publishing

```python
# Published events for cross-service coordination

# When credits are consumed
CreditBalanceChangedV1(
    subject=SubjectRefV1(type="org", id="org_uuid"),
    delta=-150,
    new_balance=350,
    reason="cj_assessment",
    correlation_id="correlation_uuid"
)

# When rate limit exceeded
RateLimitExceededV1(
    subject=SubjectRefV1(type="user", id="user_uuid"),
    metric="batch_create",
    limit=60,
    window_seconds=3600,
    correlation_id="correlation_uuid"
)
```

## Testing Strategy

### Unit Tests

- Credit resolution precedence logic
- Policy loading and caching
- Rate limiting calculations
- Balance arithmetic

### Integration Tests  

- Redis rate limiting with concurrent requests
- Database credit operations with transactions
- Policy loading from YAML files
- Event publishing via outbox

### Contract Tests

- API request/response schemas
- Event schema validation
- Common core model compatibility

### End-to-End Tests

- Gateway → Entitlements → Service flow
- Credit depletion scenarios
- Rate limit enforcement
- Org membership changes

## Deployment Configuration

### Environment Variables

```bash
# Service configuration
ENTITLEMENTS_SERVICE_NAME=entitlements_service
ENTITLEMENTS_LOG_LEVEL=INFO
ENTITLEMENTS_METRICS_PORT=8083

# Database
ENTITLEMENTS_SERVICE_DATABASE_URL=postgresql+asyncpg://...

# Redis for caching and rate limiting
ENTITLEMENTS_REDIS_URL=redis://redis:6379/0

# Kafka
ENTITLEMENTS_KAFKA_BOOTSTRAP_SERVERS=kafka:9092
ENTITLEMENTS_PRODUCER_CLIENT_ID=entitlements-service-producer

# Policy configuration
ENTITLEMENTS_POLICY_FILE=policies/default.yaml
ENTITLEMENTS_POLICY_CACHE_TTL=300
```

### Docker Configuration

```yaml
# docker-compose.services.yml
entitlements_service:
  build:
    context: .
    dockerfile: services/entitlements_service/Dockerfile
  ports:
    - "8083:8083"  # HTTP API + metrics
  environment:
    - ENTITLEMENTS_REDIS_URL=redis://redis:6379/0
    - ENTITLEMENTS_KAFKA_BOOTSTRAP_SERVERS=kafka:9092
  depends_on:
    - entitlements_db
    - redis
    - kafka

entitlements_db:
  image: postgres:15
  ports:
    - "5444:5432"  # Unique port for entitlements DB
  environment:
    - POSTGRES_DB=huleedu_entitlements
    - POSTGRES_USER=huleedu_user
    - POSTGRES_PASSWORD=huleedu_password
```

## Event Integration

### Consumed Events

```python
# From other services reporting usage
UsageRecordedV1  # Real-time usage tracking for analytics
```

### Published Events

```python
# To Result Aggregator Service for analytics
CreditBalanceChangedV1   # Balance changes for reporting
RateLimitExceededV1      # Rate limit violations for monitoring

# Event topics
ENTITLEMENTS_CREDIT_BALANCE_CHANGED → huleedu.entitlements.credit.balance.changed.v1
ENTITLEMENTS_RATE_LIMIT_EXCEEDED → huleedu.entitlements.rate_limit.exceeded.v1
```

## MVP Implementation Order

### Phase 1: Core Credit System (Week 1)

1. Database models and migrations
2. Basic credit manager with dual system (org/user precedence)
3. Policy loader with YAML + Redis caching
4. Core API endpoints (check-credits, consume-credits, balance)
5. Admin endpoints for manual credit adjustments

### Phase 2: Rate Limiting (Week 1)

1. Redis-based rate limiting implementation
2. Integration with check-credits endpoint
3. Rate limit violation events

### Phase 3: Integration & Testing (Week 1)

1. Gateway integration points
2. Event publishing via outbox
3. End-to-end testing with real services
4. Performance testing and optimization

## Future Expansion Hooks

### Payment Integration Ready

- Webhook endpoints structured for easy addition
- Credit adjustment events ready for payment service consumption
- Purchase history tracking prepared in database schema

### Advanced Features

- Two-phase commit reservation pattern (if credit disputes become frequent)
- Credit expiration and automatic cleanup
- Usage analytics and reporting dashboards
- Complex approval workflows for organizational purchases

## Success Criteria

1. **Cost Protection**: No unauthorized LLM API consumption possible
2. **Business Model**: Teachers can purchase and use individual credits
3. **B2B Ready**: Organizations can purchase credits for teacher pools
4. **Operational**: Policy updates without service restart
5. **Reliable**: Credit operations never lost or double-charged
6. **Performant**: <100ms for credit checks, <500ms for consumption
7. **Observable**: Full audit trail for credit operations and failures
