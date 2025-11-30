type: runbook
service: cj_assessment_service
severity: high
last_reviewed: 2025-11-30
---

# CJ Assessment & LLM Provider Foundation (Working Reference)

Purpose: single reference for defaults, reasoning, metrics, and open work across CJ Assessment, LLM Provider, ENG5 Runner, and API Gateway callers. Keep this in sync with handoff.md, readme_first.md, and relevant task docs under .claude/work/tasks/.

## User Stories

### US-1: Teacher Views CJ Results with Student Identification
> As a **teacher** viewing CJ assessment results, I want to see the **student name or filename** alongside the CJ rank and score, so I can **identify whose work I'm evaluating**.

**Acceptance**: RAS API returns `filename` (URL-decoded) for each essay in batch results.

### US-2: GUEST Batch Assessment (No Class Association)
> As a **teacher** running an experiment with old essays or essays not associated with any class, I want to **upload essays and run CJ assessment** without needing to create a class or associate students, so I can **quickly evaluate relative quality**.

**Context**: GUEST batches have no `class_id`, no `student_id` linkage. Filename is the **ONLY** way to identify students.

**Acceptance**:
- Batch registration succeeds without `class_id`
- Pipeline executes spellcheck → CJ without student matching phase
- Results display filename-based identification

### US-3: REGULAR Batch Assessment (Class Association)
> As a **teacher** with a class roster, I want to **upload essays for my class** and have the system **match essays to enrolled students**, so results show student names and integrate with gradebook.

**Context**: REGULAR batches have `class_id`, enabling student matching via filename heuristics or manual assignment.

**Acceptance**:
- Essays matched to students via Class Management Service
- Results display student names (not just filenames)
- Grade projections available when anchors configured

### US-4: Optional Spellcheck (Future)
> As a **teacher**, I want to **optionally skip spellcheck** for essays that are already corrected or when I want to assess raw writing quality.

**Context**: Currently spellcheck is mandatory. Future state allows bypass.

**Acceptance** (future):
- Pipeline configuration flag to skip spellcheck phase
- CJ uses `original_text_storage_id` when spellcheck skipped
- CJ uses `spellcheck_corrected_text_storage_id` when spellcheck runs

### Data Flow Requirements

| User Story | Filename Required | student_id Required | text_storage_id Source |
|------------|-------------------|---------------------|------------------------|
| US-1 | ✅ Critical | Optional | Either |
| US-2 (GUEST) | ✅ Critical (only ID) | ❌ N/A | spellcheck_corrected |
| US-3 (REGULAR) | ✅ Until matched | ✅ After matching | spellcheck_corrected |
| US-4 (Future) | ✅ Critical | Optional | original OR corrected |

### Related Tasks
- [Filename Propagation Task](../../TASKS/assessment/filename-propagation-from-els-to-ras-for-teacher-result-visibility.md) - fixes US-1, US-2 filename gap

---

## Default knobs (current proposals) and rationale

| Setting | Initial value | Rationale | Tuning plan |
| --- | --- | --- | --- |
| SCORE_STABILITY_THRESHOLD | 0.05 (current default) | Max allowed BT score change between iterations before we consider a batch “stable enough” to stop requesting more comparisons. | Sweep with ENG5 Runner across 0.025–0.05 per exam; pick per-assignment default and adjust per assignment type if needed. |
| MIN_COMPARISONS_FOR_STABILITY_CHECK | 12 (current default) | Global floor on successful comparisons before stability is evaluated; protects against noisy early BT estimates and is respected by both the production continuation path and the convergence harness. | Tune per exam type; increase for noisier cohorts where more comparisons are needed before BT deltas are informative. |
| completion_denominator | min(total_budget or total_comparisons, nC2(actual_processed_essays)) | Small batches finalize promptly; cap prevents 6-pair batches from waiting on 350-budget. | Keep; verify nC2 source is the set of `ProcessedEssay` rows (students + anchors), not just expected_essay_count. |
| MIN_RESAMPLING_NET_SIZE | 10 | Nets smaller than this are treated as “small nets” for Phase‑2 resampling semantics. | Tune per exam if small nets routinely need more or fewer Phase‑2 passes. |
| MAX_RESAMPLING_PASSES_FOR_SMALL_NET | 2 | Caps resampling passes for small nets once unique coverage is complete. | Adjust cautiously; monitor BT SE diagnostics and coverage metrics before increasing. |
| BatchMonitor timeout_hours | prod: 4h; dev: 1h | Recovery-only safety net; generous for prod, tight for dev. | Remove 80% heuristic; keep timeout-only once validated. |
| PROMPT_CACHE_TTL_SECONDS | ad-hoc/dev: 300–600s; assignment_id/batch: 3600s | Short TTL for rapid iteration; longer for stable, repeated prompts in batch runs. | Raise to 4–6h if cache hit rate is high and safety acceptable. |
| ENABLE_PROMPT_CACHING | true for assignment_id/batch; optional for ad-hoc | Reduce cost on repeated static context; avoid surprises in highly dynamic prompts. | Keep on for curated exams; monitor hits/misses. |
| stop_reason handling | error on max_tokens | Prevent silent truncation. | Keep; add tests for stop_reason and 529. |
| Retry behavior (Anthropic) | 429 respects Retry-After (bounded); 529/5xx retryable | Align with provider guidance. | Monitor error_type metrics and adjust backoff as needed. |

