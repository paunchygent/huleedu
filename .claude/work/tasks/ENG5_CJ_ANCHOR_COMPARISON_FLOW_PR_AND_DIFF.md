# PR: ENG5 NP Runner ↔ CJ Assessment Service – Anchor & Comparison Behaviour Fixes

Parent/overview: `ENG5_CJ_ANCHOR_COMPARISON_FLOW.md`.

This child doc is intended to be pasted into a PR description and used as a diff-level review guide.

---

## 1. Summary

This PR tightens the ENG5 NP runner ↔ CJ Assessment Service integration around **anchors** and **comparisons**:

- Enforces the principle that **anchors are DB-owned**. EXECUTE runs now fail fast unless anchors are successfully registered with CJ, and the runner never falls back to uploading “ephemeral” anchors.
- Removes runner-side comparison slicing. All essays are uploaded, and the optional `--max-comparisons` flag is forwarded to CJ as metadata so the service can decide how to apply it.
- Fixes the CJ service configuration bug where `COMPARISONS_PER_STABILITY_CHECK_ITERATION` was effectively ignored. Pair generation now honours both the configured per-iteration threshold and `MAX_PAIRWISE_COMPARISONS`.

The overall outcome is that CJ receives **all configured anchors**, a more appropriate number of **student comparisons**, and can produce more reliable **Bradley–Terry scores** and **grade projections**.

---

## 2. Scope

- **Runner (ENG5 NP):**
  - Make anchor registration mandatory and fail-fast for `EXECUTE` runs.
  - Remove runner-owned comparison limiting (`apply_comparison_limit`); CJ owns comparison density.

- **CJ Assessment Service:**
  - Correct `COMPARISONS_PER_STABILITY_CHECK_ITERATION` wiring.
  - Prepare for (but not yet fully implement) more robust BT convergence.

Out of scope for this PR: full iterative BT loop in `workflow_continuation`, contract changes to `ELS_CJAssessmentRequestV1`, and any DB schema changes.

---

## 3. Changes – Runner (ENG5 NP)

### 3.1 `scripts/cj_experiments_runners/eng5_np/cli.py`

**Behavioural intent (now implemented)**

- ENG5 `EXECUTE` runs use **only DB-backed anchors**.
- Any anchor registration failure is a **hard error**; the runner fails fast and highlights the underlying config/endpoint problem.

**Proposed changes**

**Implemented behaviour**

1. **Anchor registration is mandatory in EXECUTE mode:**

   - The runner now requires `cj_service_url` when anchor files exist.
   - On `AnchorRegistrationError` (or empty registration response) the CLI raises a `RuntimeError` and aborts instead of falling back.

2. **Config errors are surfaced early:**

   - Missing `cj_service_url` in EXECUTE mode produces a targeted error instructing the operator to set `CJ_SERVICE_URL`/`--cj-service-url`.

3. **Anchors are never uploaded in EXECUTE mode:**

   - After successful registration the runner uploads **only student essays**.
   - `essay_refs` contain students exclusively; CJ injects anchors from its DB.


### 3.2 `scripts/cj_experiments_runners/eng5_np/inventory.py`

**Implemented behaviour**

- `apply_comparison_limit` is no longer invoked in EXECUTE mode; all anchors/students are considered once registration succeeds.
- The optional `--max-comparisons` flag is logged for observability and forwarded via envelope metadata (`max_comparisons`). CJ owns how to interpret this hint.

---

## 4. Changes – CJ Assessment Service

### 4.1 `services/cj_assessment_service/config.py`

**Behavioural intent**

- `COMPARISONS_PER_STABILITY_CHECK_ITERATION` should be the **canonical configuration** for how many new comparisons we generate per stability-check iteration.
- `MAX_PAIRWISE_COMPARISONS` is a global cap protecting against pathological workloads.

**Current state**

- `Settings` defines:

  ```python
  MAX_PAIRWISE_COMPARISONS: int = 1000
  COMPARISONS_PER_STABILITY_CHECK_ITERATION: int = 10
  ```

- The service code attempts to use `comparisons_per_stability_check_iteration` (lowercase) via `getattr`, so the configured value is effectively ignored and a hard-coded default of `5` is used.

**Proposed changes**

- No change to the `Settings` model; we only correct call sites.


### 4.2 `services/cj_assessment_service/cj_core_logic/comparison_processing.py`

#### 4.2.1 `submit_comparisons_for_async_processing`

**Implementation notes**

- `submit_comparisons_for_async_processing` now passes `settings.COMPARISONS_PER_STABILITY_CHECK_ITERATION` and `settings.MAX_PAIRWISE_COMPARISONS` directly to `pair_generation.generate_comparison_tasks`.
- The same fix was applied to `_process_comparison_iteration` for parity with future iterative workflows.

#### 4.2.2 `_process_comparison_iteration`

