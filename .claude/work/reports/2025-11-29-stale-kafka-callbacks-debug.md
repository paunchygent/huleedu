# Bug Report: ENG5-NP Runner ValueError from Stale Kafka Callbacks

**Date:** 2025-11-29
**Status:** RESOLVED
**Affected Components:** ENG5-NP Runner, CJ Assessment Service, LLM Provider Service

## Summary

ENG5-NP runner failed with `ValueError: Comparison callback missing essay identifiers` caused by stale orphaned Kafka callbacks from prior test runs containing incomplete metadata.

## Symptoms

```
ValueError: Comparison callback missing essay identifiers; correlation=7fd9e895-94e3-480b-b06d-906f6167c2fb
```

The runner's `hydrator.py:_build_comparison_record()` validation at line 211-215 correctly rejected callbacks missing `essay_a_id`/`essay_b_id`.

## Root Cause Analysis

1. **Stale Kafka Events:** Test runs from Nov 28 left orphaned `LLMComparisonResultV1` callbacks in `huleedu.llm_provider.comparison_result.v1` topic.

2. **Incomplete Metadata:** These stale callbacks contained only:
   - `resolved_provider`
   - `queue_processing_mode`
   - `prompt_sha256`

   Missing:
   - `essay_a_id`
   - `essay_b_id`
   - `bos_batch_id`

3. **Consumer Offset Issue:** After deleting and recreating Kafka topics to clear stale events, CJ Assessment Service's consumer group (`cj_assessment_consumer_group`) pointed to invalid offsets. This caused CJ to silently fail to receive new callbacks—database showed `completed_comparisons=0` even though LLM completed and runner received callbacks directly.

## Resolution

1. Deleted and recreated Kafka topics:
   - `huleedu.llm_provider.comparison_result.v1`
   - `huleedu.cj_assessment.completed.v1`
   - `huleedu.assessment.result.published.v1`

2. Restarted all services to reset consumer group connections:
   ```bash
   pdm run dev-restart cj_assessment_service llm_provider_service
   ```

## Verification

Fresh test with `--max-comparisons 2` completed successfully in ~16 seconds:

```
event_counts={'llm_comparisons': 2, 'assessment_results': 1, 'completions': 1}
runner_status: {partial_data: false, timeout_seconds: 0.0}
```

## Lessons Learned

1. **Kafka Topic Recreation Requires Service Restart:** Consumer groups maintain offsets that become invalid when topics are deleted/recreated. Services must be restarted to re-establish valid consumer connections.

2. **Batch ID Filtering Works:** The runner correctly skipped old batch events via `bos_batch_id` metadata filtering—the issue was only with callbacks that predated proper metadata population.

3. **Metadata Validation is Essential:** The `hydrator.py` validation correctly caught malformed callbacks rather than silently producing corrupt artefacts.

## Prevention

- Development environments should periodically clear Kafka topics + restart services as a unit operation
- Consider adding a health check that validates consumer group offset validity
- Document the topic recreation → service restart sequence in operations runbook
