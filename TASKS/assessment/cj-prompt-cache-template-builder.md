---
id: cj-prompt-cache-template-builder
title: CJ Prompt Cache Template Builder
type: task
status: in_progress
priority: medium
domain: assessment
owner_team: agents
created: '2025-11-22'
last_updated: '2025-11-22'
service: cj_assessment_service, llm_provider_service
owner: ''
program: ''
related:
  - TASKS/infrastructure/lps-rate-limiting-implementation.md
labels:
  - cache-optimization
  - cost-reduction
  - anthropic-api
---

# TASK: CJ Prompt Cache Template Builder

**Created**: 2025-11-22
**Status**: 🔄 IN PROGRESS
**Priority**: P2 MEDIUM
**Services**: CJ Assessment Service, LLM Provider Service
**Related**: Anthropic Prompt Caching Infrastructure (completed 2025-11-21)

---

## Problem Statement

### Current State

CJ prompts are ~60-70% static content (1,135-2,780 tokens) but only the system prompt is cached. The user message combines static assessment context with dynamic essay content in a monolithic string, preventing selective caching of stable sections.

**Current Caching**:
```
system: "You are a comparative judge..." [CACHED]
messages: [
  {
    role: "user",
    content: "Student Assignment: ...\nAssessment Criteria: ...\nEssay A: ...\nEssay B: ..." [NOT CACHED]
  }
]
```

**Token Distribution** (per comparison):
- Static: ~1,250-2,250 tokens (system + assessment context + instructions)
- Dynamic: ~470-1,830 tokens (essay A + B)
- **Waste**: 50-70% of input tokens re-processed on each request

### Impact

**Cost**:
- Assignment batches (10 essays × 10 anchors = 100 comparisons): ~180K tokens wasted
- At $3/M input tokens: ~$0.54 per batch
- Annual projection (1000 batches): ~$540 wasted

**Throughput**:
- Redundant token processing increases API latency
- Prevents cost-effective backfilling at scale

---

## Objectives

### Primary Goals

1. **Implement Multi-Block Caching**: Separate static (cacheable) from dynamic (essay-specific) content using Anthropic's documented prompt caching API

2. **Achieve >80% Cache Hit Rate**: For assignment-scoped batches after initial warmup (first 10 comparisons)

3. **Reduce Token Costs by 30-50%**: Through selective caching of static content

4. **Maintain Backward Compatibility**: Support legacy monolithic `user_prompt` during migration

### Constraints

- **Anthropic API Requirements**:
  - TTL values: `"5m"` (default) or `"1h"` (extended) only
  - Minimum 1024 tokens for caching to activate
  - 1h TTL blocks must precede 5m TTL blocks
  - Cache available after first response (concurrent requests may miss)

- **Architecture**:
  - CJ keeps simple domain model (no Anthropic-specific logic)
  - LPS handles provider-specific transformations
  - DDD service autonomy preserved

---

## Technical Design

### Phase 1: Template Builder (CJ Service)

**New Files**:
- `services/cj_assessment_service/models_prompt.py`: Data models for prompt blocks
- `services/cj_assessment_service/cj_core_logic/prompt_templates.py`: Template builder logic

**Modified Files**:
- `services/cj_assessment_service/cj_core_logic/pair_generation.py`: Replace `_build_comparison_prompt()`

**Key Classes**:
```python
class PromptBlock:
    target: "system" | "user_content"
    content: str
    cacheable: bool
    ttl: "5m" | "1h"
    content_hash: str  # SHA256 for fragmentation tracking

class PromptTemplateBuilder:
    @staticmethod
    def build_static_blocks(assessment_context, use_extended_ttl) -> list[PromptBlock]

    @staticmethod
    def render_dynamic_essays(essay_a, essay_b) -> list[PromptBlock]
```

### Phase 2: LPS Multi-Block Cache Support

