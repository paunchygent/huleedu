---
type: runbook
service: global
severity: medium
last_reviewed: 2025-11-21
---

# ENG5 NP Runner – Execute & Alignment Runbook

## Purpose

Document the end-to-end steps for running the ENG5 NP runner in all modes:

- `plan` – inventory and validation preview
- `dry-run` – schema-only stub artefact
- `execute` – full CJ run with DB-owned anchors
- `anchor-align-test` – isolated anchor-only prompt-tuning experiments

The runner is implemented as a handler-based Typer CLI, where each mode
delegates to its own handler class under
`scripts/cj_experiments_runners/eng5_np/handlers/`. The CLI is responsible
for argument parsing and basic validation; handlers own the mode-specific
behavior and call into lower-level helpers (inventory, artefact I/O, Kafka
publish, hydrator, etc.).

## Prerequisites

1. **Repo setup**: `pdm install` with `monorepo-tools` extras.
2. **Assets**: `test_uploads/ANCHOR ESSAYS/ROLE_MODELS_ENG5_NP_2016/**` present with instructions,
   prompt, anchor essays, and student essays. Anchors must be registered with CJ; the CLI now performs registration automatically during EXECUTE and aborts if the CJ endpoint is unreachable.
3. **Docker stack**: `pdm run dev-build-start cj_assessment_service llm_provider_service`
   (or `pdm run dev-start ...`) so CJ + LLM Provider are reachable.
4. **Environment**: `source .env` to fill Kafka/bootstrap credentials. Confirm
   `KAFKA_BOOTSTRAP_SERVERS` points to the dev cluster.
5. **Pre-flight validation**: run `bash scripts/eng5_np_preflight.sh` to verify Docker services,
   Kafka connectivity, CJ admin CLI availability, and artefact directories before launching execute mode.

### Retrieve Assignment IDs (no auth required)

List registered instructions and anchors directly from database:

```bash
source .env
pdm run python scripts/cj_assessment_service/diagnostics/list_cj_instructions.py

# List anchors for specific assignment:
pdm run python scripts/cj_assessment_service/diagnostics/list_cj_instructions.py \
    --anchors 00000000-0000-0000-0000-000000000001
```

Output includes copy-paste hints for `--assignment-id` and `--course-id` parameters.

## Execution Steps (one batch – EXECUTE)

1. Inspect assets.

   ```bash
   pdm run eng5-np-run --mode plan
   ```

2. Dry-run schema generation without Kafka.

   ```bash
   pdm run eng5-np-run --mode dry-run --batch-id dev-batch --no-kafka
   ```

3. Execute with Kafka + await completion (ensure `CJ_SERVICE_URL` or `--cj-service-url` points at the active CJ instance; missing/invalid URLs now cause an immediate runner error).

```bash
pdm run eng5-np-run \
  --mode execute \
  --batch-id dev-batch-$(date +%Y%m%d-%H%M) \
  --await-completion \
  --completion-timeout 1800
```

> Optional: `--max-comparisons N` is now published as metadata for CJ to interpret (the runner no longer slices essays locally). Set it only when you need downstream observability/cost limits.

4. On success the CLI prints a comparison/cost summary and the artefact lives under
   `.claude/research/data/eng5_np_2016/assessment_run.execute.json`.

### Containerized Execution Wrapper

#### Recommended: Automated Orchestration (pdm run eng5-runner)

Use the automated wrapper script that handles infrastructure startup and health checks:

```bash
# The script automatically ensures Kafka, Zookeeper, Redis, CJ, and LLM Provider are running
pdm run eng5-runner \
  --mode execute \
  --batch-id eng5-execute-$(date +%Y%m%d-%H%M) \
  --await-completion \
  --completion-timeout 1800
```

Use the same command for **plan** and **dry-run** steps:

```bash
# Infrastructure automatically started if needed
pdm run eng5-runner --mode plan --batch-id eng5-plan-check
pdm run eng5-runner --mode dry-run --batch-id eng5-dry --no-kafka
```

The wrapper script (`scripts/run_eng5_np_runner.sh`) performs the following checks:
1. Verifies Kafka, Zookeeper, and Redis are running (starts them if needed)
2. Ensures Kafka topic setup has completed successfully
3. Verifies CJ Assessment and LLM Provider services are healthy (starts them if needed)
4. Runs the eng5_np_runner container with all arguments passed through

#### Manual: Direct Docker Compose (Advanced)

For manual control or troubleshooting, run the container directly after ensuring infrastructure is up:

