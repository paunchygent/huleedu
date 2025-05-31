---
description: "Mandatory patterns and constraints for HuleEdu services. Apply when designing or modifying services and APIs to ensure consistency and maintainability."
globs: 
alwaysApply: true
---

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