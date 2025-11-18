---
id: "llm-serial-bundle-metrics-and-diagnostics-fix"
title: "LLM Serial Bundle Metrics & Diagnostics Fix"
type: "task"
status: "todo"
priority: "high"
domain: "assessment"
service: "llm_provider_service"
owner_team: "agents"
owner: ""
program: ""
created: "2025-11-18"
last_updated: "2025-11-18"
related: [".claude/work/tasks/TASK-LLM-BATCH-STRATEGY-IMPLEMENTATION-CHECKLIST.md"]
labels: []
---

# TASK-LLM-SERIAL-BUNDLE-METRICS-AND-DIAGNOSTICS-FIX – Serial Bundling Observability & CJ Batching Metrics

This checklist decomposes the remaining serial-bundling observability work into focused PRs.
It builds on:

- `TASK-LLM-BATCH-STRATEGY-IMPLEMENTATION-CHECKLIST.md`
- `TASK-LLM-SERIAL-BUNDLING.md`
- `TASK-LLM-QUEUE-EXPIRY-METRICS-FIX.md`

The goal is to close the gaps around metadata enrichment, serial-bundle metrics, CJ batching
metrics, and diagnostics/runbooks so that `QueueProcessingMode.SERIAL_BUNDLE` can be rolled out
safely (ENG5-first, then production).

Context:

- Services: **LLM Provider Service**, **CJ Assessment Service**
- Areas: **Queue processing, batching metadata, Prometheus metrics, ENG5 diagnostics**
- Current state:
  - Serial bundle infrastructure is implemented and tested at the unit level.
  - Queue expiry metrics are implemented and validated (`llm_provider_queue_expiry_*`).
  - CJ-side batching configuration and metadata hints are fully wired and tested.

Goal: Introduce provider-side metadata enrichment, serial-bundle metrics, CJ batching metrics, and
integration tests, plus rollout docs and diagnostics, without regressing existing per-request
behaviour or queue expiry semantics.

---

## PR 1 – Provider-Side Metadata Enrichment in LLM Provider Service

**Goal:** Enrich queued requests and downstream diagnostics with provider-side metadata after
routing decisions have been made in `QueueProcessorImpl`, without breaking existing CJ → LPS
metadata contracts.

### Files

- `services/llm_provider_service/implementations/queue_processor_impl.py`
- (Tests) `services/llm_provider_service/tests/unit/test_queue_processor_error_handling.py` (and/or
  a new dedicated test module for metadata enrichment)

### Checklist

- **Add helper to enrich metadata**
  - **[x]** Introduce a small private helper, e.g.
    - `_enrich_request_metadata(self, request: QueuedRequest, *, provider: LLMProviderType, model: str | None) -> None`.
  - **[x]** Inside the helper:
    - Load `metadata = request.request_data.metadata or {}`.
    - Preserve existing keys untouched (e.g. `essay_a_id`, `essay_b_id`, `bos_batch_id`,
      `cj_batch_id`, `cj_source`, `cj_request_type`, `cj_llm_batching_mode`).
    - Add/overwrite **additive** keys only:
      - `"resolved_provider"`: `provider.value`.
      - `"resolved_model"`: derived from `model` argument when present, otherwise from
        overrides (e.g. `model_override`) or left `None`/omitted.
      - `"queue_processing_mode"`: `self.queue_processing_mode.value`.
    - Reassign the updated dict back to `request.request_data.metadata`.

- **Wire helper into per-request path**
  - **[x]** In `_process_request`:
    - After resolving `provider = self._resolve_provider_from_request(request)` and computing
      `overrides = self._build_override_kwargs(request)`, but **before** tracing/processor calls:
      - Compute a provisional `model_hint = overrides.get("model_override")`.
      - Call `_enrich_request_metadata(request, provider=provider, model=model_hint)`.
    - Keep enrichment **idempotent** so that repeated calls do not change semantics.