**Current code (simplified):**

```python
comparison_tasks_for_llm: list[ComparisonTask] = await generate_comparison_tasks_coro(
    essays_for_comparison=essays_for_api_model,
    db_session=session,
    cj_batch_id=cj_batch_id,
    existing_pairs_threshold=getattr(settings, "comparisons_per_stability_check_iteration", 5),
    correlation_id=correlation_id,
)
```

**Proposed change:**

- Mirror the same fix:

```diff
-    existing_pairs_threshold=getattr(settings, "comparisons_per_stability_check_iteration", 5),
+    existing_pairs_threshold=getattr(
+        settings,
+        "COMPARISONS_PER_STABILITY_CHECK_ITERATION",
+        10,
+    ),
```

**Note:** `_process_comparison_iteration` is not yet wired into `workflow_continuation`; this PR only ensures its behaviour matches `submit_comparisons_for_async_processing` once it is used.


### 4.3 `services/cj_assessment_service/cj_core_logic/pair_generation.py`

`pair_generation.generate_comparison_tasks` now receives both configuration values and enforces:

- A per-call `existing_pairs_threshold`.
- A global `max_pairwise_comparisons` cap that stops generation once the batch reaches the configured maximum.

---

## 5. Tests and verification

- **Runner tests** now cover:
  - `compose_cj_assessment_request` metadata (including `max_comparisons` passthrough).
  - Existing CLI validation for anchor/student prerequisites.
- **CJ service tests** include `test_generate_comparison_tasks_respects_thresholds_and_global_cap`, verifying the interplay between per-iteration thresholds and the global cap.

---

## 6. Diff-level review checklist

Use this section when reviewing the PR to ensure all intended behaviour changes are correctly implemented and no regressions are introduced.

### 6.1 Runner – `scripts/cj_experiments_runners/eng5_np/cli.py`

- [x] On `AnchorRegistrationError`, `EXECUTE` mode aborts and does **not** fall back to ephemeral anchors.
- [x] When anchors exist but `cj_service_url` is unset, `EXECUTE` mode fails with a clear configuration error.
- [x] In the happy path, `upload_targets` includes **only student essays**, and anchors are not re-uploaded.
- [x] DRY_RUN behaviour remains unchanged.

### 6.2 Runner – `scripts/cj_experiments_runners/eng5_np/inventory.py`

- [x] `apply_comparison_limit` is no longer used in the ENG5 `EXECUTE` path.
- [x] The runner does not slice anchors or students to approximate a comparison budget; CJ settings control comparison density.
- [x] `build_essay_refs` still supports `max_comparisons` for ad-hoc tooling/tests, but EXECUTE mode now passes `None` so all students are included.

### 6.3 CJ service – `cj_core_logic/comparison_processing.py`

- [ ] `submit_comparisons_for_async_processing` uses `COMPARISONS_PER_STABILITY_CHECK_ITERATION` via `getattr(settings, "COMPARISONS_PER_STABILITY_CHECK_ITERATION", 10)`.
- [ ] `_process_comparison_iteration` uses the same configuration, so behaviour is consistent once wired.
- [ ] No other logic changes were introduced in these functions (e.g. status transitions, logging, or LLM override handling).

### 6.4 CJ service – `cj_core_logic/pair_generation.py`

- [ ] No behavioural changes were made in this PR (only call sites were updated), keeping risk low.
- [ ] Logging still reports the number of generated tasks and existing pairs as before.

### 6.5 Configuration – `config.py`

- [ ] `COMPARISONS_PER_STABILITY_CHECK_ITERATION` and `MAX_PAIRWISE_COMPARISONS` remain defined with the intended defaults (10 and 1000 respectively).
- [ ] No unrelated configuration values were changed.

### 6.6 End-to-end validation (ENG5 flow)

- [ ] With DB anchors configured and registration succeeding:
  - [ ] CJ batch contains all DB anchors for the assignment/grade scale.
  - [ ] Student essays from the ENG5 runner appear in `essays_to_process` and in CJ’s processed essay table.
- [ ] With `COMPARISONS_PER_STABILITY_CHECK_ITERATION` set to a higher value (e.g. 20):
  - [ ] `generate_comparison_tasks` is called with `existing_pairs_threshold=20`.
  - [ ] More than 5 comparisons are submitted for the batch when enough essays exist.
- [ ] Grade projections are produced for ENG5 batches when anchor coverage and comparison counts are sufficient (as observed via `inspect_batch_state` and result events).

---

This PR/diff doc should live alongside `ENG5_CJ_ANCHOR_COMPARISON_FLOW.md` in `.claude/tasks` and be referenced from the actual PR description. It captures the intended behavioural changes, the exact files to inspect, and the key review checkpoints for ENG5 runner ↔ CJ Assessment Service alignment.