## How completion now works (callback-first, serial bundles)
1) LLM requests are async; callbacks update completed/failed counters and last_activity_at.
2) Continuation triggers only when `callbacks_received == submitted_comparisons` for the current wave.
3) On trigger: recompute BT scores; persist `bt_scores` / `last_score_change`; stop if stability or denominator/budget cap reached; else enqueue the next wave of comparisons (respecting `MAX_PAIRWISE_COMPARISONS`) if budget remains.

### Stability vs caps
- `MAX_PAIRWISE_COMPARISONS` (and any runner `max_comparisons` hint) are treated as **caps**, not obligations. Batches may finalize early when BT scores stabilize under `SCORE_STABILITY_THRESHOLD` once `MIN_COMPARISONS_FOR_STABILITY_CHECK` successful comparisons are available.
- To *intentionally* consume the full cap in a stability‑aware workflow (no early stop), configure `MIN_COMPARISONS_FOR_STABILITY_CHECK` greater than the effective cap (`MAX_PAIRWISE_COMPARISONS` or runner override) so the stability gate never passes; finalization then occurs only when callbacks reach the denominator/cap.
4) Finalization: SCORING -> COMPLETE_STABLE, rankings + projections (only if assignment_id), events out.
5) BatchMonitor: intended recovery-only; remove 80% heuristic after timeout-only path is validated.

## Metrics to instrument/track
- Completion latency: callback_to_finalization p95.
- Stability: stability_iterations_per_batch; max_score_change at finalization.
- Budget usage: callbacks_received vs completion_denominator; pairs_remaining when finalized.
- Prompt caching: cache_hits, cache_misses, avg_prompt_tokens_saved.
  - Metrics: `llm_provider_prompt_cache_events_total{result}`, `llm_provider_prompt_cache_tokens_total{direction}`, `llm_provider_cache_scope_total{scope,result}`, `llm_provider_prompt_blocks_total{target,cacheable,ttl}`, `llm_provider_prompt_tokens_histogram_bucket{section}`, `llm_provider_prompt_ttl_violations_total{stage}`.
  - PromQL: hit rate (assignment scope) `sum(rate(llm_provider_cache_scope_total{scope="assignment",result="hit"}[5m])) / sum(rate(llm_provider_cache_scope_total{scope="assignment"}[5m]))`; tokens saved per second `sum(rate(llm_provider_prompt_cache_tokens_total{direction="read"}[5m]))`; block mix `sum(rate(llm_provider_prompt_blocks_total[5m])) by (target, cacheable)`; static vs dynamic size `sum(rate(llm_provider_prompt_tokens_histogram_sum[5m])) by (section) / sum(rate(llm_provider_prompt_tokens_histogram_count[5m])) by (section)`; TTL violations `increase(llm_provider_prompt_ttl_violations_total[1h])` (should be zero).
- Provider errors: llm_provider_errors_total{provider,model,error_type}; rate_limit/overloaded alerts; stop_reason occurrences.
- Queue health: processing_timeout_count, orphan_callback_count (pending for PR4).

### BT SE batch quality indicators (diagnostics only)

CJ exposes lightweight batch quality indicators derived from `bt_se_summary`:

