# ENG5 NP Runner ↔ CJ Assessment Service – Anchor & Comparison Flow Mapping

Parent/overview doc for ENG5 CJ anchor behaviour and comparison limits.

Child PR/diff doc: `ENG5_CJ_ANCHOR_COMPARISON_FLOW_PR_AND_DIFF.md`.

---

## 1. Scope and goals

- **Runner:** `scripts/cj_experiments_runners/eng5_np/*`
  - `cli.py` – CLI entrypoint, execute mode, anchor registration, content upload.
  - `inventory.py` – file inventory, `apply_comparison_limit`, `build_essay_refs`.
  - `requests.py` – `compose_cj_assessment_request`, `write_cj_request_envelope`.
  - `kafka_flow.py` – publishing CJ request, capturing completion/result events.

- **CJ Assessment Service:** `services/cj_assessment_service/*`
  - `event_processor.py` – consumes `ELS_CJAssessmentRequestV1`, triggers workflow.
  - `cj_core_logic/batch_preparation.py` – creates CJ batch, fetches students, adds anchors.
  - `cj_core_logic/comparison_processing.py` – generates and submits comparison tasks.
  - `cj_core_logic/pair_generation.py` – pair generation with `existing_pairs_threshold` cap.
  - `cj_core_logic/workflow_continuation.py` – callback-driven continuation/finalisation.
  - `cj_core_logic/grade_projector.py` – BT scoring → grade projections using anchors.
  - `config.py` – comparison thresholds, iteration and projection configuration.

**Goal:**

- Map how **anchors** and **students** flow from ENG5 runner into CJ, how **comparison limits** are applied, and how this affects **Bradley–Terry scoring** and **grade projections**.
- Identify **exact locations** where behaviour should change in:
  - **1. Runner** – ensure anchors are treated as DB-owned, clarify `--max-comparisons`, harden failure modes.
  - **2. CJ service** – fix comparison threshold wiring, ensure sufficient comparisons for BT convergence.

---

## 2. End‑to‑end flow (ENG5 NP Runner ↔ CJ Assessment Service)

### 2.1 Runner: request composition and publishing

- **CLI entry (`cli.py:main`)**
  - Accepts `assignment_id`, `course_id`, `grade_scale`, `batch_id`, `user_id`, `org_id`, `course_code`, `language`.
  - Accepts flags:
    - `mode` (PLAN/DRY_RUN/EXECUTE).
    - `max_comparisons: int | None` – intended as comparison budget.
    - `cj_service_url` – used for anchor registration.
    - `content_service_url` – used to upload essays/prompt.
    - `await_completion` – whether to wait for CJ completion event.
  - Builds `RunnerSettings` with `max_comparisons`, `assignment_id`, `course_id`, `grade_scale`, `correlation_id`, etc.

- **Inventory and upload decisions (execute mode)**
  - For `RunnerMode.EXECUTE` @ `cli.py:544–618`:
    - Validates anchors + students exist and that `cj_service_url` is configured.
    - Attempts **anchor registration** with `register_anchor_essays(...)`.
    - Any registration error (or empty response) raises immediately—there is no fallback to uploading anchors.
    - On success only the student essays are uploaded via `upload_essays_parallel(records=students, ...)`.

- **Essay refs in request**
  - After upload:
    - If **anchor registration used**:
      - `essay_ref_anchors: list[FileRecord] = []`.
      - `essay_ref_students = limited_students`.
    - Else (ephemeral anchors path):
      - `essay_ref_anchors = limited_anchors`.
      - `essay_ref_students = limited_students`.
  - `build_essay_refs(anchors=essay_ref_anchors, students=essay_ref_students, max_comparisons=None, storage_id_map)`:
    - Internally calls `apply_comparison_limit` again when `max_comparisons` is not `None`.
    - Converts `FileRecord`s into `EssayProcessingInputRefV1` using checksums → Content Service storage IDs.
  - `compose_cj_assessment_request(settings, essay_refs, prompt_reference)`:
    - Packs `essay_refs` into `ELS_CJAssessmentRequestV1.essays_to_process`.
    - Includes `assignment_id`, `grade_scale`, `bos_batch_id`, identity metadata, and `llm_config_overrides`.
  - `write_cj_request_envelope(...)` writes the envelope; then `publish_envelope_to_kafka` or `run_publish_and_capture` sends it to topic `ELS_CJ_ASSESSMENT_REQUESTED`.

