---
id: 'eng5-gpt-51-reasoning-effort-alignment-experiment'
title: 'ENG5 GPT-5.1 Reasoning Effort Alignment Experiment'
type: 'task'
status: 'research'
priority: 'medium'
domain: 'programs'
service: 'eng5_runner'
owner_team: 'agents'
owner: ''
program: 'eng5'
created: '2025-12-01'
last_updated: '2025-12-01'
related: ['EPIC-008', 'llm-provider-openai-gpt-5x-reasoning-controls']
labels: ['eng5', 'alignment', 'gpt5']
---
# ENG5 GPT-5.1 Reasoning Effort Alignment Experiment

## Objective

Design and run an ENG5 anchor‑alignment experiment that uses OpenAI GPT‑5.1
with different reasoning effort levels (`none`, `low`, `medium`, `high`) and
compares alignment reports against expert anchors and existing Anthropic
configurations.

## Context

- ENG5 anchor alignment work (EPIC‑008) currently focuses on Anthropic
  Sonnet/Haiku models; we want to understand how GPT‑5.1 behaves on the same
  anchor set.
- GPT‑5.1 introduces reasoning‑specific controls (effort, verbosity) instead
  of traditional sampling parameters; we need a controlled experiment to see
  how these settings impact ENG5 alignment metrics (Kendall’s tau, inversions,
  zero‑win anchors).
- The LLM Provider Service will expose GPT‑5.x reasoning controls; ENG5
  runner should provide a concrete, reproducible example that uses those
  controls end‑to‑end.

## Plan

1. Define how GPT‑5.1 is selected for ENG5 runs:
   - Use LLM Provider overrides (`provider_override=openai`,
     `model_override='gpt-5.1'`) for `ANCHOR_ALIGN_TEST` mode.
2. Add ENG5 runner wiring and tests:
   - Extend ENG5 runner settings/CLI so `llm_config_overrides` can carry
     optional `reasoning_effort` hints for GPT‑5.1 runs.
   - Add at least one CLI integration test that exercises GPT‑5.1 +
     reasoning overrides in `anchor-align-test` mode.
3. Run anchor‑only ENG5 batches with:
   - Baseline: Anthropic Sonnet 4.5 (current config).
   - GPT‑5.1 with `reasoning_effort=none` (closest to non‑reasoning models).
   - GPT‑5.1 with `reasoning_effort=low`, `medium`, `high`.
4. For each configuration, generate:
   - Runner alignment report.
   - DB‑backed full diagnostic report (`db_alignment_report`) including all
     comparisons and justifications.
5. Compare metrics across configurations:
   - Kendall’s tau vs expert grades.
   - Direct inversions, with focus on boundary anchors (C+/B, F+/E‑, etc.).
   - Zero‑win anchors and stability across repeats.
6. Document findings and recommended follow‑ups:
   - Summarize in this task and in EPIC‑008 notes.
   - Identify whether GPT‑5.1 is a viable alternative or complementary model
     for ENG5 prompt tuning.

## Success Criteria

- At least one complete ENG5 anchor‑alignment experiment using GPT‑5.1 is
  run for each reasoning effort level (`none`, `low`, `medium`, `high`).
- For each configuration, both runner and DB‑backed alignment reports are
  produced and archived under `.claude/research/data/eng5_np_2016/`.
- A short comparative analysis is written covering:
  - Differences in Kendall’s tau and inversion patterns vs Anthropic
    baseline.
  - How reasoning effort affects boundary behavior and justifications.
  - Any surprising behavior or clear preference for a given effort level.
- This task links back to EPIC‑008 with a summary of outcomes and any
  recommended changes to ENG5 default LLM settings or prompt design.

## Progress (2025-12-01)

- LLM Provider Service now fully supports GPT‑5.x reasoning controls: GPT‑5 family manifest entries are locked, `OpenAIProviderImpl` maps `reasoning_effort` / `output_verbosity` into `reasoning` / `text` payload fields for GPT‑5 models, and the orchestrator passes these overrides through queue processing.
- CJ Assessment’s LLM client (`llm_provider_service_client.py`) can emit `reasoning_effort` and `output_verbosity` in HTTP `llm_config_overrides`, with unit tests covering override adaptation from CJ event models and request metadata.
- ENG5 runner can treat GPT‑5.1 + reasoning effort as a pure configuration concern once CLI/settings wiring is added: the downstream LLM Provider + CJ plumbing is ready for `ANCHOR_ALIGN_TEST` experiments using `provider_override=openai`, `model_override='gpt-5.1'`, and reasoning effort/verbosity hints.
- ENG5 NP runner CLI/settings have been extended for `ANCHOR_ALIGN_TEST` to support:
  - Anchor-align specific flags: `--anchor-align-provider`, `--anchor-align-model`, `--anchor-align-reasoning-effort`, and `--anchor-align-output-verbosity` (Anthropic Haiku/Sonnet with 003 prompts remain the default; GPT‑5.1 is opt‑in).
  - `RunnerSettings` fields recording effective anchor-align provider/model and reasoning/verbosity values, plus propagation into `LLMConfigOverrides.reasoning_effort` / `output_verbosity`.
  - `AnchorAlignHandler` now preserves provider/model/temperature/max_tokens **and** reasoning/verbosity when layering the 003 language-control system prompt and rubric into `llm_overrides`.
