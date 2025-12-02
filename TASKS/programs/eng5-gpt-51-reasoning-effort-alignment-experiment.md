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
last_updated: '2025-12-02'
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

## 2025-12-01 – CJ Attribution + GPT‑5.1 Low Canonical

- CJ now derives `AssessmentResultV1.model_used` / `model_provider` from
  comparison metadata (`ComparisonPair.processing_metadata["provider"]` /
  `["model"]`) via batch-level aggregation in `BatchFinalizer` and
  `BatchMonitor`. This ensures ENG5 GPT‑5.1 runs are attributed as
  `openai` / `gpt-5.1` instead of the CJ default Anthropic model for
  batches where comparison callbacks carry OpenAI attribution.

- For ENG5 anchor-align analysis we treat the following as the canonical
  GPT‑5.1 configuration:
  - Provider/model: `openai` / `gpt-5.1`
  - Reasoning effort: `"low"`
  - Output verbosity: `"low"`
  - Prompts: 003 language-control system/rubric pair
    (`scripts/cj_experiments_runners/eng5_np/prompts/system/003_language_control.txt`,
    `scripts/cj_experiments_runners/eng5_np/prompts/rubric/003_language_control.txt`).

- The three existing DB-based reports remain the primary analysis surface:
  - None:   `anchor_align_db_full_05c687fc-463d-4c2d-bcaa-73250d0830ca_20251201_133345.md`
  - Low:    `anchor_align_db_full_ddc3f259-b125-4a08-97fb-f4907fa50b3d_20251201_133351.md`
  - Medium: `anchor_align_db_full_7c0dcd60-deeb-482a-ad7c-f851df09f454_20251201_133358.md`

- Observed: GPT‑5.1 `low` and `medium` yield comparable alignment metrics
  on the ENG5 anchor set; given similar performance and lower cost,
  `low` is the preferred reasoning setting for further analysis.

- **Planned 006 usage/content parity experiments (GPT‑5.1 low)**:
  - A new 50-word usage/content parity prompt pair has been added for
    future GPT‑5.1 anchor-align experiments:
    - System:
      `scripts/cj_experiments_runners/eng5_np/prompts/system/006_usage_content_parity_system.txt`
    - Rubric:
      `scripts/cj_experiments_runners/eng5_np/prompts/rubric/006_usage_content_parity_rubric.txt`
  - 003 language-control remains the default prompt pair for all current
    ENG5 experiments.
  - 006 usage/content parity runs will be executed with
    `provider="openai"`, `model="gpt-5.1"`, `reasoning_effort="low"`,
    `output_verbosity="low"`, once the full ENG5→CJ→LPS→RAS flow is
    validated end-to-end (correct model attribution, artefact hydration,
    and DB-based reports).
- Planned CLI pattern:

    ```bash
    pdm run eng5-runner \
      --mode anchor-align-test \
      --anchor-align-provider openai \
      --anchor-align-model gpt-5.1 \
      --anchor-align-reasoning-effort low \
      --anchor-align-output-verbosity low \
      --system-prompt scripts/cj_experiments_runners/eng5_np/prompts/system/007_usage_guard.txt \
      --rubric scripts/cj_experiments_runners/eng5_np/prompts/rubric/006_usage_content_parity_rubric.txt \
      --batch-id "eng5-gpt51-low-usage-parity-006-$(date +%Y%m%d-%H%M%S)" \
      --await-completion
    ```

## 2025-12-01 – LOWER5 Tail-Only Loop (Usage Guard 007 + 006 Rubric)

- LOWER5 experiment scope:
  - Net: 5 weakest anchors only (`D‑`, `E+`, `E‑`, `F+`, `F+`).
  - Dataset directory (anchors only):
    `test_uploads/ANCHOR ESSAYS/ROLE_MODELS_ENG5_NP_2016/anchor_essays_5_lowest_grades`.
  - Goal: drive ≈20 comparisons on this 5‑essay net and **avoid early stop on BT stability**, using CJ’s small‑net Phase‑2 semantics.