### 2.2 CJ service: request consumption and batch creation

- **Event consumption (`event_processor.py`)**
  - Kafka consumer deserialises `EventEnvelope[ELS_CJAssessmentRequestV1]`.
  - Builds internal `request_data` dict containing:
    - `bos_batch_id`, `assignment_id`, `essays_to_process`, `grade_scale`, `course_code`, identity fields, `llm_config_overrides`, optional prompt/rubric text and storage IDs.
  - Calls workflow orchestration:
    - `run_cj_assessment_workflow(request_data, correlation_id)`.

- **Batch creation (`batch_preparation.create_cj_batch`)**
  - Validates `bos_batch_id` and `essays_to_process`.
  - Creates `CJBatchUpload` with:
    - `bos_batch_id`, `event_correlation_id`, `language`, `course_code`, `expected_essay_count=len(essays_to_process)`, `user_id`, `org_id`.
  - If `assignment_id` is present:
    - Fetches `AssessmentInstruction` (grade_scale, prompt/rubric references).
    - Optionally backfills missing `student_prompt_storage_id` / `judge_rubric_storage_id` into batch metadata via Content Service.
    - Stores `assignment_id` on the batch.

### 2.3 CJ service: essay prep (students + DB-backed anchors)

- **Student essays (`prepare_essays_for_assessment`)**
  - Iterates `request_data["essays_to_process"]`:
    - For each entry with `els_essay_id` and `text_storage_id`:
      - Fetches content via `content_client.fetch_content(text_storage_id, correlation_id)`.
      - Stores `CJProcessedEssay` with `processing_metadata={"is_anchor": False}`.
      - Builds `EssayForComparison(id=els_essay_id, text_content=..., current_bt_score)` and adds it to `essays_for_api_model`.

- **Anchor essays (`_fetch_and_add_anchors`)**
  - Looks up the batch by `cj_batch_id` and reads `assignment_id`.
  - Uses `database.get_assignment_context(session, assignment_id)` to obtain `grade_scale` and other metadata.
  - Fetches `AnchorEssayReference` rows with `database.get_anchor_essay_references(assignment_id, grade_scale=grade_scale)`.
  - For each anchor ref:
    - Fetches anchor content from Content Service using `ref.text_storage_id`.
    - Stores `CJProcessedEssay` with `processing_metadata={"is_anchor": True, "known_grade": ref.grade, "anchor_ref_id": str(ref.id)}`.
    - Builds `EssayForComparison` with synthetic `id = f"ANCHOR_{ref.id}_{uuid4().hex[:8]}"` and `current_bt_score=0.0`.
    - Appends anchors to `essays_for_api_model`.

**Important:** when anchor registration succeeds and the assignment is configured, **all anchors used by CJ come exclusively from DB (`AnchorEssayReference`)**, not from the runner’s request body.

### 2.4 CJ service: pair generation and comparison submission

- **submit_comparisons_for_async_processing**
  - Updates batch status to `PERFORMING_COMPARISONS`.
  - Calls `pair_generation.generate_comparison_tasks` with:
    - `essays_for_comparison=essays_for_api_model` (students + DB anchors).
    - `existing_pairs_threshold=getattr(settings, "comparisons_per_stability_check_iteration", 5)`.
  - If no tasks are generated, logs and returns.
  - Otherwise, creates `BatchProcessor` and calls `submit_comparison_batch` to send LLM requests and move the batch to `WAITING_CALLBACKS`.

