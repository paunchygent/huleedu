---
id: lps-rate-limiting-implementation
title: Lps Rate Limiting Implementation
type: task
status: in_progress
priority: high
domain: infrastructure
owner_team: agents
created: '2025-11-21'
last_updated: '2025-11-22'
service: llm_provider_service
owner: ''
program: ''
related: []
labels: [rate-limiting, anthropic, architecture-validated]
---

# TASK: LLM Provider Service Rate Limiting Implementation

**Created**: 2025-11-21
**Architectural Review**: 2025-11-22 ✅ APPROVED WITH MODIFICATIONS
**Status**: Approved - Ready for Implementation
**Priority**: P1 (High - Production Risk Under Load)
**Type**: Feature Implementation (Multi-PR)
**Related**: CJ Assessment Service, LLM Provider Service

---

## Architectural Review Findings (2025-11-22)

### Review Status: ✅ APPROVED WITH MODIFICATIONS

**Reviewer**: Research-Diagnostic Agent + Architecture Validation
**Verdict**: 5-PR plan is architecturally sound and highly feasible

### Key Findings

✅ **Validation Complete**: All task document claims validated with file:line evidence
✅ **Architecture Alignment**: Follows HuleEdu DDD/Clean Code patterns (Protocol-based DI, small modular files)
✅ **Implementation Feasibility**: All integration points verified and ready (Dishka DI, Prometheus metrics, Pydantic config)
✅ **Testing Strategy**: Unit + integration test patterns established in codebase

### Required Modifications

1. **PR1 Token Estimation**: Use over-estimation strategy (`len(prompt) // 3.3` instead of `// 4`) to account for non-English text and special characters. Validate accuracy via PR2 header data.
2. **PR2 Header Names**: Anthropic uses `anthropic-ratelimit-*` headers (not `x-ratelimit-*`). Update all references.
3. **PR3 Naming Convention**: Use uppercase `MAX_CONCURRENT_LLM_REQUESTS` to match HuleEdu configuration standards.
4. **PR4 Serial Bundle**: Explicitly document that delay applies between bundles (8-request batches), not within bundles.
5. **PR5 Validation Pattern**: Use Pydantic `@field_validator` pattern (already established in config.py) instead of separate startup validation.

### Critical Implementation Concerns

**Serial Bundle Interaction**: Ensure rate limiter is called in `comparison_processor_impl.py` batch processing path, not just in individual provider implementations. Rate limiting must apply to all request paths (per_request and serial_bundle modes).

**Token Estimation Accuracy**: Start with 20% over-estimation, monitor actual token usage via PR2 headers, tune formula based on real data.

**Retry-After Cap**: Current 5-second cap in `anthropic_provider_impl.py:599` may be too aggressive. PR2 should log actual retry-after values to determine if cap adjustment needed.

### Pre-Implementation Actions

1. Use Context7 to check if Anthropic SDK provides tokenization utility (may eliminate estimation need)
2. Read `services/llm_provider_service/implementations/comparison_processor_impl.py` to understand batch processing path
3. Validate rate limiter integration points for serial bundle mode

### Architectural Compliance

- ✅ **DDD/Clean Code**: Rate limiter follows Protocol + Implementation pattern
- ✅ **Inversion of Control**: Dishka DI ready for RateLimiterProtocol injection (APP scope)
- ✅ **Small Modular Files**: All PRs stay under 400 LoC limit per file
- ✅ **Explicit Configuration**: Pydantic Settings pattern, no magic values

---

## Pre-Implementation Research (2025-11-22)

### Context7 Investigation: Anthropic Tokenization

**Research Question**: Does Anthropic SDK provide offline tokenization utilities to eliminate estimation need?

**Findings**:
- ✅ SDK provides `client.messages.count_tokens(model, messages)` method
- ❌ Method makes an **API call** (not local/offline tokenization)
- ❌ No official Python offline tokenizer library from Anthropic
- ⚠️ TypeScript tokenizer (`anthropic-tokenizer-typescript`) is "rough approximation for Claude 3 models"

