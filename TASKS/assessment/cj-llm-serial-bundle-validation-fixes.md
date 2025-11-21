---
id: cj-llm-serial-bundle-validation-fixes
title: Cj Llm Serial Bundle Validation Fixes
type: task
status: in_progress
priority: high
domain: assessment
owner_team: agents
created: '2025-11-19'
last_updated: '2025-11-21'
service: cj_assessment_service
owner: ''
program: ''
related: []
labels: []
---

# TASK-CJ-LLM-SERIAL-BUNDLE-VALIDATION-FIXES – CJ Batch State, Fairness & Provider Diagnostics

**Scope:**  
- Correctness and observability issues discovered during ENG5 serial-bundle validation runs.  
- Services: **CJ Assessment Service** (batch state, pair generation, callbacks) and **LLM Provider Service** (queue hygiene, provider diagnostics).

**Background:**  
- `per_request` baseline: 4/4 comparisons, stable BT + projections.  
- `serial_bundle` batch 33: 100 pairs → 66 Anthropic errors, degenerate BT scores, completion logs >100%.  
- `serial_bundle` batch 34: 10/10 success, but one stray callback correlation ID and evidence of orphan callbacks / stuck queue items.

**Problem Areas (from investigation docs):**  
1. Batch completion semantics and metrics divergence from DB reality.  
2. Pair generation position bias (anchors overrepresented as `essay_a`).  
3. Poorly classified Anthropic provider errors during serial_bundle runs (rate limits vs server errors vs overload).  
4. Queue hygiene issues: stuck `PROCESSING` items and orphan callbacks.

**This task decomposes the above into PRs:**  
- **PR 1 – CJ Batch Completion & Metrics Semantics Fix**  
- **PR 2 – Pair Generation Fairness & Anchor Position Balancing**  
- **PR 3 – Anthropic Error Diagnostics for Serial-Bundle ENG5 Runs**  
- **PR 4 – Queue Hygiene & Orphan Callback Handling**

**Success Criteria:**
- Serial-bundle runs never report >100% completion and match DB counts.
- A/B positions are balanced for anchors and students across runs.
- Anthropic failures are classified with structured `ErrorDetail` + Prometheus metrics by `error_type`.
- Stuck queue items and orphan callbacks are surfaced via metrics/logs and cleaned up deterministically.

**Progress 2025-11-21:**
- PR1: stability-first completion shipped (callback-driven scoring, nC₂ denominator cap, monitor recovery-only). Unit tests added; targeted pytest command below.
- PR3: Anthropic client hardened (429 Retry-After, 529/overloaded retryable, stop_reason=max_tokens, prompt caching hook + metadata). Integration test still to extend for 529/stop_reason cases.
- Docs updated: CJ README (completion path) and LPS README (Anthropic ops/caching). Tests run: `pdm run pytest-root services/cj_assessment_service/tests/unit/test_workflow_continuation.py services/cj_assessment_service/tests/unit/test_completion_threshold.py services/llm_provider_service/tests/integration/test_anthropic_error_diagnostics.py`.

---

## PR 1 – CJ Batch Completion & Metrics Semantics Fix

**Goal:** Make batch completion, partial scoring, and metrics use coherent
counters so completion percentages never exceed 100% and match DB reality.

**Status:** in_progress (stability-first completion landed 2025-11-21)

**Files:**
- `services/cj_assessment_service/models_db.py` (`CJBatchState`)
- `cj_core_logic/callback_state_manager.py`
- `cj_core_logic/batch_completion_checker.py`
- `cj_core_logic/workflow_continuation.py`
- `cj_core_logic/batch_processor.py`

**Checklist (updated 2025-11-21):**
- **[x]** Define clear semantics for `total_comparisons`, `submitted_comparisons`,
  `completed_comparisons`, `failed_comparisons` (global budget vs runtime counts).
- **[x]** Keep `total_comparisons`/`total_budget` immutable per batch; accumulate `submitted_comparisons` per iteration.
- **[x]** Completion gate now uses callbacks_received (completed+failed) with denominator `min(total_budget or total_comparisons, nC2)`; small batches finalize immediately (n=4 → 6 pairs).
- **[x]** Stability-first: when callbacks_received == submitted_comparisons, recompute BT and finalize on stability (`SCORE_STABILITY_THRESHOLD`) or when callbacks hit denominator/budget cap; BatchMonitor stays recovery-only.
- **[±]** Partial scoring trigger still uses legacy 80% heuristic; leave for follow-up if needed (no regression today).
- **[x]** Tests added/updated: workflow continuation, completion denominator small-batch cap.
- **[x]** Validation: `pdm run pytest-root services/cj_assessment_service/tests/unit/test_workflow_continuation.py services/cj_assessment_service/tests/unit/test_completion_threshold.py` + lint/format.