- **generate_comparison_tasks**
  - Fetches existing pairs for the batch via `_fetch_existing_comparison_ids` and normalises `(essay_a_els_id, essay_b_els_id)`.
  - Loops over all unordered pairs `(i, j)`:
    - Skips if pair already exists.
    - Stops generating new pairs when `new_pairs_count >= existing_pairs_threshold`.
  - Each new pair:
    - Incorporates assessment instructions and student prompt text into the prompt.
    - Returns a `ComparisonTask` for LLM.

- **Iteration helper `_process_comparison_iteration`**
  - Mirrors the above: calls `generate_comparison_tasks` with the same `existing_pairs_threshold` expression.
  - Submits another batch of comparisons.
  - Intended to be called from `workflow_continuation`, but currently not wired in the continuation path.

### 2.5 Callbacks, continuation, and grade projection

- LLM callback events drive `batch_callback_handler` and `workflow_continuation`:
  - Comparisons are persisted, BT scores updated, batch status transitions to `COMPLETE_STABLE` when thresholds are met.
- `grade_projector` uses:
  - Final BT scores for students and anchors.
  - Anchor grades from DB and the configured `GradeScaleMetadata`.
  - Isotonic regression and priors to map BT scores → grade probabilities → projected grades.
- Dual events are published:
  - `CJ_ASSESSMENT_COMPLETED` (thin completion event).
  - `ASSESSMENT_RESULT_PUBLISHED` (rich result event with rankings and projections).
- ENG5 runner’s `AssessmentEventCollector` consumes completion and result events and updates its local hydrator.

---

## 3. Current behaviour – anchors, students, and comparison limits

### 3.1 Runner behaviour

- **Happy path (anchor registration succeeds)**
  - EXECUTE mode validates that anchors exist and that `cj_service_url` is provided.
  - `register_anchor_essays` is invoked and must succeed; otherwise the runner raises immediately.
  - After registration success:
    - Only student essays are uploaded to Content Service (`essay_ref_anchors` remains empty).
    - `build_essay_refs` receives `max_comparisons=None`, so all students are referenced.
    - `essays_to_process` in the CJ event contains **only students**; anchors are always loaded server-side.

- **Failure path**
  - If registration fails or the CJ URL/admin token is missing, the runner aborts—there is no longer a fallback where anchors are uploaded inline.

- **`--max-comparisons` semantics**
  - CLI help still advertises the flag for cost control, but the runner now treats it strictly as metadata.
  - `max_comparisons` is logged and added to the CJ event envelope (`metadata["max_comparisons"]`), allowing the service (or downstream automation) to decide how to enforce the budget.
  - EXECUTE mode never slices essays locally; all comparison density decisions happen inside CJ via configuration.

### 3.2 CJ service behaviour

- **Anchors are DB-owned**
  - `prepare_essays_for_assessment` always marks request essays as `is_anchor=False`.
  - Anchors are discovered exclusively via `assignment_id` and the anchor tables.
  - Synthetic IDs (`ANCHOR_...`) are used for anchors; real student IDs are preserved for students.

- **Comparison thresholds and caps**
  - `generate_comparison_tasks` accepts both a per-call `existing_pairs_threshold` and an optional `max_pairwise_comparisons`.
  - `submit_comparisons_for_async_processing` and `_process_comparison_iteration` now pass `settings.COMPARISONS_PER_STABILITY_CHECK_ITERATION` (default 10) and `settings.MAX_PAIRWISE_COMPARISONS` (default 1000) directly.
  - The generator enforces:
    - No more than `existing_pairs_threshold` new pairs per invocation.
    - A global guard clause that returns `[]` once `existing_count >= max_pairwise_comparisons`.

- **Iteration and stability loop**
  - `_process_comparison_iteration` exists as a helper to schedule additional comparisons.
  - `workflow_continuation` currently only:
    - Checks completion status.
    - Optionally handles retries.
    - Then finalises the batch and triggers grade projection.
  - There is **no active loop** that keeps requesting more comparisons until BT scores stabilise.