- GPT‑5.1 anchor-align experiments have been run with 003 system/rubric prompts and reasoning_effort ∈ {`none`, `low`, `medium`} (all with `output_verbosity="medium"`):
  - Baseline GPT‑5.1 (none): batch label `eng5-gpt51-none-20251201-142319`, BOS batch UUID `05c687fc-463d-4c2d-bcaa-73250d0830ca`, CJ batch_id `137`.
    - Runner report: `.claude/research/data/eng5_np_2016/anchor_align_eng5-gpt51-none-20251201-142319_20251201_132411.md`
    - DB-based full diagnostic report (all comparisons + justifications): `.claude/research/data/eng5_np_2016/anchor_align_db_full_05c687fc-463d-4c2d-bcaa-73250d0830ca_20251201_133345.md`
  - GPT‑5.1 (low): batch label `eng5-gpt51-low-20251201-142416`, BOS batch UUID `ddc3f259-b125-4a08-97fb-f4907fa50b3d`, CJ batch_id `138`.
    - Runner report: `.claude/research/data/eng5_np_2016/anchor_align_eng5-gpt51-low-20251201-142416_20251201_132640.md`
    - DB-based full diagnostic report: `.claude/research/data/eng5_np_2016/anchor_align_db_full_ddc3f259-b125-4a08-97fb-f4907fa50b3d_20251201_133351.md`
  - GPT‑5.1 (medium): batch label `eng5-gpt51-medium-20251201-142646`, BOS batch UUID `7c0dcd60-deeb-482a-ad7c-f851df09f454`, CJ batch_id `139`.
    - Runner report: `.claude/research/data/eng5_np_2016/anchor_align_eng5-gpt51-medium-20251201-142646_20251201_132921.md`
    - DB-based full diagnostic report: `.claude/research/data/eng5_np_2016/anchor_align_db_full_7c0dcd60-deeb-482a-ad7c-f851df09f454_20251201_133358.md`
- LLM Provider comparison callbacks for these runs confirm `provider="openai"` and `model="gpt-5.1"` (with `request_metadata.resolved_provider="openai"` / `resolved_model="gpt-5.1"`), but CJ’s aggregate `AssessmentResultV1` metadata still reports `model_used="claude-haiku-4-5-20251001"`, `model_provider="anthropic"` for the corresponding CJ batches (137–139). This mismatch is **logged as a follow-up** for CJ/LLM Provider service tasks; ENG5 wiring and experiments treat GPT‑5.1 as the actual judge model based on callback payloads.
- `reasoning_effort="high"` is **explicitly deferred** to a later session once:
  - CJ result metadata accurately reflects non‑Anthropic providers/models, and
  - any additional cost/latency constraints for high-effort GPT‑5.1 are agreed with infra/ops.

### Follow-up Checklist – CJ Metadata Attribution (Infra/Assessment)

- [ ] **Trace current attribution**: Identify the exact code path in CJ Assessment that sets `AssessmentResultV1.model_used` and `model_provider` (likely where CJ aggregates LLM comparison results into the rich result event).
- [ ] **Source of truth decision**: Decide on the canonical source for model/provider attribution for CJ batches (recommended: LLM Provider callback metadata, e.g., `resolved_provider` / `resolved_model` from `LLMComparisonResultV1`).
- [ ] **Update attribution logic**: Change CJ to populate `model_used` / `model_provider` from the agreed source for all providers (Anthropic, OpenAI GPT‑5.x, and future models), ensuring ENG5 guest batches (anchor-align-test) are covered.
- [ ] **Add regression tests**: Extend CJ/LLM Provider integration tests so that:
  - A CJ batch driven by Anthropic Sonnet/Haiku reports `model_used=<claude-*>`, `model_provider="anthropic"`.
  - A CJ batch driven by GPT‑5.1 via ENG5 overrides reports `model_used="gpt-5.1"`, `model_provider="openai"`.
- [ ] **Revalidate ENG5 GPT‑5.1 runs**: After the fix, run a small GPT‑5.1 anchor-align batch and confirm:
  - LLM Provider callbacks still show `openai` / `gpt-5.1`.
  - The corresponding `AssessmentResultV1` event now matches that attribution.

## Related

- Epic: `docs/product/epics/eng5-runner-refactor-and-prompt-tuning-epic.md` (EPIC‑008)
- Task: `TASKS/infrastructure/llm-provider-openai-gpt-5x-reasoning-controls.md`
- ENG5 runner: `scripts/cj_experiments_runners/eng5_np`