- CJ configuration (LOWER5 small‑net override):
  - Settings applied to `cj_assessment_service` for these experiments (set in
    your dev environment, e.g. `.env` or exported in the shell before
    starting the stack):
    - `CJ_ASSESSMENT_SERVICE_MAX_PAIRWISE_COMPARISONS=20`
    - `CJ_ASSESSMENT_SERVICE_MIN_COMPARISONS_FOR_STABILITY_CHECK=20`
    - `CJ_ASSESSMENT_SERVICE_DEFAULT_BATCH_SIZE=20`
    - `CJ_ASSESSMENT_SERVICE_MIN_RESAMPLING_NET_SIZE=10`
    - `CJ_ASSESSMENT_SERVICE_MAX_RESAMPLING_PASSES_FOR_SMALL_NET=1`
  - Dev command (from repo root, Docker running):

    ```bash
    docker compose \
      -f docker-compose.yml \
      -f docker-compose.dev.yml \
      up -d cj_assessment_service llm_provider_service
    ```

- ENG5 runner LOWER5 wiring:
  - `RunnerPaths.from_repo_root` (`scripts/cj_experiments_runners/eng5_np/paths.py`) now honors an opt‑in env override:
    - Env var: `ENG5_ANCHOR_DIR_OVERRIDE`
    - Default anchors: `ROLE_MODELS_ENG5_NP_2016/anchor_essays`
    - LOWER5 override (inside runner container where repo root is `/app`):

      ```bash
      export ENG5_ANCHOR_DIR_OVERRIDE=/app/test_uploads/ANCHOR\ ESSAYS/ROLE_MODELS_ENG5_NP_2016/anchor_essays_5_lowest_grades
      ```

  - Unit coverage:
    - `scripts/cj_experiments_runners/eng5_np/tests/unit/test_paths.py`
      validates default vs override behavior.

- LOWER5 usage‑guard experiment loop (canonical config for this task):
  - Provider/model: `openai` / `gpt-5.1`
  - Reasoning effort: `"low"`
  - Output verbosity: `"low"`
  - System prompt: `scripts/cj_experiments_runners/eng5_np/prompts/system/007_usage_guard.txt`
  - Rubric: `scripts/cj_experiments_runners/eng5_np/prompts/rubric/006_usage_content_parity_rubric.txt`
  - Net: LOWER5 anchors only via `ENG5_ANCHOR_DIR_OVERRIDE` (no students).
  - CJ configuration: LOWER5 override compose file above.

- Canonical LOWER5 run command (from repo root):

  ```bash
  export ENG5_ANCHOR_DIR_OVERRIDE=/app/test_uploads/ANCHOR\ ESSAYS/ROLE_MODELS_ENG5_NP_2016/anchor_essays_5_lowest_grades

  pdm run eng5-runner \
    --mode anchor-align-test \
    --anchor-align-provider openai \
    --anchor-align-model gpt-5.1 \
    --anchor-align-reasoning-effort low \
    --anchor-align-output-verbosity low \
    --system-prompt scripts/cj_experiments_runners/eng5_np/prompts/system/007_usage_guard.txt \
    --rubric scripts/cj_experiments_runners/eng5_np/prompts/rubric/006_usage_content_parity_rubric.txt \
    --batch-id "eng5-gpt51-lower5-007-$(date +%Y%m%d-%H%M%S)" \
    --await-completion
  ```