- Stored on `CJBatchState.processing_metadata`:
  - `bt_se_summary`: batch-level BT SE diagnostics (mean/max/min SE, item/comparison counts,
    items_at_cap, isolated_items, mean/min/max comparisons per item).
  - `bt_quality_flags`:
    - `bt_se_inflated` – True when mean or max BT SE exceeds diagnostic thresholds
      (`BT_MEAN_SE_WARN_THRESHOLD`, `BT_MAX_SE_WARN_THRESHOLD`).
    - `comparison_coverage_sparse` – True when mean comparisons per essay falls below
      `BT_MIN_MEAN_COMPARISONS_PER_ITEM`.
    - `has_isolated_items` – True when any essays are isolated in the comparison graph.
- Exposed as Prometheus counters (diagnostic only, no gating semantics):
  - `cj_bt_se_inflated_batches_total`
  - `cj_bt_sparse_coverage_batches_total`

Operational usage:
- Treat these as **gauges on the dashboard**, not steering wheels:
  - Rising `cj_bt_se_inflated_batches_total` → investigate anchor coverage / comparison budgets.
  - Rising `cj_bt_sparse_coverage_batches_total` or frequent `has_isolated_items=True` →
    investigate matching/budget configuration for nets with sparse coverage.
- These flags and counters do **not** change:
  - Completion denominator semantics.
  - Stability thresholds (`MIN_COMPARISONS_FOR_STABILITY_CHECK`, `SCORE_STABILITY_THRESHOLD`).
  - Success-rate guard behaviour (`MIN_SUCCESS_RATE_THRESHOLD` and finalize_failure paths).

Grafana panel JSON examples (per environment; assumes an `environment` label on the metric):

```json
{
  "title": "CJ BT SE Inflated Batches (rate by environment)",
  "type": "timeseries",
  "datasource": {
    "type": "prometheus",
    "uid": "PROM_DS_UID"
  },
  "gridPos": { "h": 8, "w": 12, "x": 0, "y": 0 },
  "targets": [
    {
      "refId": "A",
      "expr": "sum by (environment) (rate(cj_bt_se_inflated_batches_total[5m]))",
      "legendFormat": "{{environment}}"
    }
  ],
  "fieldConfig": {
    "defaults": { "unit": "1/s" },
    "overrides": []
  },
  "options": {
    "legend": { "showLegend": true },
    "tooltip": { "mode": "single" }
  }
}
```

For sparse coverage:

```json
{
  "title": "CJ BT Sparse Coverage Batches (rate by environment)",
  "type": "timeseries",
  "datasource": {
    "type": "prometheus",
    "uid": "PROM_DS_UID"
  },
  "gridPos": { "h": 8, "w": 12, "x": 12, "y": 0 },
  "targets": [
    {
      "refId": "A",
      "expr": "sum by (environment) (rate(cj_bt_sparse_coverage_batches_total[5m]))",
      "legendFormat": "{{environment}}"
    }
  ]
}
```

Alert idea (Grafana managed alert, configured via UI rather than raw JSON):
- Query: `sum by (environment) (rate(cj_bt_se_inflated_batches_total[5m]))`
- Condition: last value `> 0.1` for `10m`
- Labels: `service="cj_assessment_service"`, `severity="warning"`

### Workflow continuation decision metrics (diagnostics only)

Continuation outcomes are exposed via a dedicated diagnostic counter:

- Metric: `cj_workflow_decisions_total{decision=...}`
  - Labels:
    - `decision` – one of the internal `ContinuationDecision` enum values:
      - `WAIT_FOR_CALLBACKS`
      - `FINALIZE_SCORING`
      - `FINALIZE_FAILURE`
      - `REQUEST_MORE_COMPARISONS`
      - `NO_OP`
  - Emission path:
    - Derived from `ContinuationContext` + final `ContinuationDecision` in
      `workflow_continuation.trigger_existing_workflow_continuation`.
    - Implemented via the `workflow_diagnostics.record_workflow_decision(...)`
      helper to keep continuation logic pure and side-effect-free.
  - Structured logs:
    - The `Continuation decision evaluated` log line uses the same decision
      vocabulary (`decision=<enum value>`) and includes the key continuation
      fields (`callbacks_received`, `denominator`, `max_score_change`,
      `success_rate`, `success_rate_threshold`, `callbacks_reached_cap`,
      `budget_exhausted`, `is_small_net`, `small_net_cap_reached`,
      BT SE/coverage flags) so logs and metrics can be correlated.

