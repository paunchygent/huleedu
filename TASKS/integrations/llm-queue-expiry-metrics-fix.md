---
id: llm-queue-expiry-metrics-fix
title: Llm Queue Expiry Metrics Fix
type: task
status: archived
priority: high
domain: integrations
owner_team: agents
created: '2025-11-18'
last_updated: '2025-11-21'
service: llm_provider_service
owner: ''
program: ''
related: []
labels: []
---

Related reference: docs/operations/cj-assessment-runbook.md

# TASK-LLM-QUEUE-EXPIRY-METRICS-FIX – Expired Request Metrics & Observability Plan

This checklist decomposes the expired-request metrics bug into a sequence of small, focused PRs. It follows the LLM batching strategy task structure and aligns with Phase 3 observability work for the LLM Provider Service.

Context:
- Service: **LLM Provider Service**
- Area: **Queue processing, expiry handling, Prometheus metrics**
- Existing behaviour:
  - Expired requests are detected in `QueueProcessorImpl._process_queue_loop` and `_process_request_serial_bundle` and marked `QueueStatus.EXPIRED` via `_handle_expired_request`.
  - `_record_completion_metrics` is currently called with `result="expired"` and `processing_started=time.perf_counter()`, which produces misleading processing-time and callback metrics.
  - Local/Redis queue managers also delete expired entries directly, without producing explicit expiry metrics.

Goal: Introduce dedicated expiry metrics and correct queue metrics semantics so that expired requests have accurate, interpretable observability without corrupting processing or callback metrics.

---

## PR 1 – Introduce Dedicated Expiry Metrics in LLM Provider Service (IMPLEMENTED)

**Goal:** Add dedicated Prometheus metrics for expired requests in the LLM Provider Service, without changing any runtime logic or existing metric emission code.

### Files

- `services/llm_provider_service/metrics.py`
  - Shared metrics registry and `get_queue_metrics()` accessors.

### Checklist

- **Metric definitions (registry)**
  - **[x]** Add `llm_queue_expiry_total` counter:
    - Name: `llm_provider_queue_expiry_total`.
    - Help: `"Total expired queue requests"`.
    - Labels: `provider`, `queue_processing_mode`, `expiry_reason`.
    - `expiry_reason` values should be a **small fixed set**, e.g.: `"ttl"`, `"cleanup"`, `"marker_missing"`.
  - **[x]** Add `llm_queue_expiry_age_seconds` histogram:
    - Name: `llm_provider_queue_expiry_age_seconds`.
    - Help: `"Age of requests at expiry in seconds"`.
    - Labels: `provider`, `queue_processing_mode`.
    - Buckets: `(1, 5, 10, 30, 60, 120, 300, 600, 1800, 3600)` to cover ~1s–1h.

- **Queue metrics accessor**
  - **[x]** Expose the new metrics via `get_queue_metrics()`:
    - Add keys: `"llm_queue_expiry_total"`, `"llm_queue_expiry_age_seconds"`.
    - Ensure they are also discoverable via `_get_existing_metrics()` name map for duplicate-registration scenarios during tests.

- **Documentation alignment**
  - **[x]** Validate naming and label choices against `.windsurf/rules/071.2-prometheus-metrics-patterns.md` (no high-cardinality labels, no IDs or correlation IDs).
  - **[x]** Add a short note in the LLM Provider Service README to mention the new metrics under queue observability.

- **Validation**
  - **[x]** Run `pdm run pytest-root services/llm_provider_service/tests/unit` to ensure no tests depend on an exact `get_queue_metrics()` key set.
  - **[x]** Run `pdm run typecheck-all` to confirm type hints and imports remain valid.

---

## PR 2 – Correct QueueProcessor Completion Metrics for Expired Requests (IMPLEMENTED)

**Goal:** Fix the expired-request path in `QueueProcessorImpl` so that it no longer records bogus processing-time or callback metrics, and instead uses the new expiry metrics. Queue behaviour (status transitions, cleanup) must remain unchanged.

### Files

- `services/llm_provider_service/implementations/queue_processor_impl.py`
  - `_process_queue_loop`
  - `_process_request_serial_bundle`
  - `_record_completion_metrics`

### Checklist