- DB-based LOWER5 alignment reports:
  - After each run, resolve `cj_batch_id` for the runner’s `batch_uuid` and generate DB reports:

    ```bash
    # 1) Resolve cj_batch_id for the LOWER5 batch (replace BATCH_UUID)
    bash -lc 'set -a; source .env >/dev/null 2>&1 || true; set +a; \
      pdm run python - << "PY"
    import asyncio, asyncpg, os
    BATCH_UUID = "<batch_uuid_from_runner_log>"
    async def main():
        host = os.getenv("HULEEDU_DB_HOST", "localhost")
        port = int(os.getenv("HULEEDU_CJ_DB_PORT", os.getenv("HULEEDU_DB_PORT", "5434")))
        user = os.getenv("HULEEDU_DB_USER", "huleedu_user")
        password = os.getenv("HULEEDU_DB_PASSWORD", "huleedu_dev_password")
        conn = await asyncpg.connect(host=host, port=port, user=user, password=password,
                                     database="huleedu_cj_assessment")
        row = await conn.fetchrow(
            "SELECT id, bos_batch_id FROM cj_batch_uploads WHERE bos_batch_id=$1",
            BATCH_UUID,
        )
        print(row)
        await conn.close()
    asyncio.run(main())
    PY'

    # 2) Generate DB alignment reports (replace <lower5_cj_batch_id>)
    bash -lc 'set -a; source .env >/dev/null 2>&1 || true; set +a; \
      pdm run python -m scripts.cj_experiments_runners.eng5_np.db_alignment_report \
        --cj-batch-id <lower5_cj_batch_id> \
        --system-prompt-file scripts/cj_experiments_runners/eng5_np/prompts/system/007_usage_guard.txt \
        --rubric-file scripts/cj_experiments_runners/eng5_np/prompts/rubric/006_usage_content_parity_rubric.txt'
    ```

  - Outputs (canonical analysis surface for LOWER5):
    - `anchor_align_db_<uuid>_*.md`
    - `anchor_align_db_full_<uuid>_*.md`

- Latest LOWER5 run (2025-12-01, GPT‑5.1 low/low, usage guard 007 + 006 rubric):
  - `batch_id`: `eng5-gpt51-lower5-007-20251202-001714`
  - `batch_uuid`: `50f4509e-2e8c-4c62-a19d-93cf0739eefd`
  - `cj_batch_id`: `147`
  - DB reports:
    - Summary: `.claude/research/data/eng5_np_2016/anchor_align_db_50f4509e-2e8c-4c62-a19d-93cf0739eefd_20251201_231822.md`
    - Full: `.claude/research/data/eng5_np_2016/anchor_align_db_full_50f4509e-2e8c-4c62-a19d-93cf0739eefd_20251201_231822.md`
  - Key metrics:
    - Kendall’s tau `= 1.000` over the 5‑essay ladder (`D‑ > E+ > E‑ > F+ > F+`).
    - Direct inversions: `0`; one zero‑win anchor (lower F+ essay).
    - Justifications consistently emphasise clearer structure, richer content, and fewer basic errors for higher‑graded anchors; no tail inversions (no F+ beating D‑/E±).
  - Config notes: CJ small‑net overrides and GPT‑5.1 `reasoning_effort="low"`, `output_verbosity="low"` exactly matched the canonical LOWER5 loop.

- LOWER5 run with 006 parity prompts on both system + rubric (2025-12-01, GPT‑5.1 low/low):
  - `batch_id`: `eng5-gpt51-lower5-006-20251202-002205`
  - `batch_uuid`: `ec9c935c-e589-448c-b829-56ad545862f5`
  - `cj_batch_id`: `148`
  - DB reports:
    - Summary: `.claude/research/data/eng5_np_2016/anchor_align_db_ec9c935c-e589-448c-b829-56ad545862f5_20251201_232251.md`
    - Full: `.claude/research/data/eng5_np_2016/anchor_align_db_full_ec9c935c-e589-448c-b829-56ad545862f5_20251201_232251.md`
  - Key metrics:
    - Kendall’s tau `= 0.800` over the 5‑essay ladder.
    - Direct inversions: `1` (F+ essay `ANCHOR_ESSAY_ENG_5_363940D5` preferred over higher‑graded E‑ `ANCHOR_ESSAY_ENG_5_73127661` once, with justification “Clearer structure, richer content”).
    - Ladder shape: D‑ and E+ remain in positions 1 and 2; the F+ (`363940D5`) lifts above E‑ in BT rank (rank 3 vs expected 4), with one zero‑win F+ (`D298E687`) at the bottom.
    - Justifications across all pairs still stress structure, content richness, and error counts, but 006/006 configuration shows a mild usage/content parity tilt that can let a relatively strong F+ overtake E‑ when structure/content advantages dominate.
  - Config notes: Same CJ small‑net override and GPT‑5.1 `reasoning_effort="low"`, `output_verbosity="low"`; only the system prompt changed from 007 usage guard to 006 usage/content parity system text.