- **Wire helper into serial-bundle path**
  - **[x]** In `_process_request_serial_bundle`:
    - For the **first** (primary) request:
      - After `primary_provider`/`primary_overrides` are resolved and before logging,
        call `_enrich_request_metadata(first_request, provider=primary_provider,
        model=primary_overrides.get("model_override"))`.
    - For each **compatible** `next_request` added to the bundle:
      - After computing `candidate_provider` and `candidate_overrides` and before adding to
        `bundle_requests`, call `_enrich_request_metadata(next_request, provider=candidate_provider,
        model=candidate_overrides.get("model_override"))`.
    - Do **not** enrich metadata for expired requests beyond what is already done; keep expiry
      paths focused on metrics and status.

- **Ensure enrichment is visible in logs and callbacks**
  - **[ ]** Confirm that enriched fields propagate to:
    - Any structured logs that already print `request.request_data.metadata` or include extra
      context derived from it.
    - Callback payloads and completion events where metadata is forwarded (no new fields need to
      be added here yet; this PR focuses on request metadata only).

- **Unit tests for metadata enrichment**
  - **[x]** Add or update tests to assert that when a queued request is processed:
    - `request.request_data.metadata["resolved_provider"] == provider.value`.
    - `request.request_data.metadata["queue_processing_mode"] == self.queue_processing_mode.value`.
    - `"resolved_model"` is set consistently with the model override (if provided).
    - All legacy CJ metadata keys remain intact and unchanged.
  - **[x]** Cover both `QueueProcessingMode.PER_REQUEST` and `QueueProcessingMode.SERIAL_BUNDLE`.

- **Validation**
  - **[ ]** Run `pdm run pytest-root services/llm_provider_service/tests/unit`.
  - **[ ]** Run `pdm run typecheck-all` and `pdm run lint-fix --unsafe-fixes`.

---

## PR 2 – Serial Bundle Metrics in LLM Provider Service

**Goal:** Add Prometheus metrics for serial-bundle usage and bundle sizes in the LLM Provider
Service, using low-cardinality labels and aligning with existing observability standards.

### Files

- `services/llm_provider_service/metrics.py`
- `services/llm_provider_service/implementations/queue_processor_impl.py`
- (Tests) `services/llm_provider_service/tests/unit/` (new or existing modules)

### Checklist

- **Metric definitions (registry)**
  - **[ ]** Add `llm_serial_bundle_calls_total` counter:
    - Name: `llm_provider_serial_bundle_calls_total`.
    - Help: `"Total serial-bundle comparison calls"`.
    - Labels: `provider`, `model`.
  - **[ ]** Add `llm_serial_bundle_items_per_call_bucket` histogram:
    - Name: `llm_provider_serial_bundle_items_per_call`.
    - Help: `"Number of items per serial-bundle call"`.
    - Labels: `provider`, `model`.
    - Buckets: e.g. `(1, 2, 4, 8, 16, 32, 64)`.
  - **[ ]** Expose new metrics from `get_metrics()` and `get_queue_metrics()` as needed, keeping
    naming aligned with `.windsurf/rules/071.2-prometheus-metrics-patterns.md`.

- **Instrumentation point (serial bundle path)**
  - **[ ]** In `_process_request_serial_bundle`, after a **successful** call to
    `process_comparison_batch` (i.e. no exception):
    - Derive `bundle_size = len(bundle_requests)`.
    - Derive `provider_label = primary_provider.value`.
    - Derive `model_label` from the same source used by `resolved_model` (override or `None`).
    - Increment:
      - `llm_serial_bundle_calls_total.labels(provider=provider_label, model=model_label).inc()`.
      - `llm_serial_bundle_items_per_call_bucket.labels(provider=provider_label, model=model_label).observe(bundle_size)`.
  - **[ ]** Ensure no serial-bundle metrics are emitted in `QueueProcessingMode.PER_REQUEST`.

- **Unit tests**
  - **[ ]** Add tests that:
    - Run `_process_request_serial_bundle` with a mocked `comparison_processor` and metrics
      registry populated via `get_queue_metrics()` / `get_metrics()`.
    - Assert that one bundle-processing run increments `llm_serial_bundle_calls_total` and
      records the expected `bundle_size` in `llm_serial_bundle_items_per_call_bucket`.
    - Confirm that per-request mode does **not** produce serial-bundle metrics.