**Conclusion**: Character-based estimation with 20% over-estimation (`len(prompt) // 3.3`) is the most practical approach. Making an API call to count tokens before making another API call for comparison would be inefficient and defeat the purpose of rate limiting.

**Reference**: `/anthropics/anthropic-sdk-python` (Context7 library ID)

---

### Serial Bundle Batch Processing Path Analysis

**File Analyzed**: `services/llm_provider_service/implementations/comparison_processor_impl.py`

**Key Findings**:

1. **`process_comparison_batch()` (lines 149-164)**:
   - Processes batch items **sequentially** in a for-loop
   - Calls `process_comparison()` for each item individually
   - Returns list of `LLMOrchestratorResponse` results

2. **`process_comparison()` (lines 42-148)**:
   - Line 60: `result = await provider_impl.generate_comparison(...)`
   - **This is the rate limiting integration point**
   - Called by both single requests and batch processing

**Architectural Validation**:
- ✅ Rate limiting in `anthropic_provider_impl.py` **automatically covers both modes**:
  - **PER_REQUEST mode**: Single `process_comparison()` call → rate limited
  - **SERIAL_BUNDLE mode**: Loop through `process_comparison()` calls → each call rate limited
- ✅ No separate batch-specific rate limiting needed
- ✅ Token estimation happens per-request (line 179: `len(full_prompt) // 3.3`)

**Integration Point**:
```python
# services/llm_provider_service/implementations/anthropic_provider_impl.py
async def generate_comparison(...):
    # 1. Estimate tokens
    estimated_tokens = len(full_prompt) // 3.3  # 20% over-estimation

    # 2. Acquire rate limit capacity (NEW - PR1)
    await self.rate_limiter.acquire(estimated_tokens)

    # 3. Execute with retry
    result = await self.retry_manager.with_retry(...)
```

**Conclusion**: PR1 implementation in `anthropic_provider_impl.py` will correctly rate limit all request paths without requiring changes to `comparison_processor_impl.py`.

---

### Rate Limiter Integration Points Validation

**Provider Implementations** (all inherit from `LLMProviderProtocol`):
- ✅ `anthropic_provider_impl.py` - Primary target for PR1
- ⏭️ `openai_provider_impl.py` - Future extension (different rate limits)
- ⏭️ `google_provider_impl.py` - Future extension
- ⏭️ `openrouter_provider_impl.py` - Future extension

**DI Container** (`services/llm_provider_service/di.py`):
- ✅ Uses Dishka Provider pattern
- ✅ APP scope available for singleton rate limiter
- ✅ Provider-specific injection ready (line 76-97: provider map creation)

**Configuration** (`services/llm_provider_service/config.py`):
- ✅ Lines 49-50: `rate_limit_requests_per_minute`, `rate_limit_tokens_per_minute` already exist
- ✅ Pydantic `@field_validator` pattern established (lines 269-275: watermark validation example)
- ✅ Ready for PR5 validation additions

**Metrics** (`services/llm_provider_service/metrics.py`):
- ✅ Prometheus `CollectorRegistry` injected via DI
- ✅ Existing error metrics (lines 48-59) provide pattern for rate limit metrics
- ✅ Ready for new metrics: `llm_provider_rate_limit_waits_total`, `llm_provider_rate_limit_wait_duration_seconds`

---

### Implementation Recommendations

Based on comprehensive research and code analysis:

1. **Token Estimation Strategy** (PR1):
   - Use `len(full_prompt) // 3.3` (20% over-estimation)
   - Monitor accuracy via PR2 rate limit headers
   - Tune formula if actual token usage shows consistent deviation
   - Document limitation: estimation accuracy varies by language/content type