```bash
# First, ensure infrastructure and dependencies are running:
pdm run dev-start cj_assessment_service llm_provider_service

# Then run the container manually:
docker compose -f docker-compose.yml -f docker-compose.eng5-runner.yml run --rm \
  eng5_np_runner \
  --mode execute \
  --batch-id eng5-execute-$(date +%Y%m%d-%H%M) \
  --await-completion \
  --completion-timeout 1800
```

Manual execution for **plan** and **dry-run**:

```bash
docker compose -f docker-compose.yml -f docker-compose.eng5-runner.yml run --rm \
  eng5_np_runner --mode plan --batch-id eng5-plan-check

docker compose -f docker-compose.yml -f docker-compose.eng5-runner.yml run --rm \
  eng5_np_runner --mode dry-run --batch-id eng5-dry --no-kafka
```

> ℹ️  When running outside Docker (e.g., `pdm run eng5-np-run`), pipe output through
> `tee` so logs persist locally for audits:
> `pdm run eng5-np-run --mode execute ... | tee eng5_runner.log`

## Anchor Alignment Prompt-Tuning (`anchor-align-test`)

### Purpose

`anchor-align-test` mode runs CJ on **anchor essays only** (no student essays)
to measure how well LLM comparative judgments align with expert anchor grades.
It uses GUEST semantics (`assignment_id=None` in the request), so no DB-owned
anchors or grade projections are involved and no production state is affected.

### Prerequisites

1. **Assets**: Same ENG5 role model assets as EXECUTE:
   - Role model instructions and prompt
   - Anchor essays directory
   - `ANCHOR_ESSAYS_BAYESIAN_INFERENCE_DATA.(csv|xlsx)` with expert grades
2. **Services**: CJ Assessment + LLM Provider running and reachable.
3. **Kafka**:
   - For `--await-completion`, Kafka must be up and reachable via
     `KAFKA_BOOTSTRAP_SERVERS`.
   - For quick dry testing, you may use `--no-kafka` to skip publish.
4. **Prompt files**:
   - System prompt variants under
     `scripts/cj_experiments_runners/eng5_np/prompts/system/`
   - Rubric variants under
     `scripts/cj_experiments_runners/eng5_np/prompts/rubric/`

### CLI Usage

Baseline run with explicit prompt/rubric and alignment report generation:

```bash
pdm run eng5-runner \
  --mode anchor-align-test \
  --system-prompt scripts/cj_experiments_runners/eng5_np/prompts/system/001_baseline.txt \
  --rubric scripts/cj_experiments_runners/eng5_np/prompts/rubric/001_baseline.txt \
  --batch-id "anchor-align-baseline-$(date +%Y%m%d-%H%M%S)" \
  --await-completion
```

Key notes:

- `--assignment-id` is **optional** in this mode. The handler explicitly sets
  `assignment_id=None` before composing the CJ request to trigger GUEST
  behavior (no DB anchors, no grade projection).
- All anchor essays are treated as **students** in the CJ request; this keeps
  the experiment fully isolated from production anchor calibration logic.
- `--system-prompt` and `--rubric` are file paths; the handler loads their
  contents and threads them via `LLMConfigOverrides` so they are visible to CJ
  and LLM Provider.

### Alignment Report Output

When `--await-completion` is set and Kafka callbacks complete, the handler:

1. Hydrates CJ results into the ENG5 artefact.
2. Generates a markdown alignment report:

   - Location: `.claude/research/data/eng5_np_2016/anchor_align_{batch_id}_{timestamp}.md`
   - Contents:
     - Per-anchor BT scores, ranks, expert grades, wins/losses, win rate.
     - **Direct inversions**: lower-grade anchors beating higher-grade anchors.
     - **Zero-win anchors**: anchors that never win a comparison.
     - **Kendall's tau** between expected (expert) and actual (BT) ranks.
     - Embedded system prompt and judge rubric text for reproducibility.

#### DB-Based Alignment Report (No Re-run, CJ as Source of Truth)

For post-hoc analysis and baseline validation, prefer generating alignment
reports directly from CJ Assessment DB data instead of re-running ENG5:

```bash
# 1) Ensure .env is exported so CJ DB credentials are available
bash -lc 'set -a; source .env >/dev/null 2>&1 || true; set +a; \
  pdm run python -m scripts.cj_experiments_runners.eng5_np.db_alignment_report \
    --cj-batch-id <cj_batch_id>'
```