- **Add a helper for expiry metrics**
  - **[x]** Introduce a private method, e.g. `_record_expiry_metrics(self, *, request: QueuedRequest, provider: LLMProviderType, expiry_reason: str) -> None`:
    - Look up `expiry_counter = self.queue_metrics.get("llm_queue_expiry_total")` and `expiry_age_hist = self.queue_metrics.get("llm_queue_expiry_age_seconds")`.
    - Compute age: `(datetime.now(timezone.utc) - request.queued_at).total_seconds()` (clamped at ≥ 0.0).
    - When collectors are present:
      - Increment `expiry_counter.labels(provider=provider.value, queue_processing_mode=self.queue_processing_mode.value, expiry_reason=expiry_reason).inc()`.
      - Observe `expiry_age_hist.labels(provider=provider.value, queue_processing_mode=self.queue_processing_mode.value).observe(age_seconds)`.

- **Use helper in main queue loop**
  - **[x]** In `_process_queue_loop`, after detecting `self._is_expired(request)` and calling `_handle_expired_request(request)`:
    - Resolve provider: `provider = self._resolve_provider_from_request(request)`.
    - Call `_record_expiry_metrics(request=request, provider=provider, expiry_reason="ttl")`.
    - **Remove** the call to `_record_completion_metrics` for `result="expired"` **or** ensure it is called with `processing_started=None` if you adopt the API change below.

- **Use helper in serial bundle path**
  - **[x]** In `_process_request_serial_bundle`, when `next_request` is expired:
    - After `_handle_expired_request(next_request)`, resolve provider via `_resolve_provider_from_request(next_request)`.
    - Call `_record_expiry_metrics(request=next_request, provider=expired_provider, expiry_reason="ttl")`.
    - **Remove** the existing `_record_completion_metrics(..., result="expired", processing_started=time.perf_counter())` call.

- **Change `_record_completion_metrics` contract**
  - **[x]** Update `_record_completion_metrics` signature to accept `processing_started: float | None` (instead of `float` only).
  - **[x]** Inside `_record_completion_metrics`:
    - Always record **wait time** for all results (including `"expired"`) using existing `llm_queue_wait_time_seconds`, but consider that expiry-specific age is now captured in `llm_queue_expiry_age_seconds`.
    - Only record **processing time** in `llm_queue_processing_time_seconds` when `processing_started is not None` **and** `result in {"success", "failure"}`.
    - Only increment `llm_comparison_callbacks_total` when `processing_started is not None` **and** `result in {"success", "failure"}` (i.e. paths that actually publish callbacks).
    - For `result="expired"` or any call with `processing_started is None`, skip processing-time and callbacks.

- **Update callers of `_record_completion_metrics`**
  - **[x]** Ensure all success and failure paths (`_process_request` and `_process_request_serial_bundle`) still pass a non-`None` `processing_started` captured before work begins.
  - **[x]** Ensure no remaining code paths call `_record_completion_metrics` with `result="expired"` and a non-`None` start time.

- **Validation**
  - **[x]** Run `pdm run pytest-root services/llm_provider_service/tests/unit/test_queue_processor_error_handling.py` (and neighbouring tests) to confirm no regressions.
  - **[x]** Run `pdm run typecheck-all` and `pdm run lint-fix --unsafe-fixes` to catch signature and import issues.

---

## PR 3 – Optional: Instrument Manager-Level Expiry Cleanup (IMPLEMENTED)

**Goal:** Add coarse-grained expiry metrics for requests that are purged by the queue managers (Redis/local) without ever reaching `QueueProcessorImpl`. This is optional and can be delayed, but it closes the observability gap for “silent” expiries.

### Files

- `services/llm_provider_service/implementations/resilient_queue_manager_impl.py`
  - `cleanup_expired`
- `services/llm_provider_service/implementations/local_queue_manager_impl.py`
  - `_cleanup_expired_internal`
- `services/llm_provider_service/implementations/redis_queue_repository_impl.py`
  - `cleanup_expired` or `batch_delete_expired`

### Checklist

- **Expose queue metrics to the manager layer (optional)**
  - **[x]** Decide whether `ResilientQueueManagerImpl` should receive a metrics handle (e.g. `queue_metrics: dict[str, Any] | None`) via DI, or if this PR is limited to queue-processor-level metrics only.
  - **[x]** If you introduce metrics at this layer, prefer a minimal subset (e.g. only `llm_queue_expiry_total` with `provider="unknown"`).