- **Validation**
  - **[ ]** Run `pdm run pytest-root services/llm_provider_service/tests/unit`.
  - **[ ]** Run `pdm run typecheck-all` and `pdm run lint-fix --unsafe-fixes`.

---

## PR 3 – CJ Batching Metrics & Exposure

**Goal:** Add CJ-level Prometheus metrics for LLM usage by batching mode so that ENG5 and
operational dashboards can see how often each batching mode is exercised.

### Files

- `services/cj_assessment_service/metrics.py`
- `services/cj_assessment_service/cj_core_logic/comparison_processing.py`
- (Optionally) `services/cj_assessment_service/cj_core_logic/batch_processor.py` or
  `batch_submission.py` for batch-level instrumentation
- (Tests) `services/cj_assessment_service/tests/unit/`

### Checklist

- **Metric definitions (CJ metrics module)**
  - **[ ]** Add `cj_llm_requests_total` counter:
    - Name: `cj_llm_requests_total`.
    - Help: `"Total CJ LLM requests by batching mode"`.
    - Labels: `batching_mode`.
  - **[ ]** Add `cj_llm_batches_started_total` counter:
    - Name: `cj_llm_batches_started_total`.
    - Help: `"Total CJ batches started by batching mode"`.
    - Labels: `batching_mode`.
  - **[ ]** Register these metrics in `_create_metrics()` and `_get_existing_metrics()` and expose
    them via `get_business_metrics()` if appropriate.

- **Instrumentation (per-request counts)**
  - **[ ]** In `comparison_processing.submit_comparisons_for_async_processing` (or equivalent
    entry point):
    - After resolving `effective_mode` from `batch_config_overrides.llm_batching_mode_override`
      and `settings.LLM_BATCHING_MODE`, increment:
      - `cj_llm_requests_total.labels(batching_mode=effective_mode.value).inc(len(comparison_tasks_for_llm))`.

- **Instrumentation (per-batch counts)**
  - **[ ]** Identify the point where a CJ batch is first opened / started (typically when the first
    set of comparisons is submitted for a given batch):
    - Increment `cj_llm_batches_started_total.labels(batching_mode=effective_mode.value).inc()`
      once per logical CJ batch.
    - Ensure that retries / continuation runs do **not** double-count unless intentionally treated
      as separate batches.

- **Unit tests**
  - **[ ]** Add tests that configure different `LLM_BATCHING_MODE` values and overrides, then
    assert that:
      - The correct `batching_mode` label is used when incrementing metrics.
      - Metrics counts match the number of tasks and batches created.

- **Validation**
  - **[ ]** Run `pdm run pytest-root services/cj_assessment_service/tests/unit`.
  - **[ ]** Run `pdm run typecheck-all` and `pdm run lint-fix --unsafe-fixes`.

---

## PR 4 – Serial Bundle Integration Tests (Queue + Metrics)

**Goal:** Add integration tests that exercise serial-bundle mode with the real queue manager
(Local/Redis test configuration) to validate metrics, fairness, and expiry behaviour under
`QueueProcessingMode.SERIAL_BUNDLE`.

### Files

- `services/llm_provider_service/tests/integration/` (new test module)
- Existing mock provider + queue processor test harness (if available)

### Checklist

- **Happy-path serial bundle scenario**
  - **[ ]** Create an integration test that:
    - Starts a queue processor with `QUEUE_PROCESSING_MODE=serial_bundle` and a deterministic
      Local/Redis queue backend.
    - Enqueues multiple **compatible** requests (same provider, same overrides, same
      `cj_llm_batching_mode` hint).
    - Asserts that:
      - A single `process_comparison_batch` call is made with N items.
      - All queued requests transition to `COMPLETED`.
      - Serial-bundle metrics reflect 1 call and N items.

- **Fairness / compatibility scenario**
  - **[ ]** Add a test where the queue contains requests with mixed providers/models/hints:
    - Verify that compatible requests are bundled.
    - Verify that the first incompatible request is stored in `_pending_request` and processed on
      a later iteration (no loss, no starvation of other providers).