Notes:
- `db_alignment_report`:
  - Reads `cj_comparison_pairs` and `cj_processed_essays` for the given
    `cj_batch_id` using the same connection settings as
    `scripts/cj_assessment_service/diagnostics/extract_cj_results.py`.
  - Filters comparisons to successful pairs only (matching CJ scoring
    semantics), then reconstructs per-anchor wins/losses, zero-win anchors,
    and direct inversions (unique anchor pairs).
  - Derives expert grades and filenames from
    `test_uploads/ANCHOR ESSAYS/ROLE_MODELS_ENG5_NP_2016/anchor_essays/`
    using `extract_grade_from_filename`, so duplicate grades (two A, B,
    F+ anchors) remain distinguishable.
  - Writes a timestamped markdown report under
    `.claude/research/data/eng5_np_2016/anchor_align_db_{batch_label}_{timestamp}.md`.
- Use `scripts/cj_assessment_service/diagnostics/extract_cj_results.py` to
  discover the correct `cj_batch_id` (or BOS batch ID) for a given ENG5 run.

Baseline acceptance targets (from batch 108 analysis):

| Metric            | Baseline (Batch 108) | Target |
|-------------------|----------------------|--------|
| Direct inversions | 5                    | ≤1     |
| Zero-win anchors  | 1 (ANCHOR_7)         | 0      |
| Kendall's tau     | ~0.82                | ≥0.90  |
| A/B regression    | 0                    | 0      |

These metrics should be monitored when iterating on prompt/rubric variants.

#### GPT-5.1 / GPT-5.x Experiments (via LLM Provider)

For cross-provider experiments (e.g. comparing Anthropic Sonnet vs OpenAI GPT-5.1
on the same ENG5 anchors), use `ANCHOR_ALIGN_TEST` with explicit LLM overrides
that target the LLM Provider Service:

```bash
# Example: ENG5 anchor-align-test with OpenAI GPT-5.1 (reasoning effort = none)
pdm run python -m scripts.cj_experiments_runners.eng5_np.cli \
  --mode anchor-align-test \
  --course-id 00000000-0000-0000-0000-000000000052 \
  --batch-id eng5-gpt51-none \
  --kafka-bootstrap localhost:9093 \
  --llm-provider openai \
  --llm-model gpt-5.1 \
  --system-prompt scripts/cj_experiments_runners/eng5_np/prompts/system/003_language_control.txt \
  --rubric scripts/cj_experiments_runners/eng5_np/prompts/rubric/003_language_control.txt \
  --await-completion
```

Notes and conventions:
- GPT-5.x (including GPT-5.1) does **not** support `temperature`/`top_p` and
  uses reasoning controls instead. Reasoning effort and verbosity are carried
  via LLM Provider overrides:
  - `reasoning.effort ∈ {none, low, medium, high}` (default: `none`).
  - `text.verbosity ∈ {low, medium, high}` (default: provider-specific).
- The LLM Provider Service exposes these hints through
  `LLMConfigOverridesHTTP.reasoning_effort` / `output_verbosity` and maps them
  into OpenAI payloads for GPT-5 family models.
- For ENG5 research runs, treat GPT-5.1 as an **analysis configuration**:
  - Keep Anthropic Sonnet/Haiku as primary baseline.
  - Use GPT-5.1 with different `reasoning_effort` levels in `anchor-align-test`
    mode and compare alignment reports (Kendall’s tau, inversions, zero-win
    anchors) using `db_alignment_report`.

### Prompt variants

- **003 – language-control (baseline)**:
  - 50-word justification cap focused on language and style control.
  - Files:
    - System: `scripts/cj_experiments_runners/eng5_np/prompts/system/003_language_control.txt`
    - Rubric: `scripts/cj_experiments_runners/eng5_np/prompts/rubric/003_language_control.txt`
- **006 – usage/content parity (planned GPT‑5.1 low)**:
  - 50-word justification cap emphasizing joint content and language
    quality (“usage/content parity”) for anchor-align experiments.
  - Files:
    - System: `scripts/cj_experiments_runners/eng5_np/prompts/system/006_usage_content_parity_system.txt`
    - Rubric: `scripts/cj_experiments_runners/eng5_np/prompts/rubric/006_usage_content_parity_rubric.txt`
  - Intended to run with OpenAI GPT‑5.1, `reasoning_effort="low"`,
    `output_verbosity="low"`, using the explicit `--system-prompt` /
    `--rubric` pattern once the ENG5→CJ→LPS→RAS flow is fully validated.

### Background Job Caveat (Batch IDs)

