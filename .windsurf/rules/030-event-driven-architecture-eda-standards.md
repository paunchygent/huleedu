---
description: "Standards for event-driven communication. Follow when publishing/consuming events or designing event schemas to ensure reliable event handling."
globs: 
alwaysApply: true
---
===
# 030: Event-Driven Architecture (EDA) Standards

## 1. Purpose
These standards govern event-driven communication in HuleEdu. You (AI agent) **MUST** follow these to build a loosely coupled, resilient, and scalable system.

## 2. Core Principle: Async Event-Driven Default
    - Asynchronous, event-driven communication via Kafka **is the default and preferred method** for inter-service collaboration.
    - Synchronous API calls between services are minimized; if used, they **MUST** adhere to API contracts ([020-architectural-mandates.md](mdc:020-architectural-mandates.md)).

## 3. Event Design: CRITICAL STANDARDS

### 3.1. Rule: Mandatory Standardized `EventEnvelope`
    - All events published to Kafka **MUST** use the `EventEnvelope` Pydantic model from `common/events/envelope.py`.
    - **Key `EventEnvelope` Fields You MUST Populate Correctly**:
        - `event_id: UUID` (unique per event instance)
        - `event_type: str` (fully qualified, versioned name; see 3.3)
        - `event_timestamp: datetime` (UTC)
        - `source_service: str` (identifier of your publishing microservice)
        - `correlation_id: Optional[UUID]` (propagate if received, or generate for new chains)
        - `data: T_EventData` (the event-specific Pydantic model; see 3.2)

### 3.2. Rule: `EventEnvelope.data` is a Typed, Versioned Pydantic Model
    - The `data` field **MUST** be a specific, versioned Pydantic model from `common/events/data_models.py` (or similar designated `common/` path), relevant to the `event_type`.
    - This ensures type safety and clear schema definition.

### 3.3. Rule: Strict Event Naming Conventions
    - `event_type` **MUST** follow: `<project_namespace>.<domain_or_service>.<entity>.<action_past_tense>.v<version_number>`
        - Examples: `huleedu.batchorchestration.batch.pipelines_configured.v1`, `huleedu.essaylifecycle.essay.spellcheck_requested.v1`.
    - You **SHALL** propose/use event types strictly adhering to this.

### 3.4. Rule: Thin Events Principle (Events as Notifications)
    - Events signal occurrences and provide essential identifiers/references. They **SHALL NOT** carry large data blobs (e.g., full texts).
    - Large data **MUST** be stored by the responsible service. Events **SHALL** carry references using `StorageReferenceMetadata` (from `common/models/metadata_models.py`).
    - Consumers use these references to fetch data via APIs if needed.

## 4. Event Brokering (Kafka)

### 4.1. Guideline: Kafka Topic Naming
    - Follow consistent topic naming, e.g., `<project_namespace>.<environment>.<domain_or_service>.<event_type_group_or_entity>`.
    - Topics should clearly indicate event source/nature.

### 4.2. Guideline: Event Publication
    - Publish events to appropriate topics. Serialize `EventEnvelope` to JSON.

## 5. Consumer Responsibilities

### 5.1. Rule: Consumers MUST Be Idempotent
    - Design consumers to handle duplicate events without side effects or data corruption (e.g., check processed IDs, use DB constraints).

### 5.2. Rule: Graceful Error Handling & Retries
    - Consumers **MUST** implement robust error handling for transient issues (retries, backoff) and a Dead-Letter Queue (DLQ) strategy for persistent failures. Log errors, retries, and DLQ events extensively.

### 5.3. Rule: Consumer-Side Schema Validation
    - Consumers **SHOULD** validate incoming event data against their expected Pydantic schema version upon deserialization.

## 6. Event Schema Evolution
    - Changes to event Pydantic models (`EventEnvelope.data`) **MUST** be managed carefully.
    - Additive, optional field changes are generally safe.
    - Removing fields or changing types are breaking changes and **REQUIRE** a new event version (see `event_type` naming and [020-architectural-mandates.md](mdc:020-architectural-mandates.md)).

---
**Disciplined EDA is KEY. Deviations in event design/handling ARE NOT ACCEPTABLE.**
===
