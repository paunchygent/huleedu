---
type: decision
id: ADR-0016
status: proposed
created: 2025-11-27
last_updated: 2025-11-27
---

# ADR-0016: CJ Assessment Prompt Caching Strategy

## Status
Proposed

## Context
CJ Assessment makes many LLM calls with similar prompt structure (rubric, instructions) but different essay pairs. Anthropic supports prompt caching to reduce costs. Options:
1. No caching (simple but expensive)
2. Cache entire prompts (risk of stale data)
3. Cache static blocks only (system, rubric, tool schema)

## Decision
Implement **cacheable block separation** with TTL-based caching.

### Cacheable vs Non-Cacheable

| Block Type | Cacheable | TTL |
|------------|-----------|-----|
| System prompt | Yes | 3600s (assignment scope) |
| Rubric/instructions | Yes | 3600s (assignment scope) |
| Tool schema | Yes | 300s (service constant) |
| Essay text | No | - |

### TTL Configuration

| Context | TTL | Rationale |
|---------|-----|-----------|
| Assignment/batch runs | 3600s | Stable, repeated prompts |
| Ad-hoc/dev | 300-600s | Rapid iteration |

### Warm-up Strategy
1. Seed once per unique prompt hash before dispatching cohort
2. After seed, cache miss rate should drop to ≤20%
3. Light jitter on scheduling to prevent thundering herd

## Consequences

### Positive
- 50%+ cost reduction on repeated prompts
- No essay data cached (privacy)
- Per-assignment caching scope

### Negative
- TTL management complexity
- Warm-up overhead for first request

## Metrics
- `llm_provider_prompt_cache_events_total{result}`
- `llm_provider_prompt_cache_tokens_total{direction}`
- `llm_provider_cache_scope_total{scope,result}`

## References
- docs/operations/cj-assessment-foundation.md
- Anthropic Message Batches API documentation
