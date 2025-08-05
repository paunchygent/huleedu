---
description: 
globs: 
alwaysApply: true
---
# 020: Architectural Mandates

## 1. Domain-Driven Design (DDD)

### 1.1. Bounded Contexts
- Each microservice **SHALL** own a specific business domain
- Service boundaries **MUST** be respected - no cross-boundary logic/data
- **MUST** identify correct bounded context for implementation

### 1.2. Contract-Only Communication
- Inter-service communication **MUST** use explicit, versioned contracts
- **FORBIDDEN**: Direct database access, internal function calls between services
- **EXCEPTION**: Shared `common/` utilities (not service logic)

## 2. Service Autonomy

### 2.1. Independent Deployability
- Each microservice **MUST** be independently deployable/scalable/updatable
- Build/deployment **SHALL NOT** have hard dependencies on unrelated services
- Configuration **MUST** be self-contained or centrally managed

### 2.2. Data Ownership
- Each microservice is source of truth for its domain data
- Shared DB: services **MUST** operate on isolated schemas
- Schema changes **MUST** be via owning service's API/events

## 3. Explicit Contracts (Pydantic)

### 3.1. Contract Models
- All inter-service data **MUST** be Pydantic models in `common/`
- **FORBIDDEN**: Ad-hoc dictionaries for inter-service communication
- **MUST** use/create Pydantic models from `common/` for data exchange

### 3.2. Versioning & Adherence
- Contract models **MUST** be versioned (`.v1`, `.v2`)
- Breaking changes **REQUIRE** new contract version
- Services **MUST** handle version differences or have upgrade paths
- Producers/consumers **MUST** validate against Pydantic schemas

### 3.3. Shared Standards and Compliance

## 4. Event ID Generation and Idempotency

### 4.1. Deterministic Event ID Generation
- Event IDs **MUST** be generated deterministically based on business data only
- **FORBIDDEN**: Including envelope metadata (event_id, timestamp) in ID generation
- **MUST**: Use only the `data` field contents for deterministic ID calculation
- **RATIONALE**: Enables true idempotency by generating consistent IDs for identical business events

### 4.2. Idempotency Architecture
- Services **MUST** implement idempotency for all event processing
- Idempotency keys **SHALL** be stored in Redis with appropriate TTL
- **MUST** handle Redis failures gracefully with fallback to processing
- Event processors **MUST** check for duplicate events before processing

### 4.3. Event ID Generation Implementation
```python
# Correct implementation pattern
def generate_deterministic_event_id(event_type: str, data: BaseModel) -> UUID:
    """Generate deterministic UUID based on event type and data content only."""
    # Serialize only the business data, excluding envelope metadata
    data_dict = data.model_dump(mode="json", exclude_none=True)
    content = f"{event_type}:{json.dumps(data_dict, sort_keys=True)}"
    return uuid5(NAMESPACE_OID, content)
```

## 5. Phase 1 Student Matching Timeout Architecture

### 5.1. Association Timeout Monitor (Class Management Service)
- **Purpose**: Auto-confirms pending student-essay associations after 24-hour validation timeout
- **Configuration**: `TIMEOUT_HOURS = 24`, `HIGH_CONFIDENCE_THRESHOLD = 0.7`, runs hourly
- **High Confidence (≥0.7)**: Confirms association with original student using `TIMEOUT` validation method
- **Low Confidence (<0.7)**: Creates UNKNOWN student with email `unknown.{class_id}@huleedu.system`
- **Event Publishing**: Publishes `StudentAssociationsConfirmedV1` with `timeout_triggered=true`

### 5.2. Database Schema Requirements
```python
# EssayStudentAssociation model MUST include:
batch_id: UUID              # FK to batch - enables batch isolation
class_id: UUID              # FK to class - enables UNKNOWN student creation  
confidence_score: float     # NLP matching confidence for timeout decisions
validation_status: str      # pending_validation/confirmed/timeout_confirmed
validation_method: str      # human/timeout/auto
validated_at: datetime      # When validation occurred
validated_by: str          # Who/what validated (SYSTEM_TIMEOUT for timeouts)
```

## 6. CRITICAL COMPLIANCE CHECKLIST

### 6.1. Pre-Implementation Checklist
**Before writing any service code, verify:**
- [ ] Service follows DDD bounded context principles
- [ ] Service-specific architecture rule exists and is reviewed
- [ ] Protocol interfaces defined in `protocols.py`
- [ ] Dependency injection patterns planned with Dishka

### 6.2. Service Library Compliance Checklist
**MANDATORY - Zero tolerance for non-compliance:**
[ ] huleedu-service-libs declared in pyproject.toml
[ ] FORBIDDEN: Any import logging or from logging statements
[ ] MUST: All logging via huleedu_service_libs.logging_utils
[ ] FORBIDDEN: Direct aiokafka.AIOKafkaProducer or aiokafka.AIOKafkaConsumer imports
[ ] MUST: Kafka producers via the service library's KafkaBus class.
[ ] MUST: Kafka consumers via a dedicated, service-specific class (e.g., BatchKafkaConsumer) that is constructed and managed by the DI container.

### 6.3. Production Patterns Checklist (Sprint 1 Hardened)
**Battle-tested patterns from BOS - MANDATORY:**
- [ ] Graceful shutdown with proper async resource cleanup
- [ ] DI-managed `aiohttp.ClientSession` with configured timeouts
- [ ] Manual Kafka commits with error boundaries (`enable_auto_commit=False`)
- [ ] `/healthz` endpoint with consistent JSON response format
- [ ] Startup errors use `logger.critical()` and `raise` (fail fast)

### 6.4. HTTP Service Checklist
**For Quart-based services:**
- [ ] Blueprint pattern with `api/` directory structure
- [ ] `startup_setup.py` with DI and metrics initialization
- [ ] Service library metrics middleware configured
- [ ] Standard health (`/healthz`) and metrics (`/metrics`) endpoints

### 6.5. Worker Service Checklist
**For Kafka consumer services:**
- [ ] Signal handling for SIGTERM/SIGINT in worker main
- [ ] Event processor with protocol-based dependencies
- [ ] Structured logging with correlation ID tracking
- [ ] Manual offset commits after successful processing

### 6.6. Pre-Deployment Checklist
**Before container deployment:**
- [ ] All tests pass (`pdm run pytest`)
- [ ] Linting passes (`pdm run lint-all`)
- [ ] Type checking passes (`pdm run typecheck-all`)
- [ ] Dockerfile includes `ENV PYTHONPATH=/app`
- [ ] Health check endpoint responds correctly
- [ ] Service starts and shuts down gracefully

---
**NON-COMPLIANCE WITH THIS CHECKLIST IS BLOCKING FOR DEPLOYMENT**