---

## PR 2 – Pair Generation Fairness & Anchor Position Balancing

**Goal:** Remove structural bias where anchors dominate `essay_a` and ensure
balanced A/B positions while preserving reproducibility.

**Status:** todo

**Files:**
- `cj_core_logic/pair_generation.py`
- `cj_core_logic/batch_preparation.py`
- `config.py` (optional toggle)

**Checklist:**
- **[ ]** Introduce an optional deterministic shuffle of `essays_for_comparison`
  (seeded by `cj_batch_id` and iteration) before generating pairs when
  `ENABLE_COMPARISON_POSITION_BALANCING` is true.
- **[ ]** At pair creation time, randomly (but deterministically) decide whether
  to swap A/B for each pair so that frequent essays appear in both positions.
- **[ ]** Preserve duplicate-prevention by continuing to normalise pair keys via
  sorted IDs.
- **[ ]** Ensure anchors still carry `processing_metadata.is_anchor = True` and
  all grade metadata so BT/grade projection logic remains correct.
- **[ ]** Add tests that show anchors and students are no longer stuck in a
  single position when they appear in multiple pairs.
- **[ ]** Add a small diagnostic helper (or extend an existing script) to print
  per-batch A/B counts per essay and summarise anchor vs student distributions.

---

## PR 3 – Anthropic Error Diagnostics for Serial-Bundle ENG5 Runs

**Goal:** Classify Anthropic errors (rate limit, overload, max_tokens truncation) and surface
them via structured `ErrorDetail` and Prometheus metrics so ENG5 runs can distinguish provider behaviour from CJ bugs.

**Status:** in_progress (retry/overload/stop_reason + prompt caching shipped 2025-11-21)

**Files:**
- `services/llm_provider_service/implementations/anthropic_provider_impl.py`
- `services/llm_provider_service/config.py`
- `services/llm_provider_service/exceptions.py`
- `services/llm_provider_service/metrics.py`

**Checklist (current):**
- **[x]** Treat 529/`overloaded_error` as transient + retryable; metrics label `overloaded`.
- **[x]** Respect `Retry-After` on 429 (bounded sleep) and propagate retryable details.
- **[x]** Detect `stop_reason=max_tokens` and raise structured EXTERNAL_SERVICE_ERROR.
- **[x]** Include `correlation_id` + `prompt_sha256` in Anthropic request metadata; prompt caching hook on system block with configurable TTL.
- **[ ]** Extend `test_anthropic_error_diagnostics.py` to cover 529 / stop_reason flows (currently 429/500/connection).
- **[ ]** Add PromQL snippets to LPS README or ENG5 runbook for error_type visibility.

---

## PR 4 – Queue Hygiene & Orphan Callback Handling

**Goal:** Ensure stuck queue items and orphan callbacks (unknown correlation IDs)
are detectable and do not silently affect ENG5 runs.

**Status:** todo

**Files:**
- `services/llm_provider_service/implementations/queue_processor_impl.py`
- `services/llm_provider_service/queue_models.py`
- `services/llm_provider_service/metrics.py`
- `services/cj_assessment_service/cj_core_logic/callback_state_manager.py`
- `services/cj_assessment_service/message_handlers/llm_callback_handler.py`

**Checklist:**
- **[ ]** Add a configurable timeout for `QueueStatus.PROCESSING`; if a request
  exceeds it, mark as `EXPIRED` or `FAILED` and record metrics.
- **[ ]** Ensure `_periodic_cleanup` (or equivalent) runs this check and logs
  stuck items with CJ metadata when present (e.g. `cj_batch_id`).
- **[ ]** In `update_comparison_result`, when no `ComparisonPair` is found for a
  callback correlation ID, record a CJ metric
  `cj_orphan_callbacks_total{source_service}` and log structured details rather
  than only raising.
- **[ ]** Add unit tests for both stuck-queue cleanup and orphan callbacks.

---

## Summary & Validation Plan

- **[ ]** After PRs 1–4, re-run ENG5 `per_request` and `serial_bundle` executes
  with identical configuration and compare:
  - Error rates by provider/error_type.
  - A/B position distributions by anchor vs student.
  - CJ batch completion logs vs true DB counts.
- **[ ]** Update this task status and related TASK docs once validation is
  complete.