When launching ENG5 runs as **background tasks** via Bash tooling, avoid
relying on intermediate shell variables for `--batch-id`. Use inline command
substitutions instead:

```bash
# Recommended: inline substitution (works in background tasks)
pdm run eng5-runner --batch-id "eng5-full-$(date +%Y%m%d-%H%M%S)" --mode anchor-align-test ...
```

Patterns that assign to `BATCH_ID` and then reference it within a wrapped
background command can expand to an empty string, leading to ambiguous batch
labels in logs and reports.

## Monitoring & Observability

- **Kafka**: `pdm run dev-logs cj_assessment_service` to ensure callbacks stream without lag.
- **Metrics**:
  - `huleedu_cj_prompt_fetch_failures_total` (CJ service) – must stay flat.
  - `llm_requests_total{status="queued"}` (LLM provider) – confirms enqueue volume.
- **Grafana dashboards**: review sections 51–62 in `documentation/OPERATIONS/01-Grafana-Playbook.md`
  for ENG5 prompt hydration and CJ runner monitoring panels.
- **Runner summary**: after completion the CLI prints provider/model token and cost totals plus
  whether partial data occurred.

### LLM batching & serial-bundle diagnostics

- **When to use**
  - Prefer these checks when LLM Provider Service is configured to call *real* providers (not
    mock mode) and `serial_bundle` is enabled for ENG5 trials.
- **CLI output**
  - After a successful EXECUTE run with `--await-completion`, the runner prints:
    - `LLM batching diagnostics (Prometheus query hints)` followed by example Prometheus queries.
  - Copy/paste these into Grafana Explore to inspect:
    - `cj_llm_requests_total{batching_mode}` and `cj_llm_batches_started_total{batching_mode}` for
      CJ-side mode usage.
    - `llm_provider_serial_bundle_calls_total{provider,model}` and
      `llm_provider_serial_bundle_items_per_call{provider,model}` for bundle usage.
    - `llm_provider_queue_expiry_total{provider,queue_processing_mode,expiry_reason}` and
      `llm_provider_queue_wait_time_seconds{queue_processing_mode,result}` for queue health.
- **ENG5-first rollout guardrails (summary)**
  - Today (Phase 1): ENG5 trials use `serial_bundle` only:
    - `CJ_ASSESSMENT_SERVICE_LLM_BATCHING_MODE=serial_bundle`
    - `LLM_PROVIDER_SERVICE_QUEUE_PROCESSING_MODE=serial_bundle`
    - `LLM_PROVIDER_SERVICE_BATCH_API_MODE=disabled`
    - Metrics to pin:
      - CJ: `cj_llm_requests_total{batching_mode="serial_bundle"}`,
        `cj_llm_batches_started_total{batching_mode="serial_bundle"}`.
      - LPS: `llm_provider_serial_bundle_calls_total{provider,model}`,
        `llm_provider_serial_bundle_items_per_call{provider,model}`,
        `llm_provider_queue_wait_time_seconds{queue_processing_mode="serial_bundle",result}`.
  - Future (Phase 2 – provider batch APIs):
    - ENG5 provider‑batch trials will instead run with:
      - `CJ_ASSESSMENT_SERVICE_LLM_BATCHING_MODE=provider_batch_api`
      - `LLM_PROVIDER_SERVICE_QUEUE_PROCESSING_MODE=batch_api`
      - Provider‑specific `*_BATCH_API_MODE` set to `nightly`/`opportunistic` for the ENG5 pair.
    - Additional metrics to monitor:
      - CJ: `cj_llm_requests_total{batching_mode="provider_batch_api"}`,
        `cj_llm_batches_started_total{batching_mode="provider_batch_api"}`.
      - LPS queue: `llm_provider_queue_wait_time_seconds{queue_processing_mode="batch_api",result}`,
        `llm_provider_comparison_callbacks_total{queue_processing_mode="batch_api",result}`.
      - LPS jobs: `llm_provider_batch_api_jobs_total{provider,model,status}`,
        `llm_provider_batch_api_items_per_job{provider,model}`,
        `llm_provider_batch_api_job_duration_seconds{provider,model}`.
  - Enable trial runs by setting:
    - `CJ_ASSESSMENT_SERVICE_LLM_BATCHING_MODE=serial_bundle`
    - `LLM_PROVIDER_SERVICE_QUEUE_PROCESSING_MODE=serial_bundle`
    - `LLM_PROVIDER_SERVICE_BATCH_API_MODE=disabled`
  - For each trial batch:
    - Confirm error rates and queue wait-time percentiles remain close to per-request baselines.
    - Check that serial-bundle metrics move only for the expected provider/model pair used by ENG5.
  - To roll back:
    - Set `CJ_ASSESSMENT_SERVICE_LLM_BATCHING_MODE=per_request`
    - Set `LLM_PROVIDER_SERVICE_QUEUE_PROCESSING_MODE=per_request`
    - Leave `LLM_PROVIDER_SERVICE_BATCH_API_MODE=disabled`
    - Redeploy CJ and LLM Provider; HTTP contracts and callbacks are unchanged across modes.

