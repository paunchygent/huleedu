---
trigger: model_decision
description: "Standards for data and metadata management. Follow when designing database schemas, data access, or metadata to ensure data consistency and integrity."
---

===
# 060: Data and Metadata Management

## 1. Purpose
These standards govern how data and metadata are defined, stored, accessed, and managed across HuleEdu services, particularly emphasizing the use of common models.

## 2. Common Data Models (Pydantic)

### 2.1. Rule: `common/models/` as Central Data Model Repository
    - All data models shared between services (event payloads, API DTOs, shared entities) **MUST** be defined as Pydantic models within the `common/models/` directory.
    - This includes data models for events (in `common/events/data_models.py`), API schemas (in `common/models/api_schemas.py`), and common metadata structures.
    - **Your Directive**: You **MUST** reference and use these common models when generating code that handles inter-service data.

### 2.2. Rule: Use Common Metadata Models
    - Standard metadata, such as references to stored data, **MUST** use Pydantic models defined in `common/models/metadata_models.py`.
    - The `StorageReferenceMetadata` model, for example, **SHALL** be used in event payloads or API responses to point to larger data stored elsewhere (see [030-event-driven-architecture-eda-standards.md](mdc:030-event-driven-architecture-eda-standards.md) on Thin Events).

### 2.3. Rule: Model Definition Standards
    - Pydantic models in `common/models/` **MUST** be fully type-hinted (see [050-python-coding-standards.md](mdc:050-python-coding-standards.md) for Mypy standards) and include clear field descriptions (using `Field` or docstrings).
    - They **SHOULD** be versioned implicitly via their location or explicitly in naming if necessary (e.g., for API schemas).

## 3. Data Storage and Access

### 3.1. Rule: Service Owns its Data Store
    - Each service **SHALL** primarily interact with its own dedicated data store (database, object storage, etc.).
    - Direct access to another service's data store is **STRICTLY FORBIDDEN** (see [020-architectural-mandates.md](mdc:020-architectural-mandates.md)). Data access **MUST** be mediated via the owning service's defined API or events.

### 3.2. Guideline: ORM/Client Usage
    - Use async-compatible ORMs or database clients within services.
    - Keep data access logic within the service's bounded context.

## 4. Metadata Management

### 4.1. Rule: Metadata in `EventEnvelope` and API Responses
    - Essential metadata like `event_id`, `event_timestamp`, `source_service`, and `correlation_id` **MUST** be included in the `EventEnvelope` for events (see [030-event-driven-architecture-eda-standards.md](mdc:030-event-driven-architecture-eda-standards.md)).
    - API responses **SHOULD** include relevant metadata (e.g., timestamp, request ID).

### 4.2. Guideline: Logging Includes Metadata
    - Ensure logging includes relevant metadata, especially `correlation_id`, to trace requests/events across services (see [040-service-implementation-guidelines.md](mdc:040-service-implementation-guidelines.md)).

## 5. Data Schema Evolution

### 5.1. Rule: Backward Compatibility
    - When evolving schemas in `common/models/`, prioritize backward compatibility.
    - Adding optional fields is generally safe. Removing or changing types of existing fields **REQUIRES** careful versioning and communication strategy (see [020-architectural-mandates.md](mdc:020-architectural-mandates.md), [030-event-driven-architecture-eda-standards.md](mdc:030-event-driven-architecture-eda-standards.md)).
    - You **SHALL** advise on backward-compatible changes or the need for new versions.

---
**Consistent data and metadata practices are foundational for system coherence and debuggability.**
===
