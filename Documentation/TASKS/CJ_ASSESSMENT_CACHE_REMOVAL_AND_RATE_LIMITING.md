## 🎯 CJ Assessment Cache Removal and Provider Rate Limiting Implementation

You are implementing critical improvements to the CJ Assessment Service and LLM Provider Service based on production issues discovered with Anthropic rate limiting (429 errors) during functional testing.

## Current State Summary

### 🚨 Problems Identified

1. **Improper Caching Implementation in CJ Assessment**:
   - Uses prompt-based caching (`diskcache`) that stores LLM responses based on prompt hash
   - Cache key: `SHA256(prompt + model + temperature + max_tokens)`
   - This is NOT proper idempotency - it's "lazy thinking" that bypasses request-based handling
   - Causes stale responses and breaks proper request flow
   - Validation errors show cached data with old confidence scale (0-1 vs expected 1-5)

2. **Rate Limiting Issues**:
   - Test with 4 essays generates 5 comparison requests sent **simultaneously**
   - Causes burst traffic that exceeds Anthropic's per-second limits (even within per-minute limits)
   - Results in 429 "Too Many Requests" errors and test failures
   - No provider-specific rate limiting implemented

3. **Lack of Dynamic Rate Limit Discovery**:
   - No API endpoints from providers to query account tier/limits
   - Rate limits only available via response headers AFTER making requests
   - Need to implement intelligent rate limiting based on known tier limits

## Decisions Made

### ✅ Remove Prompt-Based Caching
The prompt-based cache in CJ Assessment Service must be completely removed because:
- It's not proper idempotency (should be request/correlation ID based)
- The LLM Provider Service already has proper request queuing with Redis
- It causes validation errors and stale responses
- Proper idempotency belongs at the request level, not prompt level

### ✅ Implement Provider-Specific Rate Limiting
Based on research and tier 1 limits:
- **Anthropic**: ~50-60 RPM → 1.44 seconds between requests (with 20% safety margin)
- **OpenAI**: ~500 RPM → 0.144 seconds between requests (with 20% safety margin)
- **Google/OpenRouter**: Similar to OpenAI
- Implement delays at the LLM Provider Service level (not CJ Assessment)

### ✅ Use Response Headers for Dynamic Limits
**Important: There are NO dedicated API endpoints to query rate limits from providers!**

Based on our research:
- **OpenAI**: No API to get tier/limits - only available in response headers after making requests
- **Anthropic**: No API to get tier/limits - only available in response headers after making requests
- Both providers return rate limit info in headers, but you must "burn" a request to get them

**Response Headers Available**:
- OpenAI: `x-ratelimit-limit-requests`, `x-ratelimit-remaining-requests`, etc.
- Anthropic: `anthropic-ratelimit-requests-remaining`, reset timestamps, etc.

**Implementation Strategy**:
- Start with conservative tier 1 estimates (50 RPM for Anthropic, 500 RPM for OpenAI)
- Parse rate limit headers from EVERY response
- Dynamically adjust delays based on actual limits discovered
- Honor `retry-after` headers on 429 responses
- Store discovered limits per provider for future requests

## Files to Modify

### CJ Assessment Service - Cache Removal

**Files to Remove/Clean:**
1. `/services/cj_assessment_service/implementations/cache_manager_impl.py` - **DELETE**
2. `/services/cj_assessment_service/protocols.py` - Remove `CacheProtocol` interface
3. `/services/cj_assessment_service/di.py` - Remove cache manager provider and injection
4. `/services/cj_assessment_service/implementations/llm_interaction_impl.py` - Remove all cache logic
5. `/services/cj_assessment_service/pyproject.toml` - Remove `diskcache` and `cachetools` dependencies
6. `/services/cj_assessment_service/metrics.py` - Remove cache operation metrics

**Test Files to Update/Remove:**
7. `/services/cj_assessment_service/tests/test_llm_interaction_overrides.py` - Remove cache mocks
8. Other test files with `mock_cache_manager` references

**Optional Cleanup:**
9. Remove any `cache` directories created by diskcache

### LLM Provider Service - Rate Limiting Implementation

**Files to Create/Modify:**
1. `/services/llm_provider_service/config.py` - Add provider rate limit configuration
2. `/services/llm_provider_service/implementations/rate_limiter.py` - **NEW** Rate limiting logic
3. Provider implementations - Add rate limiting before API calls:
   - `/services/llm_provider_service/implementations/anthropic_provider_impl.py`
   - `/services/llm_provider_service/implementations/openai_provider_impl.py`
   - `/services/llm_provider_service/implementations/google_provider_impl.py`
   - `/services/llm_provider_service/implementations/openrouter_provider_impl.py`
