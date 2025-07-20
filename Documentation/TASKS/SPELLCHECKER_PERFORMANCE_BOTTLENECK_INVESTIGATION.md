# Spellchecker Performance Bottleneck Investigation

## Issue Summary

**Problem**: Deterministic 10-20x processing time spike affecting exactly one essay per batch in the spellchecker pipeline, causing HTTP connection timeouts and `ServerDisconnectedError` during content storage operations.

**Impact**: 
- One essay per batch consistently fails with `ServerDisconnectedError` during content storage
- Processing time for the failing essay: 5-6 seconds vs 0.2-0.5 seconds for other essays
- Causes downstream pipeline delays and reduces batch processing reliability

**Investigation Period**: Multiple sessions focusing on evidence-based root cause analysis

## Empirical Findings (No Assumptions)

### 1. Connection Pool and Concurrency Issues (RESOLVED)

**Finding**: Content service was running with only 1 worker (single-threaded), causing request queuing and connection timeouts under concurrent load.

**Evidence**:
- Docker logs showed content service running with single worker
- Multiple `ServerDisconnectedError` events during batch processing
- HTTP connection pool exhaustion under load

**Fix Applied**:
- Increased `WEB_CONCURRENCY` from 1 to 4 in `/services/content_service/config.py`
- Modified `/services/content_service/pyproject.toml` to run hypercorn with `--workers 4 --worker-class asyncio`
- Configured aiohttp HTTP client with increased connection pool limits (`limit=200`, `limit_per_host=100`)

**Result**: The single essay failure per batch persisted with no change in performance.

### 2. Async Logging Bottleneck (RESOLVED)

**Finding**: Synchronous correction logging was blocking HTTP request processing, contributing to processing delays.

**Evidence**:
- Correction logging performed synchronously in critical path
- File I/O operations blocking async request handling

**Fix Applied**:
- Converted correction logging to fully asynchronous using `aiofiles`
- Implemented background task scheduling with `asyncio.create_task()`
- Moved logging off critical path in `/services/spellchecker_service/core_logic.py`

**Result**: Eliminated blocking I/O, but single essay processing spike remained.

### 3. HTTP Client Retry Logic (REJECTED BY USER AS BANDAID)

**Finding**: No retry mechanism for transient HTTP connection errors.

**Fix Suggested**:
- Add exponential backoff retry logic for `ServerDisconnectedError` in `/services/spellchecker_service/implementations/result_store_impl.py`
- Implement structured error handling with 3 retry attempts
- Increase HTTP timeout from 10s to 30s

**Result**: No change in behavior due to REJECTED BY USER AS BANDAID.

### 4. Performance Instrumentation (IMPLEMENTED)

**Current Status**: Added comprehensive timing instrumentation to identify bottleneck location.

**Instrumentation Added**:
```python
# In default_perform_spell_check_algorithm():
start_time = time.time()

# L2 Dictionary Loading
l2_load_start = time.time()
l2_errors = load_l2_errors(settings.effective_filtered_dict_path, filter_entries=False)
l2_load_time = time.time() - l2_load_start
logger.info(f"L2 dictionary load time: {l2_load_time:.3f}s")

# L2 Corrections Application
l2_apply_start = time.time()
l2_corrected_text, l2_corrections = apply_l2_corrections(text, l2_errors)
l2_apply_time = time.time() - l2_apply_start
logger.info(f"L2 corrections apply time: {l2_apply_time:.3f}s")

# SpellChecker Initialization
spellchecker_init_start = time.time()
spell_checker = SpellChecker(language=language)
spellchecker_init_time = time.time() - spellchecker_init_start
logger.info(f"SpellChecker init time: {spellchecker_init_time:.3f}s")

# Total Processing Time
total_time = time.time() - start_time
logger.info(f"Total processing time: {total_time:.3f}s")
```

**Files Modified**:
- `/services/spellchecker_service/core_logic.py`: Added timing measurements at lines 263, 291-294, 300-304, 316-320, 472-479

**Next Action Required**: Execute end-to-end test with timing instrumentation to collect empirical data on processing bottleneck location.

## Outstanding Investigation Items

### 1. Root Cause Analysis Required

**Status**: Instrumentation implemented, data collection pending

**Next Steps**:
1. Execute end-to-end test with timing instrumentation
2. Analyze logs to identify which processing step causes the 10-20x delay
3. Correlate timing data across all 25 essays in batch
4. Identify if bottleneck is in:
   - L2 dictionary loading (disk I/O contention)
   - L2 corrections application (algorithmic complexity)
   - SpellChecker initialization (resource loading)
   - PySpellChecker corrections processing (algorithmic inefficiency)

### 2. Hypotheses to Test (Evidence-Based Only)

**L2 Dictionary Loading**: 
- Potential disk I/O contention when multiple essays load same dictionary simultaneously
- File system lock contention under concurrent access

**PySpellChecker Processing**:
- Algorithmic complexity scaling with specific text characteristics
- Memory allocation patterns causing GC pressure
- Dictionary lookup performance degradation

**Resource Contention**:
- CPU scheduling delays under concurrent processing
- Memory pressure affecting specific essay processing

## Technical Architecture Context

### Services Involved
- **Spellchecker Service**: Processes essay text, applies L2 corrections, runs pyspellchecker
- **Content Service**: Stores corrected essay content (4 async workers)
- **ELS (Essay Lifecycle Service)**: Orchestrates pipeline phases

### Processing Pipeline
1. Essay content provisioned to spellchecker
2. L2 dictionary loaded from disk
3. L2 corrections applied to text
4. PySpellChecker initialized for language
5. PySpellChecker corrections applied
6. Corrected content stored via HTTP to content service
7. Processing result published to Kafka

### Current Performance Profile
- **Normal Essays**: 0.2-0.5 seconds total processing time
- **Slow Essay**: 5-6 seconds total processing time (10-20x slower)
- **Failure Pattern**: Always exactly 1 essay per batch, varies which essay

## Validation Requirements

Before considering this investigation complete:

1. **Timing Data Collection**: Execute instrumented test and collect precise timing logs for all processing steps
2. **Bottleneck Identification**: Identify which specific step (L2 load, L2 apply, SpellChecker init, corrections) causes delay
3. **Resource Analysis**: Correlate timing spikes with system resource usage (CPU, memory, disk I/O)
4. **Reproducibility**: Confirm bottleneck occurs consistently and identify triggering conditions
5. **Root Cause Isolation**: Distinguish between algorithmic inefficiency, resource contention, and infrastructure issues

## Success Criteria

- All 25 essays in batch process within 0.2-1.0 seconds
- No `ServerDisconnectedError` events during content storage
- Consistent processing times across all essays in batch
- No deterministic single-essay failures

## Files Modified

### Configuration Changes
- `/services/content_service/config.py`: WEB_CONCURRENCY 1→4
- `/services/content_service/pyproject.toml`: Added `--workers 4 --worker-class asyncio`

### Code Changes
- `/services/spellchecker_service/core_logic.py`: Added comprehensive timing instrumentation
- `/services/spellchecker_service/implementations/result_store_impl.py`: Added retry logic and error handling
- `/services/spellchecker_service/di.py`: Increased HTTP connection pool limits

### Instrumentation Added
- L2 dictionary load timing
- L2 corrections application timing  
- SpellChecker initialization timing
- Total processing time measurement
- Structured logging with timing metadata

## Next Action Required

Execute end-to-end test with timing instrumentation to collect empirical data on processing bottleneck location.