**Modified Files**:
- `libs/common_core/src/common_core/api_models/llm_provider.py`: Add `prompt_blocks` field
- `services/llm_provider_service/implementations/anthropic_provider_impl.py`: Multi-block caching logic
- `services/llm_provider_service/config.py`: Add `USE_EXTENDED_TTL_FOR_SERVICE_CONSTANTS`

**Key Changes**:
```python
# LLMComparisonRequest
class LLMComparisonRequest:
    user_prompt: str  # Legacy
    prompt_blocks: list[dict] | None  # New (preferred)

# Anthropic Provider
def _make_api_request():
    system_blocks = _build_system_blocks(system_prompt)  # Array with cache_control
    tools_with_cache = _build_tools_with_cache()  # Tool schema cached
    user_content = _build_user_content_from_blocks(prompt_blocks)  # Selective caching
```

### Phase 3: Observability

**Modified Files**:
- `services/llm_provider_service/metrics.py`: Add block-level metrics
- `observability/grafana/dashboards/HuleEdu_LLM_Prompt_Cache.json`: New panels
- `observability/prometheus/rules/service_alerts.yml`: Tune alerts

**New Metrics**:
- `llm_provider_prompt_blocks_total{target, cacheable, ttl}`
- `llm_provider_cache_scope_total{scope}`  # assignment vs ad-hoc
- `llm_provider_prompt_tokens_histogram{section}`  # static vs dynamic

---

## Implementation Plan

### Phase 1: Template Builder Foundation (COMPLETED 2025-11-22)
- [x] Create `models_prompt.py` with `PromptBlock`, `CacheableBlockTarget`, `AnthropicCacheTTL`
- [x] Create `cj_core_logic/prompt_templates.py` with `PromptTemplateBuilder`
- [ ] Integrate with `pair_generation.py` (replace `_build_comparison_prompt()`) - NEXT SESSION
- [x] Write Rule 075 compliant unit tests (40 tests, 16 parametrized, all passing)

### Phase 2: LPS Multi-Block Cache (2 days)
- [ ] Extend `LLMComparisonRequest` with `prompt_blocks` field
- [ ] Modify `anthropic_provider_impl.py`:
  - [ ] `_build_system_blocks()` - wrap system prompt in array
  - [ ] `_build_tools_with_cache()` - add cache_control to tool schema
  - [ ] `_build_user_content_from_blocks()` - selective caching + TTL ordering
- [ ] Add `USE_EXTENDED_TTL_FOR_SERVICE_CONSTANTS` config
- [ ] Write 8 integration tests for block caching

### Phase 3: Observability (1 day)
- [ ] Add block-level Prometheus metrics
- [ ] Extend Grafana dashboard with 3 new panels
- [ ] Update Prometheus alerts (tune thresholds, add TTL ordering violation)

### Phase 4: Testing & Validation (1.5 days)
- [ ] Write performance benchmarks:
  - [ ] Assignment cache warmup (10 essays × 10 anchors)
  - [ ] Multi-iteration stability loop
  - [ ] Concurrency behavior
  - [ ] TTL effectiveness (5min vs 1h)
  - [ ] Below-threshold graceful handling
- [ ] Run acceptance criteria validation

### Phase 5: Configuration & Documentation (0.5 days)
- [ ] Add configuration defaults (CJ and LPS)
- [ ] Update `docs/operations/cj-assessment-foundation.md`
- [ ] Update `.claude/rules/020.20-cj-llm-prompt-contract.md`
- [ ] Run format, lint, typecheck

---

## Acceptance Criteria

### Functional Requirements

- [ ] Static blocks generate consistent hashes for same assignment
- [ ] TTL values limited to "5m" or "1h" (no invalid values sent)
- [ ] 1h TTL blocks precede 5m TTL blocks in all requests
- [ ] System blocks structured as array (not string)
- [ ] Legacy `user_prompt` fallback works (backward compat)
- [ ] Requests <1024 tokens process without errors (graceful degradation)

