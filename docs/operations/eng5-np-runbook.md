---
type: runbook
service: global
severity: medium
last_reviewed: 2025-11-21
---

# ENG5 NP Runner – Execute Mode Runbook

## Purpose

Document the end-to-end steps for running `pdm run eng5-np-run --mode execute` with
metadata-complete artefacts that power Phase 3.3 confidence analysis.

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

## Execution Steps (one batch)

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

### Stability & budget recipes (ENG5)

- **Default serial-bundle behaviour (recommended)**  
  - CJ settings:
    - `CJ_ASSESSMENT_SERVICE_LLM_BATCHING_MODE=serial_bundle`
    - `CJ_ASSESSMENT_SERVICE_MAX_PAIRWISE_COMPARISONS` set to a safe cap (e.g. 150)
    - `CJ_ASSESSMENT_SERVICE_COMPARISONS_PER_STABILITY_CHECK_ITERATION` = wave size (e.g. 10–25)
    - `CJ_ASSESSMENT_SERVICE_MIN_COMPARISONS_FOR_STABILITY_CHECK` ~ 10
    - `CJ_ASSESSMENT_SERVICE_SCORE_STABILITY_THRESHOLD` ~ 0.05
  - Effect: CJ submits comparisons in waves, runs BT stability after each wave, and can stop early
    when scores stabilize or the cap is reached. `--max-comparisons` from ENG5 is treated as a cap,
    not an obligation.

- **“Use full cap” serial-bundle runs (no early stop, still waves)**  
  - CJ settings (per environment, not per batch):
    - Keep `LLM_BATCHING_MODE=serial_bundle`.
    - Choose a cap `C` via `MAX_PAIRWISE_COMPARISONS` (or a runner override).
    - Set `COMPARISONS_PER_STABILITY_CHECK_ITERATION >= C` if you want a single wave, or leave it
      smaller for multiple waves.
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

## Artefact Locations

- Requests: `.claude/research/data/eng5_np_2016/requests/`
- Events: `.claude/research/data/eng5_np_2016/events/{comparisons,assessment_results,completions}`
- Summary JSON: `.claude/research/data/eng5_np_2016/assessment_run.execute.json`

Keep this runbook updated as ENG5 tooling evolves (e.g., new overrides, different cost reporting).
- **Anchor registration failure**

  - *Cause*: `CJ_SERVICE_URL` missing/incorrect, CJ admin auth expired, or anchor API down.
  - *Action*: Fix configuration or CJ availability and rerun; EXECUTE mode now intentionally aborts rather than falling back to uploading anchors inline.