- **Grade projection expectations**
  - `grade_projector` expects:
    - Enough comparisons for a connected comparison graph.
    - Multiple anchors across the grade scale.
  - With only a handful of comparisons (e.g. 5) and many essays, BT scores are noisy and projections may not be meaningful or may be deferred.

---

## 4. Issues and gaps

1. **Comparison cap miswired in CJ (resolved):**
   - Earlier builds used `getattr(settings, "comparisons_per_stability_check_iteration", 5)` and ignored the canonical setting; this has now been corrected to reference `Settings.COMPARISONS_PER_STABILITY_CHECK_ITERATION` directly.
   - Pair generation also enforces `Settings.MAX_PAIRWISE_COMPARISONS`, preventing uncontrolled growth.

2. **No iterative BT convergence loop:**
   - `_process_comparison_iteration` is not invoked from `workflow_continuation`.
   - Once the initial 5 comparisons are submitted and callbacks processed, the batch is effectively done; no further pairs are generated to improve BT scores.

3. **Ephemeral anchors fallback undermines "DB-only anchors" principle (resolved):**
   - ENG5 runner now fails fast on anchor registration errors or missing `CJ_SERVICE_URL`, ensuring every EXECUTE run uses DB-owned anchors exclusively.

4. **`--max-comparisons` semantics have drifted (resolved):**
   - The runner no longer slices essays locally. The flag is logged and forwarded as metadata so CJ can interpret it alongside `COMPARISONS_PER_STABILITY_CHECK_ITERATION` / `MAX_PAIRWISE_COMPARISONS`.

5. **Global comparison caps unused (resolved):**
   - `Settings.MAX_PAIRWISE_COMPARISONS` is now passed into `pair_generation.generate_comparison_tasks`, which halts generation when the cap is reached.

---

## 5. Desired behaviour (target state)

### 5.1 Anchors

- **Single source of truth:**
  - Anchors for CJ must come exclusively from CJ DB (`AnchorEssayReference` linked to `assignment_id` / `grade_scale`).
- **No anchor limiting in the runner:**
  - Runner should never "chop" anchors when registration is configured and expected.
  - If anchor registration fails, the default for ENG5 should be to **fail fast**, not silently fall back to ephemeral anchors.

### 5.2 Comparisons and BT scoring

- **Configurable comparisons per iteration:**
  - `COMPARISONS_PER_STABILITY_CHECK_ITERATION` should control `existing_pairs_threshold` for pair generation.
  - ENG5 research runs should be able to raise this via env (e.g. 20–50) without code changes.

- **Optional per-run overrides:**
  - Longer term, `ELS_CJAssessmentRequestV1` may carry batch-specific overrides (e.g., comparisons per iteration, max iterations), passed through `request_data["batch_config_overrides"]`.

- **Iterative BT loop (future enhancement, not necessarily in first PR):**
  - On each callback wave, `workflow_continuation` should:
    - Evaluate score stability and comparison graph coverage.
    - If not stable and under global caps, call into `_process_comparison_iteration` to request more pairs.
    - Only finalise when convergence or hard limits are reached.

### 5.3 Runner semantics

- **Anchor registration failure handling:**
  - Default and only behaviour: treat any anchor registration failure as a hard error for ENG5 `EXECUTE` mode.
  - Do not fall back to ephemeral anchors; the ENG5 runner requires CJ anchor registration to succeed before publishing a request.

- **`--max-comparisons` ownership:**
  - The runner should not implement its own comparison-limiting logic.
  - If `max_comparisons` is set, model it as a CJ override (for example via a batch-level config field in the event) and interpret it inside CJ's BT convergence logic rather than via `apply_comparison_limit` in the runner. (Implemented: metadata now carries `max_comparisons` while EXECUTE mode uploads all essays.)

---

## 6. Planned changes (high-level), by component

### 6.1 Runner (ENG5 NP)

Focus: enforce DB-owned anchors, remove runner-level comparison limiting, and improve failure semantics.