### ENG5/CJ serial-bundle test harness

- **ENG5 profile parity tests**
  - High-fidelity, trace-based ENG5/LOWER5 mocks live in `tests/eng5_profiles/*` and are treated as **ENG5 profile parity tests** (separate from standard docker integration tests under `tests/integration/`).
- **Recommended orchestration commands**
  - `pdm run eng5-cj-docker-suite` – recreates `cj_assessment_service` + `llm_provider_service` and runs CJ docker semantics tests:
    - `pdm run eng5-cj-docker-suite` – run LOWER5 small-net + regular ENG5 batch tests.
    - `pdm run eng5-cj-docker-suite small-net` – only `tests/functional/cj_eng5/test_cj_small_net_continuation_docker.py`.
    - `pdm run eng5-cj-docker-suite regular` – only regular ENG5 batch tests (resampling + callbacks) in `tests/functional/cj_eng5/`.
  - `pdm run llm-mock-profile <profile>` – switches LLM Provider mock profile, restarts the service, and runs the matching ENG5 profile parity suite:
    - `cj-generic`, `eng5-anchor`, `eng5-lower5` map to tests in `tests/eng5_profiles/*` (see `tests/eng5_profiles/test_eng5_profile_suite.py` for the orchestrator).
    - These parity suites now also pin LPS serial-bundle and queue metrics for the mock provider:
      - `llm_provider_serial_bundle_calls_total{provider="mock",model=<profile_model>}` (≥1 per run).
      - `llm_provider_serial_bundle_items_per_call_{count,bucket}{provider="mock",model=<profile_model>}` with `1 <= max(items_per_call) <= Settings.SERIAL_BUNDLE_MAX_REQUESTS_PER_CALL`.
      - `llm_provider_queue_wait_time_seconds_{count,sum}{queue_processing_mode="serial_bundle"}` with average wait in `[0, 120]` seconds and `result ⊆ {success,failure,expired}`, plus guardrails on `llm_provider_comparison_callbacks_total{queue_processing_mode="serial_bundle"}` and `llm_provider_queue_depth{queue_type="total"}` (no runaway queue growth).
- **Running individual test files (selective validation)**
  - All tests remain runnable via `pytest-root` when you need to validate a single file instead of the full suite, for example:
    ```bash
    pdm run pytest-root tests/functional/cj_eng5/test_cj_regular_batch_callbacks_docker.py -m "docker and integration" -v
    pdm run pytest-root tests/functional/cj_eng5/test_cj_small_net_continuation_docker.py -m "docker and integration" -v
    pdm run pytest-root tests/eng5_profiles/test_eng5_mock_parity_lower5.py -m "docker and integration" -v
    ```

### CI / validation for ENG5 heavy suites

