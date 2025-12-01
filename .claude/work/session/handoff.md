# HANDOFF: Current Session Context

## Purpose

This document contains ONLY current/next-session work. All completed tasks,
architectural decisions, and patterns live in:

- **README_FIRST.md** – Architectural overview, decisions, service status
- **Service READMEs** – Service-specific patterns, error handling, testing
- **.claude/rules/** – Implementation standards and requirements
- **docs/operations/** – Operational runbooks
- **TASKS/** – Detailed task documentation

Use this file to coordinate what the very next agent should focus on.

---

## 🎯 ACTIVE WORK (2025-12-01)

- ENG5 GPT‑5.1 runner wiring + experiments:
  - Tasks:
    - `TASKS/programs/eng5-gpt-51-reasoning-effort-alignment-experiment.md`
    - `TASKS/programs/eng5/eng5-runner-assumption-hardening.md`
  - Entry points:
    - `scripts/cj_experiments_runners/eng5_np/cli.py` (ANCHOR_ALIGN_TEST mode, GPT‑5.1 flags + overrides)
    - `scripts/cj_experiments_runners/eng5_np/handlers/anchor_align_handler.py`
  - Focus:
    - Follow up on CJ/LLM Provider metadata so `AssessmentResultV1.model_used` / `model_provider` reflect `openai` / `gpt-5.1` when ENG5 overrides are set (today, callbacks are GPT‑5.1 but CJ still reports Anthropic Haiku).
    - Plan and (in a later session) run the deferred `reasoning_effort="high"` GPT‑5.1 anchor-align experiment once metadata semantics and cost/latency guardrails are agreed.
    - Use the new DB-based diagnostic reports for cj_batch_id 137–139 as the primary comparison surface for reasoning-effort analysis (Kendall’s tau, inversions, zero‑win anchors).

---

## ✅ COMPLETED (2025-12-01)

- LLM Provider OpenAI GPT‑5.x reasoning controls:
  - GPT‑5 family manifest entries normalized with shared capability/parameter flags and covered by `test_openai_manifest_gpt5_family.py`.
  - `OpenAIProviderImpl` updated to send `max_completion_tokens` (no `temperature`) and, for GPT‑5 family models, map `reasoning_effort` and `output_verbosity` into `reasoning` / `text` controls; validated via `test_openai_provider_gpt5_family.py`.
  - Orchestrator + queue plumbing now preserve reasoning/verbosity overrides through `LLMConfigOverridesHTTP` and into provider calls (`test_orchestrator_reasoning_overrides.py`).
  - CJ LLM client override adapter tested to confirm reasoning/verbosity fields flow from `LLMConfigOverrides` / request metadata into LLM Provider HTTP payloads.
- ENG5 GPT‑5.1 anchor-align runner wiring and experiments:
  - ENG5 NP runner CLI/settings now expose anchor-align specific flags (`--anchor-align-provider`, `--anchor-align-model`, `--anchor-align-reasoning-effort`, `--anchor-align-output-verbosity`) and record effective values on `RunnerSettings`, while preserving Anthropic Haiku/Sonnet + 003 prompts as the default configuration.
  - `AnchorAlignHandler` augments existing `llm_overrides` with 003 system/rubric prompt text while preserving provider/model/temperature/max_tokens and the new `reasoning_effort` / `output_verbosity` fields so they reach `ELS_CJAssessmentRequestV1.llm_config_overrides` and, via CJ/LPS, the OpenAI HTTP payloads.
  - Three GPT‑5.1 anchor-align runs completed with 003 prompts and `output_verbosity="medium"`:
    - `eng5-gpt51-none-20251201-142319` (cj_batch_id 137, BOS UUID `05c687fc-463d-4c2d-bcaa-73250d0830ca`)
    - `eng5-gpt51-low-20251201-142416` (cj_batch_id 138, BOS UUID `ddc3f259-b125-4a08-97fb-f4907fa50b3d`)
    - `eng5-gpt51-medium-20251201-142646` (cj_batch_id 139, BOS UUID `7c0dcd60-deeb-482a-ad7c-f851df09f454`)
  - LLM Provider comparison callbacks for these batches confirm `provider="openai"`, `model="gpt-5.1"`, and `request_metadata.resolved_model="gpt-5.1"`; CJ aggregate result events still report `model_used="claude-haiku-4-5-20251001"` / `model_provider="anthropic"`, which is logged as a CJ-side metadata bug rather than an ENG5 runner issue.
  - DB-based alignment reports (summary + full) have been generated for cj_batch_id 137–139 under `.claude/research/data/eng5_np_2016/anchor_align_db*_*.md`, providing complete comparison tables and justifications for reasoning-effort analysis.

## ✅ COMPLETED (2025-11-30)

- Recent CJ work (PR‑2, PR‑3, PR‑4, PR‑7, US‑00XY/US‑00XZ/US‑00YA/US‑00YB) is fully documented in:
  - Task files under `TASKS/assessment/` and `TASKS/phase3_cj_confidence/`.
  - CJ epics and ADRs under `docs/product/epics/` and `docs/decisions/`.
  - CJ service README and runbook:
    - `services/cj_assessment_service/README.md`
    - `docs/operations/cj-assessment-runbook.md`
- ENG5 anchor-only alignment experiment completed:
  - Mode: `anchor-align-test`
  - Configuration: Anthropic `claude-sonnet-4-5-20250929` + 003 language-control system/rubric prompts.
  - Report: `.claude/research/data/eng5_np_2016/anchor_align_eng5-language-control-sonnet45_20251130_235510.md`
- For historical context or design rationale, prefer those documents rather than this handoff.
