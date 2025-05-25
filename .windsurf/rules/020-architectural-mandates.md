---
description: "Mandatory patterns and constraints for HuleEdu services. Apply when designing or modifying services and APIs to ensure consistency and maintainability."
globs: 
alwaysApply: true
---
===
# 020: Architectural Mandates

## 1. Purpose
These non-negotiable mandates **MUST** be followed by all services and by you (AI agent) to ensure consistency and maintainability in the HuleEdu microservice architecture.

## 2. Domain-Driven Design (DDD) Mandates

### 2.1. Rule: Strict Bounded Contexts
    - Each microservice **SHALL** map to a specific business domain (bounded context), owning its data and logic.
    - Service boundaries **MUST** be respected. Logic/data of one context **SHALL NOT** be in a service for another.
    - You **MUST** identify the correct bounded context/microservice for task implementation.

### 2.2. Rule: No Unauthorized Cross-Boundary Violations
    - All inter-service communication **MUST** use explicitly defined, versioned contracts (Events or APIs).
    - Direct access to another service's database/datastore is **STRICTLY FORBIDDEN**.
    - Direct internal function calls between distinct microservices bypassing contracts are **STRICTLY FORBIDDEN**. (Shared `common/` utilities are an exception, not service logic).
    - You **SHALL NOT** propose solutions with such direct dependencies.

## 3. Service Autonomy Mandates

### 3.1. Rule: Design for Independent Deployability
    - Each microservice **MUST** be independently deployable, scalable, and updatable.
    - Build/deployment processes **SHALL NOT** have hard dependencies on unrelated services.
    - Configuration **MUST** be self-contained or centrally managed (service-agnostic).

### 3.2. Rule: Data (Schema) Ownership per Service
    - Each microservice is the source of truth for its domain's data.
    - If using a shared DB during transition, each service **MUST** own and operate on an isolated schema.
    - A service **MUST NOT** directly write/modify another service's schema. Changes **MUST** be via the owning service's API or events.

## 4. Explicit Contract Mandates (Pydantic)

### 4.1. Rule: Pydantic Models are the Contractual Single Source of Truth
    - All inter-service data structures (event payloads, API DTOs) **MUST** be Pydantic models.
    - These models **SHALL** reside in `common/models/` (e.g., `common/events/data_models.py`, `common/models/api_schemas.py`).
    - No ad-hoc dictionaries for inter-service communication.
    - You **MUST** use or create Pydantic models from `common/` for inter-service data exchange code.

### 4.2. Rule: Contract Versioning
    - Pydantic contract models (especially for events) **MUST** be versioned (e.g., in event type name like `.v1`, `.v2`).
    - Breaking changes to a Pydantic contract model **REQUIRE** a new contract version.
    - Services **MUST** handle different contract versions or have clear upgrade paths.

### 4.3. Rule: Strict Schema Adherence
    - Producers and consumers **MUST** strictly adhere to agreed Pydantic schema versions.
    - Producers **MUST** ensure data validates against the Pydantic model.
    - Consumers **MUST** validate received data against their expected Pydantic model.
    - You **SHALL** generate code that performs such validation.

---
**CRITICAL: Deviating from these mandates compromises the microservice architecture.**
===
