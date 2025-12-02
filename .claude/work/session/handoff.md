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

- EPIC-007 US-007.3 COMPLETE - creation scripts added:
  - `scripts/docs_mgmt/new_doc.py` - creates runbooks, ADRs, epics (`pdm run new-doc`)
  - `scripts/claude_mgmt/new_rule.py` - creates rule files (`pdm run new-rule`)
  - All management scripts refactored to module pattern (no sys.path bootstrap)
  - PDM scripts run as `python -m scripts.*` for clean imports
  - DecisionFrontmatter.id pattern fixed to `^ADR-\d{4}$` for consistency with EpicFrontmatter
  - Next: US-007.4 (Indexing Scripts) or US-007.5 (Unified Validation)

  - ENG5 GPT‑5.1 usage/content parity experiments (006, reasoning_effort=\"low\") + LOWER5 tail-only loop:
      - Tasks:
        - `TASKS/programs/eng5-gpt-51-reasoning-effort-alignment-experiment.md`
        - `TASKS/programs/eng5/eng5-runner-assumption-hardening.md`
      - Entry points:
        - `scripts/cj_experiments_runners/eng5_np/cli.py` (ANCHOR_ALIGN_TEST mode, GPT‑5.1 flags + overrides)
        - `scripts/cj_experiments_runners/eng5_np/handlers/anchor_align_handler.py`
        - `scripts/cj_experiments_runners/eng5_np/paths.py` (ENG5_ANCHOR_DIR_OVERRIDE handling)
        - `scripts/cj_experiments_runners/eng5_np/db_alignment_report.py`
        - `docker-compose.eng5-lower5.override.yml` (CJ small‑net tuning for LOWER5)
      - Current focus: ENG5 LOWER5 tail alignment, GPT‑5.1 `reasoning_effort` in {`"low"`, `"none"`}, comparing usage guard 007 + 006 rubric vs 006/006 parity prompts, with DB-based reports as the canonical surface for tau/inversion/justification analysis.
      - Focus (next sessions):
        - Maintain a repeatable LOWER5 loop over the 5 weakest anchors (`D‑`, `E+`, `E‑`, `F+`, `F+`) using:
          - CJ override: `docker-compose.eng5-lower5.override.yml` (20-comparison budget, no early stability stop, small‑net resampling cap=1).
          - ENG5 runner LOWER5 wiring: `ENG5_ANCHOR_DIR_OVERRIDE` → `/app/test_uploads/ANCHOR ESSAYS/ROLE_MODELS_ENG5_NP_2016/anchor_essays_5_lowest_grades`.
          - Prompts: system `007_usage_guard.txt`, rubric `006_usage_content_parity_rubric.txt`.
          - Model: `openai` / `gpt-5.1`, `reasoning_effort=\"low\"`, `output_verbosity=\"low\"`.
        - After each run, generate DB-based LOWER5 reports via `scripts.cj_experiments_runners/eng5_np/db_alignment_report.py` with `--system-prompt-file 007_usage_guard.txt` and `--rubric-file 006_usage_content_parity_rubric.txt`, and capture:
          - Kendall’s tau over the 5‑essay ladder.
          - Direct inversions among {D‑, E+, E‑, F+, F+}.
          - Justification patterns, especially for “wrong” tail picks.
        - Keep `TASKS/programs/eng5-gpt-51-reasoning-effort-alignment-experiment.md` updated with:
          - The canonical LOWER5 loop command.
          - Paths to the latest LOWER5 DB reports.
          - Notes on tail behaviour changes across runs (e.g. if usage guard tightens or loosens preference bias at F+/E‑ boundary).
        - Latest LOWER5 runs (2025-12-01, GPT‑5.1 low/low and none/low):
          - 007 system + 006 rubric (usage guard + parity rubric):
          - Runner batch: `batch_id=eng5-gpt51-lower5-007-20251202-001714`, `batch_uuid=50f4509e-2e8c-4c62-a19d-93cf0739eefd`, `cj_batch_id=147`.
          - DB-based reports:
            - Summary: `.claude/research/data/eng5_np_2016/anchor_align_db_50f4509e-2e8c-4c62-a19d-93cf0739eefd_20251201_231822.md`
            - Full: `.claude/research/data/eng5_np_2016/anchor_align_db_full_50f4509e-2e8c-4c62-a19d-93cf0739eefd_20251201_231822.md`
          - Metrics: Kendall’s tau `= 1.000` over the 5‑essay ladder (`D‑ > E+ > E‑ > F+ > F+`), `0` direct inversions, and one zero‑win F+ anchor; CJ small‑net overrides yielded exactly 10 comparisons (full LOWER5 pair coverage).
          - Justification patterns: winners consistently described as having clearer structure, richer content, and fewer basic errors; no tail inversions (no F+ beating D‑/E±), suggesting usage guard 007 is not inducing pathological tail behaviour under LOWER5.
          - 006 system + 006 rubric (pure usage/content parity pair):
            - Runner batch: `batch_id=eng5-gpt51-lower5-006-20251202-002205`, `batch_uuid=ec9c935c-e589-448c-b829-56ad545862f5`, `cj_batch_id=148`.
            - DB-based reports:
              - Summary: `.claude/research/data/eng5_np_2016/anchor_align_db_ec9c935c-e589-448c-b829-56ad545862f5_20251201_232251.md`
              - Full: `.claude/research/data/eng5_np_2016/anchor_align_db_full_ec9c935c-e589-448c-b829-56ad545862f5_20251201_232251.md`
            - Metrics: Kendall’s tau `= 0.800`, `1` direct inversion where F+ `ANCHOR_ESSAY_ENG_5_363940D5` beats higher‑graded E‑ `ANCHOR_ESSAY_ENG_5_73127661` (justification: “Clearer structure, richer content”); one zero‑win F+ anchor (`D298E687`), with D‑ and E+ still ranked 1–2.
            - Interpretation: relative to 007+006, the 006/006 pair slightly relaxes the tail floor, allowing a structurally/content‑strong F+ to overtake E‑ in one comparison while preserving the top of the ladder.
          - Additional LOWER5 runs with `reasoning_effort="none"`:
            - 007 system + 006 rubric:
              - Runner batch: `batch_id=eng5-gpt51-lower5-007-none-20251202-003112`, `batch_uuid=4ce7468b-bf15-46b8-8a97-ebe51f79d45f`, `cj_batch_id=149`.
              - DB-based reports: `.claude/research/data/eng5_np_2016/anchor_align_db_4ce7468b-bf15-46b8-8a97-ebe51f79d45f_20251201_233151.md` (summary) and `.claude/research/data/eng5_np_2016/anchor_align_db_full_4ce7468b-bf15-46b8-8a97-ebe51f79d45f_20251201_233151.md` (full).
              - Metrics: Kendall’s tau `= 0.800`, `1` direct inversion where F+ `ANCHOR_ESSAY_ENG_5_D298E687` beats E‑ `ANCHOR_ESSAY_ENG_5_73127661` (justification: clearer structure, fuller ideas, slightly better basic control), one zero‑win F+ anchor; D‑ and E+ remain 1–2.
            - 006 system + 006 rubric:
              - Runner batch: `batch_id=eng5-gpt51-lower5-006-none-20251202-003200`, `batch_uuid=8cb7d51a-abc9-486c-bc4f-3654c19da7e1`, `cj_batch_id=150`.
              - DB-based reports: `.claude/research/data/eng5_np_2016/anchor_align_db_8cb7d51a-abc9-486c-bc4f-3654c19da7e1_20251201_233241.md` (summary) and `.claude/research/data/eng5_np_2016/anchor_align_db_full_8cb7d51a-abc9-486c-bc4f-3654c19da7e1_20251201_233241.md` (full).
              - Metrics: Kendall’s tau `= 1.000`, `0` direct inversions, one zero‑win F+ anchor with ladder `D‑ > E+ > E‑ > F+ > F+`, mirroring the low/low 007+006 run.
          - Suggested next experiments:
            - Repeat LOWER5 for each (prompt, reasoning_effort) combination to estimate inversion frequency (especially F+/E‑ crossings) and stability.
            - Consider a small grid over `output_verbosity` or budget (within safety constraints) if PM wants to probe whether richer justifications correlate with safer tail alignment under 006/006.

---

## ✅ COMPLETED (2025-12-01)

- LLM Provider OpenAI GPT‑5.x reasoning controls:
  - GPT‑5 family manifest entries normalized with shared capability/parameter flags and covered by `test_openai_manifest_gpt5_family.py`.
  - `OpenAIProviderImpl` updated to send `max_completion_tokens` (no `temperature`) and, for GPT‑5 family models, map `reasoning_effort` and `output_verbosity` into `reasoning` / `text` controls; validated via `test_openai_provider_gpt5_family.py`.
  - Orchestrator + queue plumbing now preserve reasoning/verbosity overrides through `LLMConfigOverridesHTTP` and into provider calls (`test_orchestrator_reasoning_overrides.py`).
  - CJ LLM client override adapter tested to confirm reasoning/verbosity fields flow from `LLMConfigOverrides` / request metadata into LLM Provider HTTP payloads.
- ENG5 GPT‑5.1 anchor-align runner wiring and experiments (003 prompts):
  - ENG5 NP runner CLI/settings now expose anchor-align specific flags (`--anchor-align-provider`, `--anchor-align-model`, `--anchor-align-reasoning-effort`, `--anchor-align-output-verbosity`) and record effective values on `RunnerSettings`, while preserving Anthropic Haiku/Sonnet + 003 prompts as the default configuration.
  - `AnchorAlignHandler` augments existing `llm_overrides` with 003 system/rubric prompt text while preserving provider/model/temperature/max_tokens and the new `reasoning_effort` / `output_verbosity` fields so they reach `ELS_CJAssessmentRequestV1.llm_config_overrides` and, via CJ/LPS, the OpenAI HTTP payloads.
  - Three GPT‑5.1 anchor-align runs completed with 003 prompts and `output_verbosity="medium"`:
    - `eng5-gpt51-none-20251201-142319` (cj_batch_id 137, BOS UUID `05c687fc-463d-4c2d-bcaa-73250d0830ca`)
    - `eng5-gpt51-low-20251201-142416` (cj_batch_id 138, BOS UUID `ddc3f259-b125-4a08-97fb-f4907fa50b3d`)
    - `eng5-gpt51-medium-20251201-142646` (cj_batch_id 139, BOS UUID `7c0dcd60-deeb-482a-ad7c-f851df09f454`)
  - LLM Provider comparison callbacks for these batches confirm `provider="openai"`, `model="gpt-5.1"`, and `request_metadata.resolved_model="gpt-5.1"`; CJ now derives batch-level LLM attribution from `ComparisonPair.processing_metadata` so downstream `AssessmentResultV1` events can reflect OpenAI/GPT‑5.1 instead of legacy Anthropic defaults for these runs.
  - DB-based alignment reports (summary + full) have been generated for cj_batch_id 137–139 under `.claude/research/data/eng5_np_2016/anchor_align_db*_*.md`, providing complete comparison tables and justifications for reasoning-effort analysis. GPT‑5.1 `low` is the preferred reasoning setting for follow-up work, given comparable alignment and lower cost vs higher effort levels.

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