Operational usage:
- Use this metric to track the mix of continuation outcomes over time and
  confirm that convergence and failure patterns match expectations:
  - High `FINALIZE_SCORING` vs `FINALIZE_FAILURE` ratios in healthy runs.
  - `REQUEST_MORE_COMPARISONS` reflecting stability-first behaviour under
    `MIN_COMPARISONS_FOR_STABILITY_CHECK` / `SCORE_STABILITY_THRESHOLD`.
- Example dashboard panel (decision mix over time):

```json
{
  "title": "CJ Workflow Decisions (rate by decision)",
  "type": "timeseries",
  "datasource": {
    "type": "prometheus",
    "uid": "PROM_DS_UID"
  },
  "gridPos": { "h": 8, "w": 24, "x": 0, "y": 16 },
  "targets": [
    {
      "refId": "A",
      "expr": "sum by (decision) (rate(cj_workflow_decisions_total[5m]))",
      "legendFormat": "{{decision}}"
    }
  ],
  "fieldConfig": {
    "defaults": { "unit": "1/s" },
    "overrides": []
  }
}
```

- Guardrail: this metric is **diagnostic only**. It does **not** change:
  - PR‑2 stability thresholds or success-rate gating.
  - PR‑7 small-net semantics or resampling caps.
  - BT SE / coverage semantics derived from `bt_se_summary` and
    `bt_quality_flags`.

## Experiments to run (ENG5 Runner)
1) Stability sweep: vary SCORE_STABILITY_THRESHOLD (0.025–0.05) and measure cost vs agreement vs iterations; choose per-assignment default.
2) Cache TTL sweep: compare 600s vs 3600s vs 14400s on repeated prompts; record hit rate and token savings.
3) Model/prompt anchor tests: mix official + teacher anchors; measure grade projection consistency and cost.

## Prompt cache warm-up – acceptance criteria
- Seed once per unique prompt hash (static cacheable blocks + tool schema) before dispatching the rest of that hash cohort; essays remain non-cacheable.
- After the seed completes, cache miss rate per hash should drop to ≤20% and converge to near-0 within the next request (PromQL hit rate over 5m window).
- TTL ordering must hold (1h blocks before 5m blocks); system/tool blocks keep `cache_control` aligned with `USE_EXTENDED_TTL_FOR_SERVICE_CONSTANTS` (default 5m).
- No essay caching or A/B slot tricks; cacheable scope is system/rubric/instructions/tool schema only.
- Warm-up scheduling avoids concurrent first-writes (light jitter or ordered dequeue) to prevent thundering-herd misses.
- Callback metadata must include `prompt_sha256` and provider cache usage (`usage`, `cache_read_input_tokens`, `cache_creation_input_tokens`) without overwriting caller metadata (essay IDs, batch IDs, etc.).
- **Benchmark runs paused (2025-11-23):** Smoke artefacts are sufficient for operational decisions; final validation runs are deferred until deployment window. Do not run prompt-cache benchmarks until unpaused.
- **Haiku caching stance:** Leave cacheable prefix uninflated (1.0–1.3k tokens) and accept bypass for Haiku; use Sonnet for caching validation. Haiku remains the default dev model; ENG5 Runner experiments will compare Haiku vs Sonnet and drive the production model choice based on hit-rate + cost/latency tradeoffs.

## Open work (align with .claude/work/tasks)
- PR2: Pair position fairness (balanced A/B for anchors/students).
- PR3: Extend Anthropic tests to 529 + stop_reason; add PromQL snippets for error_type and cache hit rate.
- PR4: Queue/orphan hygiene (timeouts for PROCESSING, orphan callback detection + metrics).
- Remove BatchMonitor 80% heuristic after timeout-only bake.
- Prompt segmentation: split cacheable static blocks (system, tool schema, rubric/instructions) from dynamic essay blocks; add hit/miss + tokens-saved metrics.

## Assignment vs no-assignment behavior
- With assignment_id: hydrate prompt/rubric/anchors; grade projections enabled; cached prompts encouraged.
- Without assignment_id: rankings only; projections off; shorter cache TTL recommended.