- **Increment expiry counter on manager-level cleanup**
  - **[x]** When `cleanup_expired()` in `ResilientQueueManagerImpl` removes items, optionally increment `llm_queue_expiry_total` with:
    - `provider="unknown"` (since the provider may not be cheap to compute here).
    - `queue_processing_mode` omitted or set to a fixed label (e.g. `"unknown"`) if you do not have access to mode in this layer.
    - `expiry_reason="cleanup"`.
  - **[ ]** If you are not comfortable approximating provider/mode here, explicitly document that manager-level expiries are **not** separately tagged and rely instead on `cleanup_expired` logs plus queue-processor-level metrics.

- **Do not duplicate age metrics**
  - **[x]** Avoid recording `llm_queue_expiry_age_seconds` here unless you can cheaply reconstruct `queued_at`. Otherwise, accept that age metrics are only accurate for expiries observed in `QueueProcessorImpl`.

- **Validation**
  - **[x]** Confirm that added metrics do not introduce additional Redis calls in hot paths (keep overhead small).
  - **[x]** Run targeted tests for Redis/local cleanup if new behaviour is added.

---

## PR 4 – Test Coverage & Regression Protection (IMPLEMENTED)

**Goal:** Add focused tests that validate the new expiry metrics behaviour and guard against regressions in queue metrics for expired, successful, and failed requests.

### Files

- `services/llm_provider_service/tests/unit/test_queue_processor_error_handling.py`
- (Optionally) `services/llm_provider_service/tests/integration/test_mock_provider_with_queue_processor.py`

### Checklist

- **Unit tests: expired requests (per-request path)**
  - **[x]** Add `test_expired_request_records_expiry_metrics_not_processing_time_or_callbacks`:
    - Arrange:
      - Create a `QueueProcessorImpl` with a `queue_metrics` dict populated from `get_queue_metrics()`.
      - Build a `QueuedRequest` whose `queued_at` is some seconds in the past and `ttl` small enough that `_is_expired` returns `True`.
      - Stub `queue_manager.dequeue()` to yield this request once, then `None`.
      - Stub `queue_manager.update_status()` and `_handle_expired_request()`.
    - Act:
      - Run a single iteration of `_process_queue_loop()` (or call the internal branch directly) that processes the expired request.
    - Assert:
      - `llm_queue_expiry_total` increments by 1 with `expiry_reason="ttl"` and the correct `queue_processing_mode` label.
      - `llm_queue_expiry_age_seconds` observes a value ≥ the expected age.
      - `llm_queue_processing_time_seconds` does **not** observe any value for `result="expired"`.
      - `llm_comparison_callbacks_total` is **not** incremented for `result="expired"`.

- **Unit tests: expired requests (serial bundle path)**
  - **[x]** Add a test where `_process_request_serial_bundle` encounters at least one expired request while building a bundle:
    - Arrange:
      - First request: valid, non-expired.
      - Second request: expired.
      - Stub `queue_manager.dequeue()` to yield the expired request then `None`.
    - Assert:
      - Expired request drives expiry metrics as above.
      - Only the valid request goes through success/failure metrics and callbacks.

- **Regression tests for success/failure metrics**
  - **[x]** Ensure existing tests for success and error paths still pass and, if helpful, add explicit assertions that:
    - `llm_queue_processing_time_seconds` and `llm_comparison_callbacks_total` are recorded for success/failure results.
    - Wait-time metrics remain present for all processed items.

- **Optional integration test**
  - **[ ]** Extend `test_mock_provider_with_queue_processor.py` to run a small, end-to-end scenario involving:
    - At least one request that expires before processing.
    - At least one request that is processed successfully.
    - Snapshot or inspect the metrics registry to ensure expiry and processing metrics line up with expectations (if feasible in the test harness).

---

## Success Criteria

- Expired requests are visible via dedicated metrics:
  - `llm_provider_queue_expiry_total{provider, queue_processing_mode, expiry_reason}` – `expiry_reason="ttl"` from `QueueProcessorImpl` when dequeued requests exceed TTL, `expiry_reason="cleanup"` from `ResilientQueueManagerImpl.cleanup_expired()` when Redis/local cleanup purges entries (with `provider="unknown"`).
  - `llm_provider_queue_expiry_age_seconds{provider, queue_processing_mode}` – age-at-expiry histogram recorded only from the queue processor path.
- Expired requests **do not** distort processing-time or callback metrics:
  - `llm_provider_queue_processing_time_seconds` only reflects actual processing work.
  - `llm_provider_comparison_callbacks_total` matches real callback events (success/failure only).
- Queue behaviour (status transitions, cleanup, retry semantics) is unchanged.
- Unit tests cover the expired-path semantics and protect against regression in future metrics changes.