2. **Rate Limiter Scope** (PR1):
   - Use Dishka APP scope (singleton per provider)
   - Share token bucket state across all requests to same provider
   - Ensure thread-safety with `asyncio.Lock`

3. **Serial Bundle Considerations** (PR1 + PR4):
   - Rate limiting applies per-request within batch loop (correct behavior)
   - Inter-request delay (PR4) applies between loop iterations
   - No special batch-specific rate limiting logic needed

4. **Header Validation** (PR2):
   - Log actual `retry-after` values to validate 5-second cap
   - Monitor `anthropic-ratelimit-requests-remaining` and `anthropic-ratelimit-tokens-remaining`
   - Compare estimated vs actual token usage to tune estimation formula

5. **Configuration Validation** (PR5):
   - Use `@field_validator` pattern from existing code (not separate startup validation)
   - Warn (don't block) when limits exceed tier thresholds
   - Document tier limits in validator docstrings

---

## Problem Statement

### Current State: Reactive Rate Limiting Only

The LLM Provider Service (LPS) currently sends API requests to Anthropic **as fast as the queue processor can dequeue them**, with no preventive rate limiting mechanisms. This creates moderate-to-high risk of hitting provider rate limits under batch processing loads.

**Evidence**: Comprehensive investigation completed 2025-11-21
- **Report**: See research-diagnostic agent findings in session transcript
- **Key Finding**: Queue processor has 0.5s delay only when queue is **empty**, no delay between consecutive requests
- **Risk**: Under high load (50-100 comparison batches), system can exceed Anthropic tier 1 limits (50 req/min)

### What Works Today

✅ **Semaphore limiting**: CJ → LPS HTTP requests limited to 3 concurrent
✅ **Queue resilience**: Redis queue prevents request loss during restarts
✅ **Retry logic**: Exponential backoff on 429 errors (4s → 8s → 16s)
✅ **Configuration exists**: Rate limit settings defined in `ProviderConfig`

### What's Missing

❌ **Proactive rate limiting**: No throttling based on provider quotas
❌ **Token-aware limiting**: Only considers request count, not token usage
❌ **Rate limit header reading**: Response headers ignored
❌ **Inter-request pacing**: Requests sent back-to-back (only network latency limits rate)
❌ **Configuration enforcement**: `rate_limit_requests_per_minute` defined but unused

---

## Investigation Summary

### Request Flow Analysis

```
CJ Assessment Service
  ↓ (Semaphore: max 3 concurrent HTTP)
LLM Provider Service - Redis Queue
  ↓ (Sequential dequeue, NO delays)
Queue Processor
  ↓ (Immediate API call, NO throttling)
Anthropic API
  ↓ (429 errors → reactive retry)
```

### Code Evidence

**File**: `services/llm_provider_service/implementations/queue_processor_impl.py:112-163`
- Queue processor loop: `while self._running: await dequeue() → process() → repeat`
- Only delay: `await asyncio.sleep(0.5)` when queue **empty**
- **NO delay between consecutive requests**

**File**: `services/llm_provider_service/config.py:49-50`
- Settings exist: `rate_limit_requests_per_minute`, `rate_limit_tokens_per_minute`
- **Never enforced**: Zero usage in implementations

**File**: `services/cj_assessment_service/implementations/llm_interaction_impl.py:135-136`
- Semaphore value: `getattr(settings, "max_concurrent_llm_requests", 3)`
- **Not configurable**: Setting doesn't exist in config.py

### Risk Assessment

| Load Level | Comparisons/Batch | Risk | Impact |
|------------|-------------------|------|--------|
| Normal | ≤30 | LOW | Natural latency keeps under limits |
| High | 50-100 | **MODERATE-HIGH** | Can exceed 50 req/min tier 1 limit |
| Serial Bundle | 100+ | **VERY HIGH** | Processes 8 requests at once |

---

## Implementation Plan: 5 Pull Requests

### PR1: Token Bucket Rate Limiter (Core Implementation)

**Priority**: P0 - Critical
**Complexity**: Medium (150 LoC)
**Dependencies**: None
**Target**: `services/llm_provider_service/`

#### Scope

Implement token bucket algorithm to enforce provider-specific rate limits based on both request count and token usage.

#### Files to Create

1. **`implementations/rate_limiter_impl.py`** (NEW)
   - `TokenBucketRateLimiter` class
   - Dual-bucket: requests/min + tokens/min
   - Async `acquire(estimated_tokens)` method
   - Automatic token refill logic
   - Lines: ~120

2. **`protocols/rate_limiter.py`** (NEW)
   - `RateLimiterProtocol` interface
   - Lines: ~20

3. **`tests/unit/test_rate_limiter.py`** (NEW)
   - Token bucket behavior tests
   - Refill rate verification
   - Concurrent access tests
   - Lines: ~150

#### Files to Modify

1. **`implementations/anthropic_provider_impl.py`**
   - Add `rate_limiter: RateLimiterProtocol` to `__init__`
   - Call `await self.rate_limiter.acquire(estimated_tokens)` before API call (line ~100)
   - Estimate tokens: `len(full_prompt) // 3.3` (20% over-estimation to account for non-English text and special characters)
   - **Note**: Validate estimation accuracy via PR2 header data, tune formula based on real token usage
   - **Consider**: Check if Anthropic SDK provides tokenization utility (may eliminate estimation need)
   - Lines changed: ~15

2. **`di.py`**
   - Add `RateLimiterProvider` to Dishka container
   - Scope: `APP` (singleton)
   - Lines changed: ~20

3. **`config.py`**
   - Ensure `rate_limit_requests_per_minute` defaults to 50 (Anthropic tier 1)
   - Ensure `rate_limit_tokens_per_minute` defaults to 40000 (Anthropic tier 1)
   - Lines changed: ~5

#### Acceptance Criteria

- [ ] `TokenBucketRateLimiter` enforces configured request/min limit
- [ ] `TokenBucketRateLimiter` enforces configured token/min limit
- [ ] Integration test: 100 requests respect 50 req/min limit (takes ~2 minutes)
- [ ] Unit tests: All edge cases covered (empty bucket, concurrent access, refill)
- [ ] No `type: ignore` or `cast()` used
- [ ] All quality gates pass (typecheck, lint, format, tests)

#### Testing Strategy

**Unit Tests**:
- `test_request_rate_limiting` - Verify requests/min enforcement
- `test_token_rate_limiting` - Verify tokens/min enforcement
- `test_bucket_refill` - Verify automatic token replenishment
- `test_concurrent_acquire` - Verify thread-safety with asyncio.Lock
- `test_wait_calculation` - Verify accurate wait time computation

**Integration Test**:
- `test_rate_limiter_integration_with_anthropic_provider` - Verify real API call pacing

---

### PR2: Rate Limit Header Reading & Dynamic Adjustment

**Priority**: P1 - High
**Complexity**: Low (50 LoC)
**Dependencies**: PR1 (optional - can work standalone)
**Target**: `services/llm_provider_service/`

#### Scope

Read Anthropic rate limit headers from API responses and log quota status. Optionally adjust rate limiter dynamically based on remaining quota.

#### Files to Modify

1. **`implementations/anthropic_provider_impl.py`**
   - After successful API call (line ~150), extract headers:
     - `anthropic-ratelimit-requests-remaining`
     - `anthropic-ratelimit-requests-reset`
     - `anthropic-ratelimit-tokens-remaining`
     - `anthropic-ratelimit-tokens-reset`
   - Log warnings when quota low (< 5 requests or < 10k tokens)
   - **Additional**: Log actual `retry-after` values to validate current 5-second cap (line 599)
   - **Note**: Header names are Anthropic-specific; other providers use different formats
   - Lines changed: ~25

2. **`tests/unit/test_anthropic_provider.py`**
   - Mock response headers
   - Verify header extraction
   - Verify warning logs
   - Lines added: ~30

#### Acceptance Criteria

- [ ] Rate limit headers extracted from all successful responses
- [ ] Warning logged when requests_remaining < 5
- [ ] Warning logged when tokens_remaining < 10000
- [ ] Headers logged at DEBUG level for monitoring
- [ ] No impact on error handling flow
- [ ] All quality gates pass

#### Testing Strategy

**Unit Tests**:
- `test_rate_limit_headers_extracted` - Verify headers read
- `test_low_quota_warnings` - Verify warnings logged
- `test_missing_headers_handled` - Verify graceful handling if headers absent

---

### PR3: Configurable CJ Semaphore Limit

**Priority**: P2 - Medium
**Complexity**: Trivial (10 LoC)
**Dependencies**: None
**Target**: `services/cj_assessment_service/`

#### Scope

Make the CJ → LPS HTTP request concurrency limit configurable via environment variable instead of hardcoded fallback.

#### Files to Modify

1. **`config.py`**
   - Add `MAX_CONCURRENT_LLM_REQUESTS: int = Field(default=3, ...)`
   - Lines added: ~5

2. **`implementations/llm_interaction_impl.py`**
   - Change `getattr(self.settings, "max_concurrent_llm_requests", 3)`
   - To: `self.settings.MAX_CONCURRENT_LLM_REQUESTS`
   - Lines changed: ~2

3. **`.env.example`** (if exists)
   - Document `MAX_CONCURRENT_LLM_REQUESTS=3`
   - Lines added: ~2

4. **`README.md`**
   - Document environment variable in configuration section
   - Lines added: ~5

#### Acceptance Criteria

- [ ] `MAX_CONCURRENT_LLM_REQUESTS` configurable via env var
- [ ] Default value remains 3 (backward compatible)
- [ ] Setting properly typed (no `getattr` fallback)
- [ ] Documented in README
- [ ] All quality gates pass

#### Testing Strategy

**Manual Test**:
- Set `MAX_CONCURRENT_LLM_REQUESTS=5` in .env
- Verify semaphore uses 5 (check logs or behavior)

---

### PR4: Inter-Request Delay in Queue Processor

**Priority**: P1 - High
**Complexity**: Medium (80 LoC)
**Dependencies**: None
**Target**: `services/llm_provider_service/`

#### Scope

Add configurable minimum delay between consecutive API calls in the queue processor to provide baseline rate limiting even without token bucket.

#### Files to Modify

1. **`config.py`**
   - Add `QUEUE_MIN_DELAY_BETWEEN_REQUESTS_MS: int = Field(default=100, ...)`
   - Description: "Minimum milliseconds between consecutive API calls (prevents burst requests)"
   - Lines added: ~5

2. **`implementations/queue_processor_impl.py`**
   - Track `last_process_time` in `_process_queue_loop`
   - Calculate elapsed since last request/bundle
   - Add `await asyncio.sleep(min_delay - elapsed)` if under threshold
   - Apply to both PER_REQUEST and SERIAL_BUNDLE modes:
     - **PER_REQUEST**: Delay between individual requests
     - **SERIAL_BUNDLE**: Delay between bundles (8-request batches), not within bundles
   - Lines changed: ~30

3. **`tests/unit/test_queue_processor.py`**
   - Test minimum delay enforcement
   - Verify timing with mock time
   - Lines added: ~40

#### Acceptance Criteria

- [ ] Minimum 100ms delay between consecutive requests (configurable)
- [ ] Delay applied in PER_REQUEST mode
- [ ] Delay applied in SERIAL_BUNDLE mode (between bundles)
- [ ] Delay NOT applied when queue empty (existing 0.5s poll unchanged)
- [ ] No delay if natural processing time exceeds minimum
- [ ] All quality gates pass

#### Testing Strategy

**Unit Tests**:
- `test_minimum_delay_enforced` - Mock time, verify sleep called
- `test_no_delay_when_slow_processing` - Long API call, verify no extra delay
- `test_delay_between_bundles` - Serial bundle mode, verify delay between batches

**Integration Test**:
- Process 10 requests, measure total time ≥ (10-1) * 100ms = 900ms

---

### PR5: Startup Rate Limit Configuration Validation

**Priority**: P2 - Medium
**Complexity**: Low (40 LoC)
**Dependencies**: PR1 (for full validation)
**Target**: `services/llm_provider_service/`

#### Scope

Add Pydantic field validation to warn if configured rate limits exceed known provider limits, preventing misconfigurations.

#### Files to Modify

1. **`config.py` (ProviderConfig class)**
   - Add `@field_validator("rate_limit_requests_per_minute")` method
   - Add `@field_validator("rate_limit_tokens_per_minute")` method
   - Warn if Anthropic RPM > 50 (tier 1 limit) or TPM > 40000 (tier 1 limit)
   - Follow existing pattern from `config.py:269-275` (watermark validation example)
   - **Note**: Use logging.warning() within validator (not raise ValueError) since warnings shouldn't block startup
   - Lines added: ~30

2. **`tests/unit/test_config_validation.py`** (NEW or append to existing)
   - Test validation warnings when limits exceed tier thresholds
   - Test no warnings when limits are within bounds
   - Test validation with missing/None values (use defaults)
   - Lines: ~25

#### Acceptance Criteria

- [ ] Warning logged if Anthropic RPM exceeds tier 1 limit (50)
- [ ] Warning logged if Anthropic TPM exceeds tier 1 limit (40k)
- [ ] Warning logged if rate limits not configured (using defaults)
- [ ] Validation runs on service startup
- [ ] Does NOT block startup (warnings only)
- [ ] All quality gates pass

#### Testing Strategy

**Unit Tests**:
- `test_warns_on_excessive_rpm` - Set RPM=100, verify warning
- `test_warns_on_missing_config` - Set RPM=None, verify warning
- `test_no_warning_on_valid_config` - Set RPM=40, verify no warning

---

## Success Criteria

### Overall Implementation Success

- [ ] All 5 PRs merged and deployed
- [ ] No production 429 errors under normal load (≤50 comparisons/batch)
- [ ] Rate limit metrics added to Prometheus
- [ ] Documentation updated (README, .env.example)
- [ ] All quality gates pass (typecheck, lint, format, tests)
- [ ] Zero `type: ignore` or `cast()` usage

### Performance Requirements

- [ ] Rate limiting overhead < 50ms per request
- [ ] No measurable impact on batch completion time under normal load
- [ ] Graceful degradation under high load (requests delayed, not dropped)

### Monitoring

Add Prometheus metrics:
- `llm_provider_rate_limit_waits_total` - Count of rate limit delays
- `llm_provider_rate_limit_wait_duration_seconds` - Histogram of wait times
- `llm_provider_429_errors_total` - Count of rate limit errors (should decrease)

---

## Implementation Order

### Phase 1: Foundation (Week 1)
1. **PR1**: Token Bucket Rate Limiter - Core implementation
2. **PR4**: Inter-Request Delay - Immediate baseline protection

### Phase 2: Enhancement (Week 2)
3. **PR2**: Rate Limit Headers - Better observability
4. **PR3**: Configurable Semaphore - Operational flexibility

### Phase 3: Validation (Week 2-3)
5. **PR5**: Startup Validation - Configuration safety

---

## Testing Strategy

### Unit Tests (Per PR)

Each PR includes comprehensive unit tests covering:
- Happy path behavior
- Edge cases (empty buckets, concurrent access, etc.)
- Error conditions
- Configuration variations

**Total new tests**: ~250 lines across 5 test files

### Integration Tests

**New Test**: `tests/integration/test_rate_limiting_integration.py`

Test scenarios:
1. **Burst protection**: Submit 100 requests, verify rate stays ≤ configured limit
2. **Token bucket refill**: Wait 60s, verify full quota restored
3. **429 handling**: Mock 429 response, verify backoff + retry
4. **Mixed load**: Concurrent batches from multiple CJ instances

### Load Testing (Manual)

**Test Plan**:
1. Configure Anthropic tier 1 limits (50 RPM, 40k TPM)
2. Submit batch with 100 comparisons
3. Monitor:
   - API call rate (should stay ≤ 50 req/min)
   - 429 error count (should be zero)
   - Batch completion time (acceptable delay)
   - Rate limit wait metrics

**Success**: Zero 429 errors, smooth request pacing visible in logs

---

## Rollout Plan

### Development Testing

1. Deploy to dev environment with DEBUG logging
2. Run 10-comparison batch → verify delays logged
3. Run 100-comparison batch → measure completion time
4. Verify Prometheus metrics populated

### Staging Validation

1. Configure production-like rate limits
2. Simulate production traffic patterns
3. Monitor for 24 hours
4. Verify no 429 errors, acceptable latency

### Production Deployment

1. **Pre-deployment**:
   - Document current 429 error rate
   - Set alerts for rate limit metric anomalies

2. **Deployment**:
   - Deploy during low-traffic window
   - Monitor 429 error rate (should decrease)
   - Monitor batch completion times (may increase slightly)

3. **Post-deployment**:
   - Monitor for 1 week
   - Tune rate limits if needed
   - Document optimal configuration

---

## Risks & Mitigations

### Risk 1: Increased Batch Completion Time

**Description**: Rate limiting adds delays, may increase total batch processing time

**Mitigation**:
- Use realistic rate limits (don't over-throttle)
- PR4 adds only 100ms baseline delay (minimal impact)
- Token bucket allows bursts up to full capacity
- Monitor completion time metrics

**Acceptable Impact**: +10-20% batch completion time under high load (100+ comparisons)

### Risk 2: Configuration Mistakes

**Description**: Incorrect rate limits could cause excessive delays or 429 errors

**Mitigation**:
- PR5 validates configuration on startup
- Sensible defaults (Anthropic tier 1 limits)
- Documentation with examples
- Staging testing before production

### Risk 3: Token Estimation Inaccuracy

**Description**: Prompt token count estimation (`len(prompt) // 4`) may be inaccurate

**Mitigation**:
- Conservative estimate (over-estimate slightly)
- Monitor token usage via rate limit headers (PR2)
- Adjust estimation formula if needed based on real data
- Anthropic SDK may provide tokenization utility (investigate)

### Risk 4: Backward Compatibility

**Description**: New rate limiting behavior may affect existing workloads

**Mitigation**:
- Defaults preserve current behavior (low limits, minimal delay)
- Gradual rollout (dev → staging → production)
- Feature flags if needed (can disable rate limiter)
- Comprehensive testing before production

---

## Documentation Updates

### Files to Update

1. **`services/llm_provider_service/README.md`**
   - Add "Rate Limiting" section
   - Explain token bucket algorithm
   - Document configuration options
   - Provide troubleshooting guide

2. **`.env.example`**
   - Add all new environment variables with comments
   - Provide tier-based examples (tier 1, tier 2, etc.)

3. **`services/cj_assessment_service/README.md`**
   - Document `MAX_CONCURRENT_LLM_REQUESTS` setting
   - Explain interaction with LPS rate limits

4. **`.agent/rules/`** (if applicable)
   - Update architectural documentation
   - Document rate limiting patterns

### Example Documentation Section

```markdown
## Rate Limiting

The LLM Provider Service implements token bucket rate limiting to prevent exceeding API provider quotas.

### Configuration

**Anthropic (Tier 1 Defaults)**:
```env
ANTHROPIC_RATE_LIMIT_REQUESTS_PER_MINUTE=50
ANTHROPIC_RATE_LIMIT_TOKENS_PER_MINUTE=40000
QUEUE_MIN_DELAY_BETWEEN_REQUESTS_MS=100
```

**Anthropic (Tier 2 Example)**:
```env
ANTHROPIC_RATE_LIMIT_REQUESTS_PER_MINUTE=100
ANTHROPIC_RATE_LIMIT_TOKENS_PER_MINUTE=80000
QUEUE_MIN_DELAY_BETWEEN_REQUESTS_MS=50
```

### How It Works

1. **Token Bucket Algorithm**: Maintains two buckets (requests/min and tokens/min)
2. **Automatic Refill**: Tokens replenish at configured rate (e.g., 50/60 = 0.833 req/sec)
3. **Pre-Request Wait**: `acquire()` waits until sufficient tokens available
4. **Dual Limiting**: Enforces BOTH request count AND token usage limits

### Monitoring

**Prometheus Metrics**:
- `llm_provider_rate_limit_waits_total{provider="anthropic"}` - Delay count
- `llm_provider_rate_limit_wait_duration_seconds` - Wait time histogram
- `llm_provider_429_errors_total{provider="anthropic"}` - Rate limit errors

**Expected Behavior**:
- Normal load: Few/zero rate limit waits
- High load: Increased wait duration, smooth request pacing
- Correct config: Zero 429 errors

### Troubleshooting

**Symptom**: Increased batch completion time
- **Cause**: Rate limiting adding delays
- **Solution**: Check if load exceeds configured limits, consider upgrading provider tier

**Symptom**: Still seeing 429 errors
- **Cause**: Rate limits set too high or token estimation inaccurate
- **Solution**: Lower `RATE_LIMIT_*` values, check rate limit headers in logs

**Symptom**: "Rate limit config exceeds tier limit" warning
- **Cause**: Configured limits higher than provider tier
- **Solution**: Reduce limits or upgrade provider tier
```

---

## References

- **Investigation Report**: Session transcript 2025-11-21 (research-diagnostic agent)
- **Code Evidence**: All file:line references in investigation report
- **Anthropic Documentation**: https://docs.anthropic.com/claude/reference/rate-limits
- **Token Bucket Algorithm**: https://en.wikipedia.org/wiki/Token_bucket

---

## Next Steps

### Immediate (Ready for Implementation)

1. ✅ **Architectural Review Complete** - All findings documented above
2. ✅ **Pre-Implementation Research Complete** - Tokenization and serial bundle analysis done
3. 🎯 **Begin PR1 Implementation** - Token Bucket Rate Limiter (P0 priority)
4. 🎯 **Begin PR4 Implementation** - Inter-Request Delay (P1 priority)

### Week 1: Foundation (PR1 + PR4)

- Implement `RateLimiterProtocol` and `TokenBucketRateLimiter`
- Integrate with `anthropic_provider_impl.py` via Dishka DI
- Add inter-request delay in `queue_processor_impl.py`
- Write comprehensive unit tests (~190 LoC)
- Run quality gates: typecheck, format, lint, tests

### Week 2: Observability & Flexibility (PR2 + PR3)

- Extract and log Anthropic rate limit headers
- Validate token estimation accuracy with real data
- Make CJ semaphore configurable
- Document configuration in README

### Week 2-3: Safety & Rollout (PR5 + Deployment)

- Add Pydantic field validation for rate limits
- Create Grafana dashboard for rate limiting metrics
- 24-hour staging soak test
- Production deployment with 1-week monitoring

---

**Task Created**: 2025-11-21
**Architectural Review**: 2025-11-22 ✅ APPROVED
**Status**: Approved - Ready for Implementation
**Priority**: P1 (High - Production Risk Under Load)
**Estimated Effort**: 2-3 weeks (1 developer, includes testing and deployment)

**Next Session**: Begin PR1 implementation of Token Bucket Rate Limiter
