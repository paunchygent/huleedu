# ENG5 NP Runner – Execute Mode Runbook

## Purpose

Document the end-to-end steps for running `pdm run eng5-np-run --mode execute` with
metadata-complete artefacts that power Phase 3.3 confidence analysis.

## Prerequisites

1. **Repo setup**: `pdm install` with `monorepo-tools` extras.
2. **Assets**: `test_uploads/ANCHOR ESSAYS/ROLE_MODELS_ENG5_NP_2016/**` present with instructions,
   prompt, anchor essays, and student essays.
3. **Docker stack**: `pdm run dev-build-start cj_assessment_service llm_provider_service`
   (or `pdm run dev-start ...`) so CJ + LLM Provider are reachable.
4. **Environment**: `source .env` to fill Kafka/bootstrap credentials. Confirm
   `KAFKA_BOOTSTRAP_SERVERS` points to the dev cluster.

## Execution Steps (one batch)

1. Inspect assets:
   ```bash
   pdm run eng5-np-run --mode plan
   ```
2. Dry-run schema generation without Kafka:
   ```bash
   pdm run eng5-np-run --mode dry-run --batch-id dev-batch --no-kafka
   ```
3. Execute with Kafka + await completion:
   ```bash
   pdm run eng5-np-run \
     --mode execute \
     --batch-id dev-batch-$(date +%Y%m%d-%H%M) \
     --await-completion \
     --completion-timeout 1800
   ```
4. On success the CLI prints a comparison/cost summary and the artefact lives under
   `.claude/research/data/eng5_np_2016/assessment_run.execute.json`.

## Monitoring & Observability

- **Kafka**: `pdm run dev-logs cj_assessment_service` to ensure callbacks stream without lag.
- **Metrics**:
  - `huleedu_cj_prompt_fetch_failures_total` (CJ service) – must stay flat.
  - `llm_requests_total{status="queued"}` (LLM provider) – confirms enqueue volume.
- **Runner summary**: after completion the CLI prints provider/model token and cost totals plus
  whether partial data occurred.

## Validation Checklist

1. **Schema**: run `pdm run pytest-root scripts/tests/test_eng5_np_runner.py -k schema` if artefact
   shape changes.
2. **Manifest**: `jq '.validation.manifest' assessment_run.execute.json` should list every file under
   `requests/` and `events/` with SHA256 digests.
3. **Runner status**: check `validation.runner_status.partial_data` – should be `false`. If `true`,
   rerun with a higher `--completion-timeout` after confirming CJ/LLM logs.
4. **Cost sanity**: review the CLI summary or `costs.token_counts` inside the artefact to ensure
   providers/models match expectations.

## Failure Modes & Recovery

| Symptom | Likely Cause | Action |
| --- | --- | --- |
| Runner exits with `Missing prompt hash` | Queue processor failed before hashing | Inspect LLM provider logs; ensure error callbacks now include `prompt_sha256`. Re-run once provider issue resolved. |
| Timeout with partial artefact | CJ pipeline slow or callbacks dropped | Bump `--completion-timeout`, watch Kafka lag, confirm `CJAssessmentCompletedV1` emitted. Artefact records `runner_status.partial_data=true` for forensic tracking. |
| Schema validation fails | Inputs folder missing anchors/students or files unreadable | Re-sync role-model assets. Stub creation now surfaces warnings for missing files; fix before execute rerun. |
| Duplicate comparisons in artefact | Should no longer occur (dedupe guard). If observed, clear `.claude/research/data/eng5_np_2016/events` and rerun to isolate offending callback. |

## Artefact Locations

- Requests: `.claude/research/data/eng5_np_2016/requests/`
- Events: `.claude/research/data/eng5_np_2016/events/{comparisons,assessment_results,completions}`
- Summary JSON: `.claude/research/data/eng5_np_2016/assessment_run.execute.json`

Keep this runbook updated as ENG5 tooling evolves (e.g., new overrides, different cost reporting).
