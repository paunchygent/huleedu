---
type: decision
id: ADR-0013
status: proposed
created: 2025-11-27
last_updated: 2025-11-27
---

# ADR-0013: AI Feedback Name Resolution Strategy

## Status
Proposed

## Context
AI Feedback prompts require teacher and student names for personalization. Options:
1. Include names in Kafka events (PII in message bus)
2. Include names in RAS aggregated response
3. Resolve names via HTTP at consumption time

## Decision
Resolve names via **HTTP calls at consumption time** (DDD bounded context compliance).

### Implementation
- **Teacher Name**: HTTP call to Identity Service using `owner_user_id`
- **Student Name**: HTTP call to CMS using `essay_id` or `batch_id`
- **Graceful Degradation**: Default names on failure ("Unknown Teacher", "the student")

### HTTP Clients
```python
# Identity Client
async def get_user_person_name(user_id: str) -> PersonNameV1

# CMS Client
async def get_essay_student_name(essay_id: str) -> PersonNameV1 | None
async def get_batch_student_names(batch_id: str) -> list[dict]
```

### Resilience
- Circuit breaker: 3 failure threshold, 30s recovery
- Timeout: 5s single request, 10s batch operations
- Fallback: Default names on failure

## Consequences

### Positive
- No PII in Kafka events
- Clean bounded contexts
- Service continues without name services

### Negative
- Additional HTTP calls per batch
- Network latency for name resolution

## References
- TASKS/assessment/ai-feedback-service-implementation.md (Phase 1.5)
- libs/common_core/src/common_core/metadata_models.py (PersonNameV1)