## Planned PR: staged submission for serial bundles (non-batch-API)
- Purpose/story: prevent flooding the full comparison budget at once. Submit comparisons in waves (N bundles per wave), wait for callbacks, run stability check (`SCORE_STABILITY_THRESHOLD`, `MIN_COMPARISONS_FOR_STABILITY_CHECK`), then decide whether to enqueue the next wave. Goal: earlier convergence, lower cost/latency, clearer observability.
- Entry points: initial submission via `submit_comparisons_for_async_processing`, continuation via `workflow_continuation.trigger_existing_workflow_continuation` which calls `comparison_processing.request_additional_comparisons_for_batch`.
- Scope: `cj_core_logic/comparison_processing.py` (wave size emerges from batch size, matching strategy, and `MAX_PAIRWISE_COMPARISONS`) and `workflow_continuation.py` (stability/budget checks after each wave); stability is governed by `MIN_COMPARISONS_FOR_STABILITY_CHECK`, `SCORE_STABILITY_THRESHOLD`, `MAX_PAIRWISE_COMPARISONS`, and small-net coverage metadata on `CJBatchState.processing_metadata`, with no separate per-wave size setting.
- Acceptance: early stop when stable/complete; metrics/events stay thin (no per-iteration vectors); integration/functional tests verify staged submission and stability stop.

## File upload traceability & assignment_id guidance
- Regular/class batches: assignment_id at upload is recommended for filename-level audit but not required for pipeline execution or student mapping (ELS/Class Mgmt already ties essay_id → student_id). If assignment_id is supplied later (before CJ), ensure BOS/ELS propagate it into the CJ request; uploads may stay unset unless you need filename-level audit.
- Guest batches: strongly recommended. There is no student context, so CJ → filename joins rely on `file_uploads` having `text_storage_id` (now stored) and, for contextual reporting, `assignment_id`.
- Best-practice backfill (preferred): add a File Service endpoint `/v1/files/batch/{batch_id}/assignment` that validates ownership and updates all `file_uploads.assignment_id` for the batch. Alternate options: BOS → File Service command/event to update uploads when assignment_id is captured, or a one-off repository-based backfill script (transactional, audited).

### Acceptance criteria for traceability
1) For new uploads, `file_uploads` rows store `text_storage_id` and (when provided) `assignment_id`; joins CJ ranking → text_storage_id → filename work in guest and class flows.
2) For late-provided assignment_id, BOS/ELS propagate it into the CJ request before batch prep; if filename-level audit is required, the chosen backfill path updates `file_uploads.assignment_id` for the batch.
3) Functional runs default to `FUNCTIONAL_ASSIGNMENT_ID` and run with mock LLM; suite skips if mock mode is disabled unless explicitly overridden.

## Owners/rollout (solo-friendly)
- Defaults above are starting points; adjust per experiment results. Keep batching mode (`per_request`, `serial_bundle`, `provider_batch_api`) and prompt cache TTL overridable per env.

Update guidance: treat this doc like handoff/readme_first—update whenever behavior, defaults, or metrics change in CJ, LLM Provider, ENG5 Runner, or API Gateway integration.

## Related references
- .claude/work/session/handoff.md (current session context)
- .claude/work/session/readme-first.md (service status snapshot)
- docs/operations/llm-provider-configuration-hierarchy.md (LLM mock/real config precedence)
- Tasks: key trackers aligned to this doc:
  - TASKS/assessment/filename-propagation-from-els-to-ras-for-teacher-result-visibility.md (US-1, US-2 fix)
  - .claude/work/tasks/TASK-CJ-LLM-SERIAL-BUNDLE-VALIDATION-FIXES.md
  - .claude/work/tasks/TASK-CJ-BATCH-STATE-AND-COMPLETION-FIXES.md
  - .claude/work/tasks/TASK-LLM-BATCH-STRATEGY-IMPLEMENTATION.md (+ checklist child)
  - .claude/work/tasks/TASK-LLM-BATCH-STRATEGY-LPS-IMPLEMENTATION.md
  - .claude/work/tasks/TASK-LLM-SERIAL-BUNDLE-METRICS-AND-DIAGNOSTICS-FIX.md
  - .claude/work/tasks/TASK-LLM-QUEUE-EXPIRY-METRICS-FIX.md
- Investigation reports:
  - .claude/work/reports/2025-11-27-filename-propagation-flow-mapping.md
