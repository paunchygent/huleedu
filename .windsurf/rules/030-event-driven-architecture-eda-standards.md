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

### 2.3. Event Size Optimization

#### Thin Events Principle
- Events signal occurrences with identifiers/references
- **FORBIDDEN**: Large data blobs in events
- **MUST** use `StorageReferenceMetadata` for data references

#### Dual Event Pattern (Advanced)
For services requiring both state management and business data:
- **Thin Event**: Minimal state transition data (~300 bytes) for ELS/BCS consumers
- **Rich Event**: Complete business metrics for RAS/analytics consumers
- **Example**: Spellchecker publishes both `SpellcheckPhaseCompletedV1` and `SpellcheckResultV1`
- **Benefits**: Performance optimization, separation of concerns, network efficiency

## 3. Event Publishing

### 3.1. Transactional Outbox Pattern (Preferred)
- **MUST** use outbox pattern for business-critical events
- **Pattern**: Store events in database transaction, relay worker publishes to Kafka
- **Benefits**: Atomicity, reliability, Kafka downtime tolerance
- **Implementation**: Use `huleedu_service_libs.outbox` components

### 3.2. Direct Kafka Publishing (Limited Use)
- **Use Cases**: Non-critical events, external integrations
- **Requirements**: Must handle Kafka failures gracefully
- **Pattern**: Circuit breaker protection with graceful degradation

### 3.3. Kafka Topics
- **Naming**: `<project>.<environment>.<domain>.<entity>`
- **Publication**: Serialize `EventEnvelope` to JSON

## 4. Consumer Responsibilities
- **MUST** be idempotent (handle duplicates)
- **MUST** implement error handling, retries, DLQ strategy
- **SHOULD** validate schema on deserialization

### 4.1. Header-First Processing
**Processing Path**: Idempotency decorator prioritizes header extraction over JSON parsing.

**Header Decoding**:
- Handles bytes/string key formats via utf-8 decode
- Extracts `event_id`, `event_type`, `trace_id`, `source_service`
- `headers_used` field tracks header utilization in logs

**Fallback Logic**:
- Complete headers (`event_id` + `event_type`) → Skip JSON parsing
- Incomplete headers → Parse JSON for missing fields
- Missing headers → Full JSON parsing

## 5. Schema Evolution
- Additive, optional changes are safe
- Breaking changes **REQUIRE** new event version

## 6. Error Handling
- **MUST** use generic platform error handling patterns
- **MUST** implement correlation ID propagation
- **MUST** use `HuleEduError` for structured error reporting

### 6.1. Outbox Pattern Error Handling
- **Database Transaction Failures**: Business operation and event storage both rollback
- **Kafka Failures**: Events accumulate in outbox, automatic retry when Kafka recovers
- **Relay Worker Failures**: Events marked for retry up to configurable max attempts
- **Poison Events**: Failed events logged and marked as permanently failed

Use graceful degradation as a **platform standard** for all event-driven services
