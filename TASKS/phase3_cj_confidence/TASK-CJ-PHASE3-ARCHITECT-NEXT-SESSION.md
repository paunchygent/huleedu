# Task: Phase 3 – Architect Session (ENG5 NP Data Capture)

- **Date Prepared**: 2025-11-09
- **Owner**: Lead Architect Agent
- **Session Scope**: One working session (~3–4 focused hours)
- **Phase Context**: Phase 3.3 – Batch Tooling & Data Capture (feeds TASK-CJ-CONFIDENCE-PHASE3-GRADE-SCALE-DATA-PIPELINE.md)

## 1. Objective

Ensure the ENG5 NP runner’s event-driven pipeline is architecturally complete so a single execute-mode run can emit schema-compliant artefacts without manual patching or missing metadata. This session should leave the runner ready for downstream statistical validation (Phase 4) by guaranteeing deterministic inputs/outputs and observability for LLM cost tracking.

## 2. Desired Outcome

By session end we should have:

1. **Metadata integrity**: `LLMComparisonResultV1.request_metadata` always carries `essay_a_id`, `essay_b_id`, and `prompt_sha256`, and the runner treats their absence as a hard fault (no silent skips).
2. **Artefact completeness**: `assessment_run.execute.json` includes fully populated `llm_comparisons`, `bt_summary`, `grade_projections`, and `costs` sections that align with `Documentation/schemas/eng5_np/assessment_run.schema.json`.
3. **Operational runbook**: Documented checklist for executing `pdm run eng5-np-run --mode execute` against the dev stack, including how to verify Kafka consumers, metrics, and manifest outputs.

## 2.1 Current Progress (2025-11-09)

- CJ service and LLM provider callbacks now propagate `essay_a_id`, `essay_b_id`, and `prompt_sha256`; unit coverage in the admin/interaction suites confirms the metadata contract.
- `AssessmentEventCollector` and `AssessmentRunHydrator` enforce metadata presence, halt consumption on missing fields, and hydrate artefacts (comparisons, BT summary, grade projections, cost rollups) using the modularized runner package.
- ENG5 runner (`pdm run eng5-np-run`) supports plan/dry-run/execute modes, maintains manifest hashing, and writes schema-aligned stubs; documentation and Grafana playbook entries cover admin/JWT enablement and metadata counters.

## 2.2 Immediate Next Steps

1. Execute runner dry-run validation and full execute-mode capture to generate ENG5 artefacts per schema, retaining events/requests in the manifest.
2. Expand tests to cover ENG5 legacy vs national scale flows, JSON artefact schema validation, and non-mutating DB behavior for the runner.
3. Finalize operational guidance by adding the execute-mode checklist and monitoring cues to the README/runbook, including completion timeout handling and rerun guidance.

## 3. Critical Decisions & Considerations

| Area | Decision Points | Considerations |
| --- | --- | --- |
| Metadata propagation | Do we enforce metadata at CJ ingestion or at LLM Provider callbacks (or both)? | CJ service now injects IDs + prompt text; confirm queue/job layers do not strip optional fields. Decide whether `prompt_sha256` is computed once (CJ) or re-derived at provider publish time for trust. |
| Kafka consumer strategy | Should the runner stop after `AssessmentResultV1` or wait for explicit `CJAssessmentCompletedV1` confirmation? | Need timeout/partial-data behavior to avoid hanging sessions; ensure idempotent writes when events arrive late. |
| Artefact manifest | Which files are hashed in `manifest.json` and how to handle re-runs? | Keep deterministic ordering; specify retention policy for raw events vs derived artefacts. |
| Observability | Which metrics/logs confirm metadata coverage and artefact hydration? | Coordinate with `Documentation/OPERATIONS/01-Grafana-Playbook.md` counters (`huleedu_llm_prompt_fetch_failures_total`, `cj_admin_instruction_operations_total`) and add runner-side logging (cost summaries, prompt hash stats). |
| Failure modes | How should the runner surface partial captures or schema validation failures? | Prefer fail-fast with actionable error messages; emit `manifest_status` flags in artefact validation block. |

## 4. Next-Session Implementation Steps

1. **Verify metadata end-to-end**
   - Inspect `services/cj_assessment_service/implementations/llm_interaction_impl.py` and `services/llm_provider_service/implementations/queue_processor_impl.py` to confirm they pass through `essay_a_id`, `essay_b_id`, and `prompt_sha256`.
   - Add assertions/unit tests if any layer still drops these fields (use `services/cj_assessment_service/tests/unit/test_callback_state_manager*.py` and `services/llm_provider_service/tests` harnesses).

2. **Enforce strict handling in runner**
   - Update `scripts/cj_experiments_runners/eng5_np/hydrator.py` so `_build_comparison_record` raises a descriptive exception (or toggled failure flag) when metadata is missing.
   - Ensure `scripts/cj_experiments_runners/eng5_np/kafka_flow.py` stops consumption if hydrator signals an error; wire this into CLI exit codes.

3. **Schema validation & artefact completeness**
   - Run `pdm run eng5-np-run --mode dry-run --no-kafka` to regenerate artefact stubs, then validate them against `Documentation/schemas/eng5_np/assessment_run.schema.json` via `scripts/tests/test_eng5_np_runner.py` (or add a new CLI smoke test node).
   - Confirm manifest entries include new modular paths (events/, requests/). Update `scripts/cj_experiments_runners/eng5_np/artefact_io.py` if ordering or hashing logic needs tweaks.

4. **Operational playbook updates**
   - Capture the exact command sequence for execute mode (Docker pre-checks, env sourcing, Kafka bootstrap config) and add it to `services/cj_assessment_service/README.md` or a new subsection under `Documentation/OPERATIONS/01-Grafana-Playbook.md`.
   - Note monitoring hooks (Prometheus counters, Kafka consumer lag) architects/TestOps should watch during long-running batches.

## 5. Critical Files & References

- **Runner package**: `scripts/cj_experiments_runners/eng5_np/`
  - `cli.py` – Typer entrypoint and manifest validation.
  - `kafka_flow.py` – `AssessmentEventCollector` and publish/capture orchestration.
  - `hydrator.py` – Artefact hydration + cost accounting.
  - `events.py`, `artefact_io.py`, `requests.py`, `paths.py`, `settings.py` – supporting utilities.
- **Schema & docs**:
  - `Documentation/schemas/eng5_np/assessment_run.schema.json`
  - `Documentation/OPERATIONS/01-Grafana-Playbook.md` (prompt hydration + ENG5 monitoring section).
- **Service pipelines**:
  - `services/cj_assessment_service/implementations/llm_interaction_impl.py`
  - `services/cj_assessment_service/metrics.py`
  - `services/llm_provider_service/implementations/queue_processor_impl.py`
- **Tests**:
  - `scripts/tests/test_eng5_np_runner.py`
  - `services/cj_assessment_service/tests/integration/test_llm_provider_manifest_integration.py`

## 6. Risks & Mitigations

- **Partial event capture**: If Kafka callbacks arrive late, artefacts may miss comparisons. Mitigation: add `completion_timeout` telemetry + rerun guidance.
- **Schema drift**: Multiple contributors editing schema/runner independently can desynchronize fields. Mitigation: enforce `jsonschema` validation in runner tests.
- **Cost overruns**: Execute mode may hit real LLMs; ensure `--no-kafka` and mock toggles are clearly documented for dry runs.

---

**Call to Action**: Use this task to align engineering and data science expectations before executing another ENG5 NP batch. The lead architect should confirm or adjust the decisions above, then green-light the implementation steps for the next engineering session.
