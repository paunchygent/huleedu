---
type: decision
id: ADR-0012
status: proposed
created: 2025-11-27
last_updated: 2025-11-27
---

# ADR-0012: AI Feedback Pure Kafka Worker Pattern

## Status
Proposed

## Context
AI Feedback Service needs to process batch requests triggered by Essay Lifecycle Service. Options:
1. HTTP API with request-response pattern
2. Pure Kafka worker consuming events

## Decision
Implement AI Feedback as **Pure Kafka Worker** (no client-facing APIs).

### Service Classification
- **Type**: Event-driven consumer with batch processing
- **Template**: Based on CJ Assessment Service architecture
- **Input**: `BatchAIFeedbackRequestedV1` from ELS
- **Output**: `BatchAIFeedbackCompletedV1` to ELS

### Event Flow
```
ELS → batch.ai.feedback.requested → AI Feedback Service
AI Feedback Service → batch.ai.feedback.completed → ELS
```

### Worker Structure
```
services/ai_feedback_service/
├── worker_main.py         # Kafka consumer entrypoint
├── event_processor.py     # Batch processing orchestration
├── config.py              # Settings
├── protocols.py           # DI interfaces
├── di.py                  # Dishka providers
└── core_logic/            # Business logic
```

## Consequences

### Positive
- Consistent with CJ Assessment pattern
- Natural batch processing
- Decoupled from HTTP concerns
- Idempotency via message keys

### Negative
- No direct query capability (use RAS for results)
- Debugging requires Kafka tooling

## References
- TASKS/assessment/ai-feedback-service-implementation.md
- services/cj_assessment_service/ (pattern reference)
