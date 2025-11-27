---
type: decision
id: ADR-0014
status: proposed
created: 2025-11-27
last_updated: 2025-11-27
---

# ADR-0014: AI Feedback Context Builder Pattern

## Status
Proposed

## Context
AI Feedback Service generates prompts using data from multiple upstream analyses. Options:
1. Pass raw data directly to prompts
2. Build structured context with summarized insights

## Decision
Implement **Context Builder pattern** to curate prompt context from aggregated analyses.

### Implementation
```python
def build_feedback_context(
    nlp_metrics: NLPMetrics,
    spelling_errors: list[SpellingError],
    cj_ranking: Optional[CJRanking]
) -> FeedbackContext
```

### FeedbackContext Structure
```python
class FeedbackContext:
    grammar_summary: str      # Summarized grammar patterns
    grammar_count: int
    spelling_patterns: str    # Categorized spelling issues
    spelling_error_count: int
    readability_score: float
    complexity_level: str
    comparative_position: Optional[str]  # "Top 25% of class"
    peer_comparison: Optional[str]
```

### Intelligence Layer
- Groups grammar issues by category
- Identifies recurring spelling patterns
- Formats CJ ranking as natural language
- Determines what context matters for each feedback type

## Consequences

### Positive
- Prompts receive curated, relevant context
- Separation of data gathering from prompt composition
- Easy to add new context sources (AES scores)
- Testable summarization logic

### Negative
- Additional abstraction layer
- Summary may lose nuance from raw data

## References
- TASKS/assessment/ai-feedback-service-implementation.md (Phase 2.2)