4. `/services/llm_provider_service/implementations/llm_orchestrator_impl.py` - Integrate rate limiter

## Implementation Plan

### Phase 1: Remove Cache from CJ Assessment Service ✅

1. **Delete cache implementation files**
2. **Remove `CacheProtocol` from protocols.py**
3. **Update `llm_interaction_impl.py`**:
   - Remove cache_manager from constructor
   - Remove all cache checking/storing logic
   - Keep the core comparison logic intact
4. **Update DI configuration**:
   - Remove cache manager provider
   - Update LLMInteractionImpl provider to not inject cache
5. **Fix all tests** that reference cache
6. **Remove dependencies** from pyproject.toml

### Phase 2: Implement Rate Limiting in LLM Provider Service 🚀

1. **Create Rate Limiter Configuration**:
   ```python
   PROVIDER_RATE_LIMITS = {
       LLMProviderType.ANTHROPIC: {
           "tier_1_rpm": 50,
           "request_delay_seconds": 1.44  # 60/50 * 1.2 (20% margin)
       },
       LLMProviderType.OPENAI: {
           "tier_1_rpm": 500,
           "request_delay_seconds": 0.144  # 60/500 * 1.2 (20% margin)
       },
       # ... other providers
   }
   ```

2. **Create Rate Limiter Implementation**:
   - Track last request timestamp per provider
   - Calculate required delay before next request
   - Sleep if needed to maintain rate limit
   - Parse response headers to update limits dynamically
   - **Cannot pre-fetch limits** - must discover from actual API responses
   - Store discovered limits and adjust delays accordingly

3. **Integrate into Provider Implementations**:
   - Add rate limiting before each API call
   - Handle 429 responses with retry-after header
   - Update rate limits based on response headers

4. **Add Observability**:
   - Log rate limit delays
   - Track rate limit headers
   - Monitor 429 errors

### Phase 3: Testing and Validation ✅

1. **Test cache removal**:
   - Ensure no cache references remain
   - Verify comparisons still work without cache
   - Check all tests pass

2. **Test rate limiting**:
   - Verify delays are applied correctly
   - Test 429 error handling
   - Confirm headers are parsed properly

3. **Run functional tests**:
   - The 4-essay test should now pass without 429 errors
   - Comparisons should complete successfully with delays

## Success Criteria

1. **Cache Completely Removed**:
   - No `diskcache` usage in CJ Assessment
   - All tests pass without cache
   - Clean code with no cache artifacts

2. **Rate Limiting Working**:
   - No 429 errors during normal operation
   - Proper delays between provider requests
   - Dynamic adjustment based on headers

3. **Tests Pass**:
   - Functional tests complete without rate limit errors
   - Unit tests updated and passing
   - No performance regression beyond expected delays

## Commands to Run

```bash
# After cache removal
pdm run pytest services/cj_assessment_service/tests/ -v
pdm run ruff check services/cj_assessment_service/

# After rate limiting implementation  
pdm run pytest services/llm_provider_service/tests/ -v
pdm run pytest tests/functional/test_e2e_cj_assessment_workflows.py -v

# Verify no cache artifacts
find services/cj_assessment_service -name "*cache*" -type f
find services/cj_assessment_service -name "*cache*" -type d
```

## Important Context

### Why This Matters
- The prompt-based cache violates proper architectural patterns
- Rate limiting prevents service disruption and unexpected costs
- This enables reliable production operation with LLM providers

### Dynamic Rate Limit Discovery Limitations
- **No API endpoints exist** to query account tier or rate limits before making requests
- Providers only expose limits via response headers AFTER you make API calls
- Must implement adaptive rate limiting that starts conservative and adjusts based on actual responses
- This is a limitation of all major LLM providers (OpenAI, Anthropic, etc.)

### Related Systems
- Redis queue in LLM Provider Service handles proper request management
- The removed cache should NOT be replaced with another cache
- Rate limiting must be provider-aware and configurable

### References
- Original conversation about cache discovery and rate limits
- Anthropic/OpenAI documentation on rate limits and headers
- Existing Redis queue implementation for proper request handling

## Questions Before Starting

1. Should we implement rate limiting for mock provider too (for testing)?
2. Do you want rate limit configuration in environment variables or hardcoded?
3. Should we add metrics for rate limit delays and 429 errors?
4. Do you want a migration script to clean up existing cache directories?

---

**Priority**: HIGH - This fixes production issues with 429 errors and removes improper caching
**Estimated Time**: 4-6 hours (2-3 hours per phase)
**Risk**: Medium - Removing cache might reveal other issues, but Redis queue should handle properly