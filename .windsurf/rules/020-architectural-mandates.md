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

## 4. CRITICAL COMPLIANCE CHECKLIST

### 4.1. Pre-Implementation Checklist
**Before writing any service code, verify:**
- [ ] Service follows DDD bounded context principles
- [ ] Service-specific architecture rule exists and is reviewed
- [ ] Protocol interfaces defined in `protocols.py`
- [ ] Dependency injection patterns planned with Dishka

### 4.2. Service Library Compliance Checklist
**MANDATORY - Zero tolerance for non-compliance:**
[ ] huleedu-service-libs declared in pyproject.toml
[ ] FORBIDDEN: Any import logging or from logging statements
[ ] MUST: All logging via huleedu_service_libs.logging_utils
[ ] FORBIDDEN: Direct aiokafka.AIOKafkaProducer or aiokafka.AIOKafkaConsumer imports
[ ] MUST: Kafka producers via the service library's KafkaBus class.
[ ] MUST: Kafka consumers via a dedicated, service-specific class (e.g., BatchKafkaConsumer) that is constructed and managed by the DI container.

### 4.3. Production Patterns Checklist (Sprint 1 Hardened)
**Battle-tested patterns from BOS - MANDATORY:**
- [ ] Graceful shutdown with proper async resource cleanup
- [ ] DI-managed `aiohttp.ClientSession` with configured timeouts
- [ ] Manual Kafka commits with error boundaries (`enable_auto_commit=False`)
- [ ] `/healthz` endpoint with consistent JSON response format
- [ ] Startup errors use `logger.critical()` and `raise` (fail fast)

### 4.4. HTTP Service Checklist
**For Quart-based services:**
- [ ] Blueprint pattern with `api/` directory structure
- [ ] `startup_setup.py` with DI and metrics initialization
- [ ] Service library metrics middleware configured
- [ ] Standard health (`/healthz`) and metrics (`/metrics`) endpoints

### 4.5. Worker Service Checklist
**For Kafka consumer services:**
- [ ] Signal handling for SIGTERM/SIGINT in worker main
- [ ] Event processor with protocol-based dependencies
- [ ] Structured logging with correlation ID tracking
- [ ] Manual offset commits after successful processing

### 4.6. Pre-Deployment Checklist
**Before container deployment:**
- [ ] All tests pass (`pdm run pytest`)
- [ ] Linting passes (`pdm run lint-all`)
- [ ] Type checking passes (`pdm run typecheck-all`)
- [ ] Dockerfile includes `ENV PYTHONPATH=/app`
- [ ] Health check endpoint responds correctly
- [ ] Service starts and shuts down gracefully

---
**NON-COMPLIANCE WITH THIS CHECKLIST IS BLOCKING FOR DEPLOYMENT**
