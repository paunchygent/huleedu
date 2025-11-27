---
type: runbook
service: cj_assessment_service
severity: high
last_reviewed: 2025-11-27
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
| SCORE_STABILITY_THRESHOLD | 0.025 (start) | Force higher agreement before stopping; early experiments should map cost vs convergence. | Sweep with ENG5 Runner across 0.025–0.05 per exam; pick per-assignment default. |
| MIN_COMPARISONS_FOR_STABILITY_CHECK | = COMPARISONS_PER_STABILITY_CHECK_ITERATION (floor 8) | Check stability once each “round” finishes; BT is cheap, so prefer more frequent checks. | Keep tied to round size; revisit if iterations grow large. |
| COMPARISONS_PER_STABILITY_CHECK_ITERATION | existing env default | Defines round size; also drives MIN_COMPARISONS_FOR_STABILITY_CHECK. | Adjust per dataset size to balance turnaround vs stability. |
| completion_denominator | min(total_budget or total_comparisons, nC2(expected_essay_count)) | Small batches finalize promptly; cap prevents 6-pair batches from waiting on 350-budget. | Keep; verify nC2 source from batch_upload.expected_essay_count. |
| BatchMonitor timeout_hours | prod: 4h; dev: 1h | Recovery-only safety net; generous for prod, tight for dev. | Remove 80% heuristic; keep timeout-only once validated. |
| PROMPT_CACHE_TTL_SECONDS | ad-hoc/dev: 300–600s; assignment_id/batch: 3600s | Short TTL for rapid iteration; longer for stable, repeated prompts in batch runs. | Raise to 4–6h if cache hit rate is high and safety acceptable. |
| ENABLE_PROMPT_CACHING | true for assignment_id/batch; optional for ad-hoc | Reduce cost on repeated static context; avoid surprises in highly dynamic prompts. | Keep on for curated exams; monitor hits/misses. |
| stop_reason handling | error on max_tokens | Prevent silent truncation. | Keep; add tests for stop_reason and 529. |
| Retry behavior (Anthropic) | 429 respects Retry-After (bounded); 529/5xx retryable | Align with provider guidance. | Monitor error_type metrics and adjust backoff as needed. |

## How completion now works (callback-first)
1) LLM requests are async; callbacks update completed/failed counters and last_activity_at.
2) Continuation triggers only when callbacks_received == submitted_comparisons for the current wave.
3) On trigger: recompute BT scores; persist bt_scores/last_score_change; stop if stability or denominator/budget cap reached; else enqueue next wave if budget remains.
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
- Scope: `cj_core_logic/comparison_processing.py` (wave size surfaced via settings), `workflow_continuation.py` (stability/budget check after each wave), new setting (e.g., `MAX_BUNDLES_PER_WAVE`) wired through DI.
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
- Defaults above are starting points; adjust per experiment results. Keep flags: iterative/serial_bundle and prompt cache TTL overridable per env.

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
