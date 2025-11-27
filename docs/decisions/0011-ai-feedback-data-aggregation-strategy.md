---
type: decision
id: ADR-0011
status: proposed
created: 2025-11-27
last_updated: 2025-11-27
---

# ADR-0011: AI Feedback Data Aggregation Strategy

## Status
Proposed

## Context
AI Feedback Service requires data from multiple upstream services (Spellchecker, NLP, CJ Assessment) to generate comprehensive teacher feedback. Two approaches exist:
1. Direct HTTP calls to each upstream service
2. Single query to Result Aggregator Service (RAS) which maintains materialized views

## Decision
Use **Result Aggregator Service as data facade** for AI Feedback Service.

### Implementation
- AI Feedback calls: `GET /internal/v1/essays/{essay_id}/aggregated-analysis`
- RAS returns: corrected text, NLP metrics, spelling errors, CJ ranking (if available)
- Single HTTP call replaces 3-4 parallel service queries

### Data Flow
```
AI Feedback → RAS → {Spellcheck results, NLP metrics, CJ ranking}
```

### RAS Endpoint Contract
```python
class AggregatedEssayAnalysis:
    essay_id: str
    corrected_text_storage_id: str
    nlp_metrics: NLPMetrics
    spelling_errors: list[SpellingError]
    cj_ranking: Optional[CJRanking]
    course_code: CourseCode
    owner_user_id: str
```

## Consequences

### Positive
- Single point of data access
- RAS handles cache/DB reads efficiently
- Reduced HTTP overhead for AI Feedback
- Clear data contract

### Negative
- Dependency on RAS availability
- RAS must keep materialized views current

## References
- TASKS/assessment/ai-feedback-service-implementation.md
- services/result_aggregator_service/