- **Workflow**: `.github/workflows/eng5-heavy-suites.yml`
- **Jobs (heavy, non-default CI path)**:
  - `ENG5 CJ Docker Semantics (regular + small-net)` (`eng5-cj-docker-regular-and-small-net`)
    - Triggers: `workflow_dispatch`, nightly `schedule` (03:00 UTC).
    - Environment (expected):
      - `CJ_ASSESSMENT_SERVICE_LLM_BATCHING_MODE=serial_bundle`
      - `CJ_ASSESSMENT_SERVICE_ENABLE_LLM_BATCHING_METADATA_HINTS=true`
      - `LLM_PROVIDER_SERVICE_QUEUE_PROCESSING_MODE=serial_bundle`
      - `LLM_PROVIDER_SERVICE_BATCH_API_MODE=disabled`
      - `LLM_PROVIDER_SERVICE_USE_MOCK_LLM=true` / `LLM_PROVIDER_SERVICE_ALLOW_MOCK_PROVIDER=true`
    - Commands:
      - `pdm run eng5-cj-docker-suite regular`
      - `pdm run eng5-cj-docker-suite small-net`
    - Local reproduction (from repo root, .env matching the above):
      ```bash
      pdm run eng5-cj-docker-suite regular
      pdm run eng5-cj-docker-suite small-net
      ```
  - `ENG5 Mock Profile Parity Suite` (`eng5-profile-parity-suite`)
    - Triggers: `workflow_dispatch`, nightly `schedule` (03:00 UTC).
    - Environment (expected):
      - `LLM_PROVIDER_SERVICE_QUEUE_PROCESSING_MODE=serial_bundle`
      - `LLM_PROVIDER_SERVICE_BATCH_API_MODE=disabled`
      - `LLM_PROVIDER_SERVICE_USE_MOCK_LLM=true` / `LLM_PROVIDER_SERVICE_ALLOW_MOCK_PROVIDER=true`
    - For each profile, CI updates `.env` `LLM_PROVIDER_SERVICE_MOCK_MODE` and runs:
      - Generic CJ mock:
        ```bash
        pdm run llm-mock-profile cj-generic
        ```
      - ENG5 anchor:
        ```bash
        pdm run llm-mock-profile eng5-anchor
        ```
      - ENG5 LOWER5:
        ```bash
        pdm run llm-mock-profile eng5-lower5
        ```
    - Local reproduction:
      - Use the same `pdm run llm-mock-profile <profile>` commands as above, or run the orchestrator:
        ```bash
        pdm run pytest-root tests/eng5_profiles/test_eng5_profile_suite.py -m "docker and integration" -v
        ```

### Stability & budget recipes (ENG5)

- **Default serial-bundle behaviour (recommended)**  
  - CJ settings:
    - `CJ_ASSESSMENT_SERVICE_LLM_BATCHING_MODE=serial_bundle`
    - `CJ_ASSESSMENT_SERVICE_MAX_PAIRWISE_COMPARISONS` set to a safe cap (e.g. 150)
    - `CJ_ASSESSMENT_SERVICE_MIN_COMPARISONS_FOR_STABILITY_CHECK` ~ 10
    - `CJ_ASSESSMENT_SERVICE_SCORE_STABILITY_THRESHOLD` ~ 0.05
  - Effect: CJ submits comparisons in waves, runs BT stability after each wave, and can stop early
    when scores stabilize or the cap is reached. `--max-comparisons` from ENG5 is treated as a cap,
    not an obligation.

- **“Use full cap” serial-bundle runs (no early stop, still waves)**  
  - CJ settings (per environment, not per batch):
    - Keep `LLM_BATCHING_MODE=serial_bundle`.
    - Choose a cap `C` via `MAX_PAIRWISE_COMPARISONS` (or a runner override).
    - Wave size (comparisons per callback iteration) emerges from batch size,
      matching strategy, and CJ’s comparison budget; tune stability via
      `MIN_COMPARISONS_FOR_STABILITY_CHECK` / `SCORE_STABILITY_THRESHOLD` and cost
      via `MAX_PAIRWISE_COMPARISONS`.
    - Set `MIN_COMPARISONS_FOR_STABILITY_CHECK > C` so the stability gate never passes.
  - Effect: CJ will always finalize only after the denominator/cap is reached; stability is
    effectively disabled without introducing a separate flag.

- **Future “all at once” provider-batch runs (design intent)**  
  - Runner selects `llm_batching_mode_override=provider_batch_api` and sets a cap via
    `--max-comparisons`.
  - CJ generates all required pairs up to the cap in a **single** wave and calls the LLM Provider
    using its true batch API. Once callbacks for that wave are complete, CJ computes scores once
    and finalizes, skipping continuation regardless of stability. See ADR-0017 and the CJ
    assessment runbook for the high-level pattern; implementation will land in a dedicated PR.

### BT SE Diagnostics Interpretation

BT (Bradley-Terry) Standard Error diagnostics provide insight into comparison graph quality. These are **diagnostic-only** fields that do NOT gate completion, stability checks, or success-rate guards.

#### Available Fields (from `CJBatchState.processing_metadata`)

| Field | Type | Description |
|-------|------|-------------|
| `bt_se_summary.mean_se` | float | Average SE across all essays |
| `bt_se_summary.max_se` | float | Maximum SE value (capped at 2.0) |
| `bt_se_summary.min_se` | float | Minimum SE value |
| `bt_se_summary.items_at_cap` | int | Essays with SE >= 2.0 (poorly constrained) |
| `bt_se_summary.isolated_items` | int | Essays with 0 comparisons |
| `bt_se_summary.mean_comparisons_per_item` | float | Average comparisons per essay |
| `bt_quality_flags.bt_se_inflated` | bool | True if mean_se > 0.4 OR max_se > 0.8 |
| `bt_quality_flags.comparison_coverage_sparse` | bool | True if mean_comparisons_per_item < 1.0 |
| `bt_quality_flags.has_isolated_items` | bool | True if isolated_items > 0 |