- **Expired + active mix scenario**
  - **[ ]** Add a test where at least one request is already expired when dequeued:
    - Confirm that expiry metrics (`llm_provider_queue_expiry_*`) are recorded correctly.
    - Confirm that only non-expired requests contribute to processing/callback and serial-bundle
      metrics.

- **Regression coverage**
  - **[ ]** Ensure integration tests validate that per-request mode is unaffected when
    `QUEUE_PROCESSING_MODE=per_request` (no serial-bundle metrics, same behaviour as before).

- **Validation**
  - **[ ]** Run `pdm run pytest-root services/llm_provider_service/tests/integration`.
  - **[ ]** Run `pdm run typecheck-all` and `pdm run lint-fix --unsafe-fixes`.

---

## PR 5 – Rollout Documentation & ENG5 Diagnostics

**Goal:** Document batching mode trade-offs and rollout procedures, and extend ENG5 diagnostics to
surface batching mode and LPS metrics, enabling safe ENG5-first rollout of serial bundling.

### Files

- `.claude/work/tasks/TASK-LLM-BATCH-STRATEGY-IMPLEMENTATION.md`
- `.claude/work/tasks/TASK-LLM-SERIAL-BUNDLING.md`
- Service READMEs:
  - `services/llm_provider_service/README.md`
  - `services/cj_assessment_service/README.md`
- ENG5 diagnostics / runner scripts:
  - `scripts/cj_experiments_runners/eng5_np/cli.py`
  - Any ENG5 diagnostics helpers under `scripts/`

### Checklist

- **Document batching modes and mapping**
  - **[ ]** In `TASK-LLM-BATCH-STRATEGY-IMPLEMENTATION.md` (or a closely related doc), add a
    matrix that shows:
    - CJ `LLM_BATCHING_MODE` values.
    - LPS `QUEUE_PROCESSING_MODE` and `BATCH_API_MODE` combinations.
    - Recommended usage (e.g. ENG5-heavy runs vs standard BOS/ELS flows).
  - **[ ]** Summarize trade-offs for each mode: cost, latency, error surface, observability.

- **Update LPS & CJ READMEs**
  - **[ ]** Add short sections to LPS and CJ READMEs describing:
    - Available batching modes and relevant env vars.
    - Key metrics to watch (serial-bundle metrics, CJ batching metrics, queue depth/latency).
    - Basic guidance for enabling/disabling serial bundling.

- **ENG5 diagnostics & tooling**
  - **[ ]** Extend ENG5 runner/diagnostics to:
    - Display the effective `LLM_BATCHING_MODE` and any batch-level overrides in summaries.
    - Optionally, fetch and summarize LPS metrics for serial-bundle usage and request volumes,
      scoped to an ENG5 run where possible.
    - Confirm that `correlation_id` tracing behaves consistently across batching modes.

- **Rollout and rollback procedures**
  - **[ ]** Document in an appropriate runbook (or in the TASK doc) how to:
    - Enable serial_bundle for ENG5-only workloads via env vars.
    - Validate via metrics before widening rollout.
    - Roll back to `per_request` safely if error rates or latencies regress.

- **Validation**
  - **[ ]** Perform at least one ENG5 `execute` run with `serial_bundle` enabled and verify:
    - Metrics and diagnostics produce expected output.
    - No regressions in callback handling or CJ batch completion.

---

## Success Criteria

- Serial bundle metadata is enriched with `resolved_provider`, `resolved_model`, and
  `queue_processing_mode` without breaking existing CJ → LPS contracts.
- Serial-bundling metrics in LPS (`llm_provider_serial_bundle_calls_total`,
  `llm_provider_serial_bundle_items_per_call`) provide clear visibility into bundle usage and
  sizes per provider/model.
- CJ-level batching metrics (`cj_llm_requests_total`, `cj_llm_batches_started_total`) are
  available and correctly labelled by `batching_mode`.
- Integration tests validate serial bundle behaviour across queue backends, including fairness,
  expiry handling, and metric correctness.
- Documentation and ENG5 diagnostics clearly explain how batching modes are configured, how to
  interpret the new metrics, and how to enable/roll back serial bundling safely.