- LOWER5 007 system + 006 rubric with `reasoning_effort="none"` (2025-12-01, GPT‑5.1 none/low):
  - `batch_id`: `eng5-gpt51-lower5-007-none-20251202-003112`
  - `batch_uuid`: `4ce7468b-bf15-46b8-8a97-ebe51f79d45f`
  - `cj_batch_id`: `149`
  - DB reports:
    - Summary: `.claude/research/data/eng5_np_2016/anchor_align_db_4ce7468b-bf15-46b8-8a97-ebe51f79d45f_20251201_233151.md`
    - Full: `.claude/research/data/eng5_np_2016/anchor_align_db_full_4ce7468b-bf15-46b8-8a97-ebe51f79d45f_20251201_233151.md`
  - Key metrics:
    - Kendall’s tau `= 0.800` over the 5‑essay ladder.
    - Direct inversions: `1` (F+ `ANCHOR_ESSAY_ENG_5_D298E687` beating higher‑graded E‑ `ANCHOR_ESSAY_ENG_5_73127661`, justification: “Clearer structure, fuller ideas, slightly better control of grammar and vocabulary despite many errors”).
    - Ladder shape: D‑ and E+ remain 1–2; one F+ (`D298E687`) lifts above E‑ (rank 3 vs expected 4), with the other F+ (`363940D5`) zero‑win at the bottom.
    - Justifications continue to emphasise structure, idea development, and basic error counts; usage guard 007 plus `reasoning_effort="none"` still allows a single F+/E‑ inversion at the tail under LOWER5.
  - Config notes: Same LOWER5 CJ override and rubric 006; only reasoning effort changed from `"low"` to `"none"`.

- LOWER5 006 system + 006 rubric with `reasoning_effort="none"` (2025-12-01, GPT‑5.1 none/low):
  - `batch_id`: `eng5-gpt51-lower5-006-none-20251202-003200`
  - `batch_uuid`: `8cb7d51a-abc9-486c-bc4f-3654c19da7e1`
  - `cj_batch_id`: `150`
  - DB reports:
    - Summary: `.claude/research/data/eng5_np_2016/anchor_align_db_8cb7d51a-abc9-486c-bc4f-3654c19da7e1_20251201_233241.md`
    - Full: `.claude/research/data/eng5_np_2016/anchor_align_db_full_8cb7d51a-abc9-486c-bc4f-3654c19da7e1_20251201_233241.md`
  - Key metrics:
    - Kendall’s tau `= 1.000` over the 5‑essay ladder (`D‑ > E+ > E‑ > F+ > F+`).
    - Direct inversions: `0`; one zero‑win F+ anchor, identical ladder order to the low/low 007+006 run.
    - Despite weaker performance of GPT‑5.1 `none` on the full anchor set, LOWER5 with 006/006 parity prompts and `reasoning_effort="none"` recovers perfect tail alignment in this small‑net regime.
  - Config notes: Same LOWER5 CJ override and 006/006 prompt pair; only reasoning effort changed from `"low"` to `"none"`.

## Related

- Epic: `docs/product/epics/eng5-runner-refactor-and-prompt-tuning-epic.md` (EPIC‑008)
- Task: `TASKS/infrastructure/llm-provider-openai-gpt-5x-reasoning-controls.md`
- ENG5 runner: `scripts/cj_experiments_runners/eng5_np`