#### Interpretation Guide

**Normal Operation:**
- `mean_se` < 0.4 and `max_se` < 0.8
- `items_at_cap` = 0
- `isolated_items` = 0
- All quality flags = false

**When `bt_se_inflated = true`:**
- Investigate anchor coverage - are anchors getting enough comparisons?
- Check if total budget is sufficient for essay count
- Review if callback failures are reducing effective comparisons
- NOT a failure state - grade projections may still be reliable

**When `comparison_coverage_sparse = true`:**
- Essays are averaging < 1 comparison each
- May indicate early batch termination or budget exhaustion
- Check `items_at_cap` to see how many essays are poorly constrained
- Consider increasing `total_budget` for future batches

**When `has_isolated_items = true`:**
- Some essays have zero comparisons (no BT score possible)
- Check pair matching strategy and anchor distribution
- Isolated items will have capped SE (2.0) and neutral scores
- May affect grade projection quality for those specific essays

#### Key Principle

These diagnostics are **gauges on the dashboard, not steering wheels**. They inform operator awareness but do not change:
- Completion threshold semantics
- Stability check behaviour
- Success-rate guard logic

Use them to:
1. Monitor batch health trends over time
2. Tune budgets and comparison strategies for future batches
3. Investigate anomalies when quality appears degraded
4. Correlate with grade projection confidence in downstream analysis

### Structured JSON Logging

- The runner configures `structlog` via `logging_support.configure_cli_logging()` with
  `service_name="eng5-np-runner"` so every entry is JSON and includes
  `correlation_id`, `batch_id`, and `runner_mode` bindings.
- `log_validation_state()` is invoked for **plan**, **dry-run**, and **execute** flows.
  The resulting log line (`runner_validation_state`) exposes manifest length, checksum,
  and the embedded `validation.runner_status` block for downstream dashboards.
- Hydrator and Kafka collector logs emit `collector_*` and `*_hydrated` events with
  incrementing counters to track callback progress; expect these alongside
  `runner_execution_complete` for execute mode.

### Loki Query Examples

Assuming Promtail ships container stdout, verify logs in Grafana Explore with:

```logql
{service_name="eng5-np-runner"} |= "runner_validation_state"
```

To isolate a specific batch / correlation ID:

```logql
{service_name="eng5-np-runner", batch_id="eng5-dry"} | json | correlation_id
```

Check for partial data warnings:

```logql
{service_name="eng5-np-runner"} |= "collector_timeout"
```

## Validation Checklist

1. **Schema**: run `pdm run pytest-root scripts/tests/test_eng5_np_runner.py -k schema` if artefact
   shape changes.
2. **Manifest**: `jq '.validation.manifest' assessment_run.execute.json` should list every file under
   `requests/` and `events/` with SHA256 digests.
3. **Runner status**: check `validation.runner_status.partial_data` – should be `false`. If `true`,
   rerun with a higher `--completion-timeout` after confirming CJ/LLM logs.
4. **Cost sanity**: review the CLI summary or `costs.token_counts` inside the artefact to ensure
   providers/models match expectations.

### Post-Execution Artefact Inspection

Use `jq` to spot-check the execute artefact after a run:

- Inspect comparison coverage by grade scale band:

  ```bash
  jq '.results.comparisons | group_by(.grade_scale) | map({scale: .[0].grade_scale, count: length})' \
    .claude/research/data/eng5_np_2016/assessment_run.execute.json
  ```

- Verify that every essay exposes prompt references and projections:

  ```bash
  jq '.results.essays[] | {essay_id, grade: .grade_projection.grade, prompt_ref: .student_prompt_ref.storage_id}' \
    .claude/research/data/eng5_np_2016/assessment_run.execute.json
  ```

- Cross-check manifests for checksum drift:

  ```bash
  jq '.validation.manifest | to_entries[] | {path: .key, sha256: .value.sha256}' \
    .claude/research/data/eng5_np_2016/assessment_run.execute.json
  ```

## Failure Modes & Recovery

- **Runner exits with `Missing prompt hash`**

  - *Cause*: Queue processor failed before hashing.
  - *Action*: Inspect LLM provider logs; ensure error callbacks now include `prompt_sha256`. Re-run once provider issue resolved.

