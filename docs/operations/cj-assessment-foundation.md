---
type: runbook
service: cj_assessment_service
severity: high
last_reviewed: 2025-11-21
---

# CJ Assessment & LLM Provider Foundation (Working Reference)

Purpose: single reference for defaults, reasoning, metrics, and open work across CJ Assessment, LLM Provider, ENG5 Runner, and API Gateway callers. Keep this in sync with handoff.md, readme_first.md, and relevant task docs under .claude/work/tasks/.

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
  - Metrics: `llm_provider_prompt_cache_events_total{result}`, `llm_provider_prompt_cache_tokens_total{direction}`.
  - PromQL: hit rate `sum(rate(llm_provider_prompt_cache_events_total{result="hit"}[5m])) / sum(rate(llm_provider_prompt_cache_events_total{result=~"hit|miss|bypass"}[5m]))`; tokens saved per second `sum(rate(llm_provider_prompt_cache_tokens_total{direction="read"}[5m]))`.
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

## Open work (align with .claude/work/tasks)
- PR2: Pair position fairness (balanced A/B for anchors/students).
- PR3: Extend Anthropic tests to 529 + stop_reason; add PromQL snippets for error_type and cache hit rate.
- PR4: Queue/orphan hygiene (timeouts for PROCESSING, orphan callback detection + metrics).
- Remove BatchMonitor 80% heuristic after timeout-only bake.
- Prompt segmentation: split cacheable static blocks (system, tool schema, rubric/instructions) from dynamic essay blocks; add hit/miss + tokens-saved metrics.

## Assignment vs no-assignment behavior
- With assignment_id: hydrate prompt/rubric/anchors; grade projections enabled; cached prompts encouraged.
- Without assignment_id: rankings only; projections off; shorter cache TTL recommended.

## Owners/rollout (solo-friendly)
- Defaults above are starting points; adjust per experiment results. Keep flags: iterative/serial_bundle and prompt cache TTL overridable per env.

Update guidance: treat this doc like handoff/readme_first—update whenever behavior, defaults, or metrics change in CJ, LLM Provider, ENG5 Runner, or API Gateway integration.

## Related references
- .claude/work/session/handoff.md (current session context)
- .claude/work/session/readme-first.md (service status snapshot)
- Tasks: key trackers aligned to this doc:
  - .claude/work/tasks/TASK-CJ-LLM-SERIAL-BUNDLE-VALIDATION-FIXES.md
  - .claude/work/tasks/TASK-CJ-BATCH-STATE-AND-COMPLETION-FIXES.md
  - .claude/work/tasks/TASK-LLM-BATCH-STRATEGY-IMPLEMENTATION.md (+ checklist child)
  - .claude/work/tasks/TASK-LLM-BATCH-STRATEGY-LPS-IMPLEMENTATION.md
  - .claude/work/tasks/TASK-LLM-SERIAL-BUNDLE-METRICS-AND-DIAGNOSTICS-FIX.md
  - .claude/work/tasks/TASK-LLM-QUEUE-EXPIRY-METRICS-FIX.md
