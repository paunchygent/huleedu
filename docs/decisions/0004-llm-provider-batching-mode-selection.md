---
type: decision
id: ADR-0004
status: proposed
created: 2025-11-27
last_updated: 2025-11-27
---

# ADR-0004: LLM Provider Batching Mode Selection

## Status
Proposed

## Context
The LLM Provider Service currently makes individual API calls to Anthropic/OpenAI for each comparison task in Comparative Judgment (CJ) assessments. This approach faces challenges:

1. **Rate Limiting Pressure**: Individual requests quickly hit provider rate limits during batch processing
2. **Cost Inefficiency**: Each HTTP round-trip adds overhead; batching could reduce costs
3. **Latency Tradeoffs**: Synchronous per-round processing offers fast feedback but limited throughput
4. **Provider Capabilities**: Both Anthropic and OpenAI now support batch APIs with significant cost reductions (50% for Anthropic Message Batches, similar for OpenAI)

Current state:
- Per-comparison synchronous API calls via `LLMProviderService`
- Rate limit errors force manual retry logic
- No batching or request aggregation
- Comparison results returned immediately via Kafka events

The platform needs to support multiple batching strategies to balance latency, cost, and reliability based on assessment context (classroom quick-check vs district-wide summative).

## Decision
Implement **configurable batching strategies** with three modes:

### 1. Per-Round Batching (Default)
- **Behavior**: Aggregate all comparison tasks from a single `perform_comparisons` call and submit together
- **Use Case**: Classroom assessments where teachers expect results within minutes
- **Implementation**: Bundle prompts into single API call (multi-message format for Claude, batch-within-request for OpenAI)
- **Latency**: ~1-5 minutes depending on comparison count
- **Cost**: Standard API pricing

### 2. Serial Bundling (Experimental)
- **Behavior**: Pack multiple comparison prompts into sequential entries in one API call
- **Use Case**: Reduce HTTP overhead while maintaining synchronous flow
- **Implementation**: Send multiple `messages` in a single Claude call or multiple prompts in OpenAI completion
- **Latency**: ~1-3 minutes (reduced connection overhead)
- **Cost**: Standard API pricing but fewer HTTP operations

### 3. Nightly Batch Jobs (NOT IMPLEMENTED - Future Consideration)
- **Behavior**: Accumulate comparison tasks throughout the day and submit via provider batch APIs overnight
- **Use Case**: District-wide summative assessments where 24-hour turnaround is acceptable
- **Implementation**: Queue tasks in database, submit JSONL batch at configured time, poll for completion
- **Latency**: 12-24 hours
- **Cost**: 50% reduction via Anthropic Message Batches API / OpenAI Batch API
- **Status**: Not implemented. Consider if demand for cost savings outweighs latency requirements.

### Configuration
Add `llm_batching_strategy` to CJ Assessment Service settings:

```python
class CJAssessmentSettings:
    llm_batching_strategy: Literal["per_round", "serial_bundle", "nightly_batch"] = "per_round"
    batch_submission_hour: int = 2  # For nightly_batch mode (UTC)
    batch_max_wait_hours: int = 24  # For nightly_batch mode
```

### Implementation Phases
1. **Phase 1** (Immediate): Implement serial bundling prototype to measure rate limit relief
2. **Phase 2** (Next sprint): Add per-round batching with proper aggregation
3. **Phase 3** (Future): Implement nightly batch jobs with provider batch APIs

## Consequences

### Positive
- **Flexibility**: Different assessment contexts can use appropriate latency/cost tradeoffs
- **Cost Reduction Path**: Clear migration to 50% cheaper batch APIs when latency tolerance exists
- **Rate Limit Relief**: Bundling reduces API call frequency significantly
- **Operational Visibility**: Metrics track batch progress and completion rates
- **Backward Compatible**: Default per-round mode maintains current synchronous behavior

### Negative
- **Complexity**: Three strategies to implement, test, and maintain
- **Callback Mapping**: Nightly batches require custom_id tracking to map results back to essay pairs
- **Monitoring Overhead**: Need separate health checks for batch job status and queue depths
- **Provider API Changes**: Batch APIs have different error handling and retry semantics
- **Testing Burden**: Each strategy requires distinct integration and contract tests

## Alternatives Considered

1. **Always Use Batch APIs**: Force all assessments through nightly batch processing
   - Rejected: Unacceptable latency for classroom use cases where teachers need immediate feedback
   - Would save 50% on LLM costs but destroy user experience

2. **Only Serial Bundling**: Stick with synchronous requests but bundle multiple comparisons
   - Rejected: Doesn't unlock batch API cost savings for tolerance-compatible assessments
   - Misses opportunity to serve both real-time and batch use cases

3. **External Queue Service** (e.g., Celery, AWS SQS): Use separate queue infrastructure for batch management
   - Rejected: Adds operational complexity; current Kafka + PostgreSQL sufficient for queueing
   - Would introduce new infrastructure dependency without clear benefit

4. **Smart Adaptive Batching**: Automatically detect assessment urgency and choose strategy
   - Deferred: Requires user intent modeling; start with explicit configuration first
   - Could be future enhancement once usage patterns are understood

## CJ / LLM Provider Batching Interplay (Short Summary)

- **CJ-side modes**: CJ Assessment exposes `LLMBatchingMode` (`per_request`, `serial_bundle`, `provider_batch_api`) and persists the effective mode in batch metadata.
- **LPS queue modes**: LLM Provider Service uses `QUEUE_PROCESSING_MODE` (`per_request`, `serial_bundle`, `batch_api`) plus `cj_llm_batching_mode` hints from `LLMComparisonRequest.metadata` to decide how many queued items are grouped into a single provider call.
- **Mapping**:
  - `LLMBatchingMode.SERIAL_BUNDLE` → `QUEUE_PROCESSING_MODE=serial_bundle`: CJ sends comparisons in waves; LPS groups compatible requests into `process_comparison_batch` calls while still emitting one callback per comparison.
  - `LLMBatchingMode.PROVIDER_BATCH_API` → `QUEUE_PROCESSING_MODE=batch_api` (once native batch endpoints are implemented): CJ generates all comparisons up to the cap in a single wave; LPS uses provider batch APIs to execute the work, but the callback contract (`LLMComparisonResultV1`) remains unchanged.
- **Contract stability**: All modes use the same 202+callback pattern; batching changes only how many comparison requests are coalesced into a single provider call, not the HTTP or Kafka contracts seen by upstream services.

## Related ADRs
- ADR-0006: Pipeline Completion State Management (batch processing coordination)

## References
- TASKS/integrations/llm-batch-strategy-serial-bundle.md
- .claude/rules/042-async-patterns-and-di.md (async processing patterns)
- Services: services/llm_provider_service/, services/cj_assessment_service/
- Anthropic Message Batches API: <https://docs.anthropic.com/en/docs/build-with-claude/message-batches>