### Performance Requirements

- [ ] Cache hit rate >80% for assignment batches (after first 10 comparisons)
- [ ] Token savings measurable (`cache_read_input_tokens` tracked)
- [ ] No latency regression vs baseline
- [ ] 5min TTL sufficient for typical batches (<5min completion)

### Observability Requirements

- [ ] Grafana dashboard shows hit rate by scope (assignment/ad-hoc)
- [ ] Block-level metrics track cacheable vs non-cacheable
- [ ] Prometheus alert fires on low hit rate (<40% for assignments)
- [ ] TTL ordering violations tracked (should be zero)

### Code Quality Requirements

- [ ] All unit tests passing (20 new tests: 12 CJ + 8 LPS)
- [ ] All integration tests passing
- [ ] `pdm run typecheck-all` passing
- [ ] `pdm run format-all && pdm run lint-fix --unsafe-fixes` passing

---

## Migration Strategy

### Week 1: Dual-Send Pattern

**CJ Changes**:
1. Generate both `user_prompt` (legacy) and `prompt_blocks` (new)
2. Send both in `LLMComparisonRequest`
3. Log which field was used

**LPS Changes**:
1. Prefer `prompt_blocks` if present
2. Fallback to `user_prompt` if absent
3. Emit metric: `llm_provider_request_source_total{source="blocks|legacy"}`

**Monitoring**:
- Track `source=blocks` adoption rate (should be 100% for new CJ requests)
- Watch for errors in either mode

### Week 2: Validation & Tuning

**Metrics Analysis**:
1. Compare cache hit rates: `prompt_blocks` vs `user_prompt` baseline
2. Validate token savings: `cache_read_input_tokens` increasing?
3. Check cost: Are 5min writes (1.25x) delivering sufficient hit rate?

**Tuning Decisions**:
- If batches complete <5min: keep `USE_EXTENDED_TTL=false`
- If long backfills (>10min): enable `USE_EXTENDED_TTL=true` for service constants
- If hit rate low (<40%): investigate fragmentation

### Week 3+: Stabilization

**Success Criteria**:
- Hit rate >80% for assignment batches (sustained for 1 week)
- Zero TTL ordering violations
- Token savings >50% of static content
- No performance regressions

---

## Risks & Mitigations

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| TTL too short (cache expires mid-batch) | Reduced savings | Low (5min sufficient for most) | Monitor batch duration; opt-in to 1h if needed |
| Cache fragmentation (many unique hashes) | Low hit rate | Medium | Hash stability tests; template determinism enforcement |
| TTL ordering violation | API errors | Low | Unit tests + runtime validation + Prometheus alert |
| Below 1024 tokens (no caching) | Reduced savings | Low (most assignments >1024) | Graceful degradation (no action needed) |
| Concurrency race (first request misses) | Slightly lower hit rate | High (expected) | Document as normal; first wave = writes, second = reads |
| Cost increase (2x for 1h writes) | Budget impact | Low (5min default) | Default to 5min; only enable 1h if ROI proven |

---

## Testing Strategy

### Unit Tests (20 tests)

**CJ Service** (12 tests in `test_prompt_templates.py`):
- `test_static_blocks_hash_stability`
- `test_ttl_mapping_five_min_default`
- `test_ttl_mapping_one_hour_extended`
- `test_ttl_ordering_with_mixed_ttls`
- `test_essay_blocks_not_cacheable`
- `test_placeholder_substitution`
- `test_block_target_assignment`
- `test_assessment_context_formatting`
- `test_empty_context_handling`
- `test_content_hash_computation`
- `test_block_ordering_user_content`
- `test_extended_ttl_flag_propagation`

**LPS Service** (8 tests in `test_prompt_block_caching.py`):
- `test_prompt_blocks_preferred_over_user_prompt`
- `test_legacy_user_prompt_fallback`
- `test_system_blocks_always_array`
- `test_cache_control_omitted_when_disabled`
- `test_ttl_ordering_enforcement`
- `test_tools_cache_control_on_extended_ttl`
- `test_minimum_token_threshold_graceful`
- `test_metadata_preserved_with_blocks`