- **`cli.py`**
  - After `register_anchor_essays`:
    - If registration fails for any reason, abort `EXECUTE` mode with a clear error; do not fall back to ephemeral anchors.
    - Keep current behaviour that, on success, only student essays are uploaded; anchors are always provided by CJ DB.
  - If `cj_service_url` is missing while anchors are present, treat this as a configuration error and abort rather than running with anchors but no registration.

- **`inventory.py`**
  - Remove `apply_comparison_limit` from the ENG5 `EXECUTE` path so the runner no longer slices anchors or students to approximate a comparison budget. (Done.)
  - Allow CJ to be the single source of truth for comparison density (`COMPARISONS_PER_STABILITY_CHECK_ITERATION`, `MAX_PAIRWISE_COMPARISONS`).
  - Any future `max_comparisons` behaviour in the runner should be expressed as a CJ override (for example via an event-level batch config), not as local slicing.

- **`requests.py`**
  - No structural changes are required for anchor semantics; continue to send only students in `essays_to_process` when registration is used.
  - Future extension: allow embedding `batch_config_overrides` in the event to control CJ comparison density per run.

### 6.2 CJ Assessment Service

Focus: fix comparison threshold wiring, prepare for more robust BT convergence, and guard against pathological loads.

- **`config.py`**
  - `COMPARISONS_PER_STABILITY_CHECK_ITERATION` remains the source of truth for per-iteration generation cap.
  - `MAX_PAIRWISE_COMPARISONS` remains a global upper bound for all pairs in a batch.

- **`comparison_processing.py`**
  - In `submit_comparisons_for_async_processing` and `_process_comparison_iteration`:
    - Use `settings.COMPARISONS_PER_STABILITY_CHECK_ITERATION` directly (or a robust accessor) instead of `getattr(..., "comparisons_per_stability_check_iteration", 5)`.
  - Optionally:
    - Accept batch-level overrides via `BatchConfigOverrides` populated from `request_data["batch_config_overrides"]`.

- **`pair_generation.py`**
  - Keep `existing_pairs_threshold` as per-call cap, but:
    - Consider adding an optional `max_pairwise_comparisons` input and respecting the global `MAX_PAIRWISE_COMPARISONS` value.
    - Use `min(existing_pairs_threshold, remaining_pairs_until_global_cap)` when deciding when to stop.

- **`workflow_continuation.py`** (later iteration)
  - Wire it to call a public wrapper around `_process_comparison_iteration` so that CJ actually performs multiple comparison iterations until either stability thresholds are met or caps are reached.

- **`grade_projector.py`**
  - No code change in the initial PR, but behaviour depends heavily on:
    - Anchor coverage (number of anchors, grade diversity).
    - Number of comparisons and score stability.
  - The changes above should increase comparison counts and anchor utilisation, improving projection reliability.

---

## 7. Risks and open questions

- **BT convergence vs. cost:**
  - Raising `COMPARISONS_PER_STABILITY_CHECK_ITERATION` and wiring in iteration support will increase LLM cost per batch; need guardrails via `MAX_PAIRWISE_COMPARISONS` and potentially per-run overrides.

- **Anchor configuration correctness:**
  - Misconfigured `assignment_id`/`grade_scale` or missing anchors in DB will directly affect projections. The runner should not attempt to compensate by providing anchors itself; instead, CJ admin APIs should be used to correct configuration.

- **Runner flag semantics:**
  - EXECUTE now fails fast on anchor registration issues; ensure downstream users are aware that `CJ_SERVICE_URL`/admin auth are mandatory inputs and that there is no longer an "upload anchors inline" fallback.

- **Per-run overrides vs. service config:**
  - Allowing the runner to override comparison thresholds per run is powerful but risks fragmentation. A coherent policy (who is allowed to tune what, and where) is needed.

---

This parent doc captures the mapping and behaviour; see `ENG5_CJ_ANCHOR_COMPARISON_FLOW_PR_AND_DIFF.md` for the concrete PR description and diff-level review plan.