- **Timeout with partial artefact**

  - *Cause*: CJ pipeline slow or callbacks dropped.
  - *Action*: Bump `--completion-timeout`, watch Kafka lag, confirm `CJAssessmentCompletedV1` emitted. Artefact records `runner_status.partial_data=true` for forensic tracking.

- **Schema validation fails**

  - *Cause*: Inputs folder missing anchors/students or files unreadable.
  - *Action*: Re-sync role-model assets. Stub creation now surfaces warnings for missing files; fix before execute rerun.

- **Duplicate comparisons in artefact**

  - *Cause*: Should no longer occur (dedupe guard).
  - *Action*: If observed, clear `.claude/research/data/eng5_np_2016/events` and rerun to isolate offending callback.

## CJ DB Inspection (`scripts/cj_assessment_service/diagnostics/extract_cj_results.py`)

Use this script for **one-off inspection** of a single CJ/ENG5 batch directly from the CJ Assessment database. It is a diagnostic tool for developers/analysts, **not** a user-facing reporting surface (RAS remains the source of truth).

### Prerequisites

- CJ dev stack running (CJ Assessment DB up):

  ```bash
  pdm run dev-start cj_assessment_service
  ```

- Environment loaded (DB host/user/password/ports):

  ```bash
  source .env
  ```

- Standard dev DB defaults are:
  - `HULEEDU_DB_HOST=localhost`
  - `HULEEDU_CJ_DB_PORT=5434` (or `HULEEDU_DB_PORT`)
  - `HULEEDU_DB_USER=huleedu_user`
  - `HULEEDU_DB_PASSWORD=huleedu_dev_password`
  - Database: `huleedu_cj_assessment`

### Basic Usage

From the repo root:

```bash
pdm run python scripts/cj_assessment_service/diagnostics/extract_cj_results.py <batch_identifier>
```

- `<batch_identifier>` can be:
  - Internal CJ batch ID (`cj_batch_uploads.id`), e.g. `5`
  - BOS batch ID (`cj_batch_uploads.bos_batch_id`), e.g. `eng5-execute-20251129-1200`

### Common Patterns

**1. Human-readable report for ENG5 batch**

```bash
pdm run python scripts/cj_assessment_service/diagnostics/extract_cj_results.py eng5-execute-20251129-1200
```

This prints:

- Batch + state summary (`cj_batch_uploads`, `cj_batch_states`)
- All comparison pairs + winners/justifications (`cj_comparison_pairs`)
- BT ranking table (score, SE, wins/losses, anchor flag, `known_grade`)
- Student grade projections (if present)
- Summary counts (students/anchors, comparisons, failures, projections)

**2. Save text report to file**

```bash
pdm run python scripts/cj_assessment_service/diagnostics/extract_cj_results.py eng5-execute-20251129-1200 \
  --format text \
  --output /tmp/cj_eng5_batch_report.txt
```

**3. JSON for analysis (e.g. notebooks)**

```bash
pdm run python scripts/cj_assessment_service/diagnostics/extract_cj_results.py 5 \
  --format json \
  --output /tmp/cj_batch_5.json
```

JSON structure:

- `batch_info` – from `cj_batch_uploads`
- `batch_state` – from `cj_batch_states`
- `comparisons` – from `cj_comparison_pairs`
- `bradley_terry_stats` – from `cj_processed_essays`
- `grade_projections` – from `grade_projections`
- `wins_losses` – derived per‑essay `{wins, losses, total}`

### Notes

- This script is for **internal inspection** of CJ data. For any user-facing reports or ENG5 validation outputs, continue to treat **RAS** as the authoritative source.
- When investigating ENG5 runs, use:
  - RAS (HTTP/DB) for official results.
  - `extract_cj_results.py` for low-level CJ diagnostics (BT graph, SEs, comparison coverage, raw justifications).

## Artefact Locations

- Requests: `.claude/research/data/eng5_np_2016/requests/`
- Events: `.claude/research/data/eng5_np_2016/events/{comparisons,assessment_results,completions}`
- Summary JSON: `.claude/research/data/eng5_np_2016/assessment_run.execute.json`

Keep this runbook updated as ENG5 tooling evolves (e.g., new overrides, different cost reporting).
- **Anchor registration failure**

  - *Cause*: `CJ_SERVICE_URL` missing/incorrect, CJ admin auth expired, or anchor API down.
  - *Action*: Fix configuration or CJ availability and rerun; EXECUTE mode now intentionally aborts rather than falling back to uploading anchors inline.
