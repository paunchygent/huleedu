---
description: 
globs: 
alwaysApply: true
---
# 030: Event-Driven Architecture (EDA) Standards

## 1. Core Principle
- **Default**: Asynchronous, event-driven communication via Kafka
- **Minimize**: Synchronous API calls between services

## 2. Event Design Standards

### 2.1. EventEnvelope Structure
**MUST** use `EventEnvelope` from `common/events/envelope.py` with:
- `event_id: UUID`, `event_type: str`, `event_timestamp: datetime`
- `source_service: str`, `correlation_id: Optional[UUID]`
- `data: T_EventData` (typed, versioned Pydantic model)

### 2.2. Event Naming Convention
**MUST** follow: `<project>.<domain>.<entity>.<action_past_tense>.v<version>`
Example: `huleedu.essay.spellcheck.requested.v1`

### 2.3. Thin Events Principle
- Events signal occurrences with identifiers/references
- **FORBIDDEN**: Large data blobs in events
- **MUST** use `StorageReferenceMetadata` for data references

## 3. Kafka Topics
- **Naming**: `<project>.<environment>.<domain>.<entity>`
- **Publication**: Serialize `EventEnvelope` to JSON

## 4. Consumer Responsibilities
- **MUST** be idempotent (handle duplicates)
- **MUST** implement error handling, retries, DLQ strategy
- **SHOULD** validate schema on deserialization

## 5. Schema Evolution
- Additive, optional changes are safe
- Breaking changes **REQUIRE** new event version