### Performance Benchmarks

**File**: `tests/performance/test_prompt_cache_effectiveness.py`

1. **Assignment Cache Warmup**: 100 comparisons, >80% hit rate after first 10
2. **Multi-Iteration Stability**: 3 iterations × 10 comparisons, >80% hit rate after iteration 1
3. **Concurrency Behavior**: Parallel requests, cache available after first response
4. **TTL Effectiveness**: 5min vs 1h cost comparison
5. **Below-Threshold Graceful**: <1024 tokens processes without errors

---

## Success Metrics (Post-Deployment)

### Target Improvements

**Token Savings**:
- Static content: 50-70% cost reduction (1.25x writes → 0.1x reads after hit)
- Overall: 30-50% total input token cost reduction

**Cache Hit Rates**:
- Assignment batches: >80% (after first 10 comparisons)
- Ad-hoc batches: >40%
- Service-level constants: >90% (if extended TTL enabled)

**Cost Example** (100 comparisons, 2000 static + 1000 dynamic tokens):
```
No caching: 300K tokens

With caching (5min TTL, 90% hit rate):
  First 10: 35K tokens (writes + dynamic)
  Next 90: 108K tokens (reads + dynamic)
  Total: 143K tokens → 52% savings
```

### Monitoring Plan

**Daily** (First 2 weeks):
- Review `HuleEdu_LLM_Prompt_Cache` dashboard
- Check for `LLMPromptCacheLowHitRate` alerts
- Validate TTL ordering (zero violations)

**Weekly**:
- Cache effectiveness report: hit rate trends, tokens saved
- Fragmentation analysis: unique hash count per scope

**Monthly**:
- Cost analysis: actual savings vs projection
- TTL tuning: evaluate if extended TTL needed

---

## Timeline

**Total**: 6 days (1.2 weeks)

- Days 1-1.5: Phase 1 (CJ Template Builder)
- Days 2-3.5: Phase 2 (LPS Multi-Block Cache)
- Day 4: Phase 3 (Observability)
- Day 5: Phase 4 (Testing & Validation)
- Day 6: Phase 5 (Configuration & Docs)

---

## References

**Anthropic Documentation**:
- Prompt Caching Guide: <https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching>
- TTL values: "5m" (default, 1.25x write cost) or "1h" (extended, 2x write cost)
- Cache reads: 0.1x base input cost
- Minimum cacheable prefix: 1024 tokens
- TTL ordering: 1h must precede 5m
- 20-block lookback window

**Codebase References**:
- Current prompt composition: `services/cj_assessment_service/cj_core_logic/pair_generation.py:311-356`
- Current caching: `services/llm_provider_service/implementations/anthropic_provider_impl.py:372-386`
- Metadata contract: `libs/common_core/src/common_core/api_models/llm_provider.py`
- Metrics: `services/llm_provider_service/metrics.py`
- Dashboard: `observability/grafana/dashboards/HuleEdu_LLM_Prompt_Cache.json`

**Related Tasks**:
- Prompt caching infrastructure (completed 2025-11-21)
- LPS rate limiting implementation (pending)
- CJ LLM serial bundle validation fixes (completed 2025-11-21)

---

## Notes

**TTL Strategy**: Default to 5min for all blocks. Most CJ assignments complete within 5min, making extended 1h TTL unnecessary for typical usage. Extended TTL is opt-in for long-running backfills if ROI proven.

**Graceful Degradation**: Requests below 1024 token threshold process normally without caching. No client-side logic needed - API handles automatically.

**Service Autonomy**: CJ sends simple `PromptBlock` list; LPS transforms to Anthropic-specific format (system array, cache_control). Other LPS providers (OpenAI, etc.) can implement differently.
