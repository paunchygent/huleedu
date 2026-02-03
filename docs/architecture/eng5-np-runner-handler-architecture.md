---
type: design
id: eng5-np-runner-handler-architecture
title: ENG5 NP Runner Handler Architecture & Alignment Harness
created: 2025-11-29
last_updated: 2026-02-03
---

# ENG5 NP Runner Handler Architecture & Alignment Harness

## 1. Goals

- Reduce the ENG5 NP runner CLI from a monolithic ~900-line script to a
  handler-based architecture with clear responsibilities per mode.
- Enable isolated prompt-tuning experiments via `anchor-align-test` without
  impacting production CJ flows.
- Make the runner testable via protocol-based dependency boundaries and
  small, focused unit and CLI integration tests.

## 2. High-Level Structure

Key modules (under `scripts/cj_experiments_runners/eng5_np/`):

- `cli.py` – Typer CLI entrypoint:
  - Parses arguments/options (mode, IDs, URLs, LLM overrides, batching hints).
  - Validates mode-specific preconditions (`assignment_id` required only for
    EXECUTE).
  - Builds `RunnerSettings` and `RunnerPaths`.
  - Collects file inventory via `inventory.collect_inventory`.
  - Dispatches to the appropriate handler from `HANDLER_MAP`.
- `handlers/` – mode-specific handlers:
  - `PlanHandler` – PLAN mode (inventory + validation snapshot).
  - `DryRunHandler` – DRY_RUN mode (stub artefact only).
  - `ExecuteHandler` – EXECUTE mode (DB-owned anchors, full CJ pipeline).
  - `AnchorAlignHandler` – ANCHOR_ALIGN_TEST mode (anchor-only GUEST flow).
- Supporting modules:
  - `inventory.py` – filesystem inventory, comparison capacity validation.
  - `artefact_io.py` – stub artefact writing and anchor grade map loading.
  - `kafka_flow.py` – Kafka publish helpers and hydrator integration.
  - `requests.py` – ENG5 CJ request composition and envelope writing.
  - `alignment_report.py` – anchor alignment report generation.

The CLI is intentionally thin; handler classes own orchestration logic and
call into the lower-level modules above.

## 3. Handler Protocol Contract

`protocols.ModeHandlerProtocol` defines the contract for all handlers:

```python
class ModeHandlerProtocol(Protocol):
    def execute(
        self,
        settings: RunnerSettings,
        inventory: RunnerInventory,
        paths: RunnerPaths,
    ) -> int: ...
```

Requirements:

- Handlers MUST be instantiable without arguments and implement `execute`
  with the signature above.
- Handlers MUST NOT mutate `RunnerPaths`.
- Handlers MAY mutate `RunnerSettings` only in ways that are strictly
  internal to the mode (for example temporarily setting `assignment_id=None`
  before composing a GUEST request).
- `execute` MUST return a process-style exit code (0 = success; non-zero =
  failure). The Typer CLI turns this into a `typer.Exit` code.

Contract tests assert that each handler instance is `isinstance(handler,
ModeHandlerProtocol) is True` and that `execute` returns an integer exit code.

## 4. Mode Semantics

### 4.1 PLAN

- Reads ENG5 inventory (instructions, prompt, anchors, students).
- Logs and prints a human-readable inventory snapshot.
- Writes a lightweight validation state via `log_validation_state`, with
  `runner_status.mode="plan"` and counts for anchors/students.
- Performs no network I/O and no Kafka publish.

### 4.2 DRY_RUN

- Ensures the ENG5 JSON schema is available via
  `schema.ensure_schema_available(paths.schema_path)`.
- Writes a stub artefact containing validation/manifest structure only
  (no CJ requests or events).
- Logs validation state and prints the stub artefact path.
- Performs no Kafka publish and does not upload essays.

### 4.3 EXECUTE (DB-Owned Anchors)

Responsibilities:

- Validate execute prerequisites:
  - Instructions file exists.
  - Prompt file exists **only when** running without `assignment_id` (assignment-bound runs
    use CJ-owned `student_prompt_storage_id`).
  - At least one student essay is present.
  - `CJ_SERVICE_URL` is configured (flag or env).
- Execute-time preflight is CJ-admin driven (performed in the CLI before handler dispatch):
  - Resolve `assessment_instructions` to fetch `grade_scale`, `context_origin`, and prompt storage.
  - Fail if the assignment lacks a `student_prompt_storage_id`.
  - Resolve anchor summary to ensure anchors exist for the assignment grade_scale.
- Create stub artefact and, if `await_completion` and `use_kafka` are set,
  instantiate an `AssessmentRunHydrator` to capture results.
- Upload student essays to Content Service using `upload_essays_parallel`.
- Upload the prompt only when `assignment_id` is **not** set; assignment-bound
  runs rely on the CJ-owned prompt reference.
- Compose a CJ assessment request (student essays only; anchors are DB-owned) and
  write the request envelope to disk.
- Publish to Kafka:
  - If `await_completion=True` and `use_kafka=True`, run
    `run_publish_and_capture` and log a structured run summary.
  - If `await_completion=False`, publish once and exit after logging.
  - If `use_kafka=False`, log and skip publishing.

### 4.4 ANCHOR_ALIGN_TEST (GUEST Flow)

Responsibilities:

- Require at least one anchor essay; treat missing anchors as a hard error.
- Accept optional `--system-prompt` and `--rubric` file paths:
  - Validate existence and non-empty content.
  - Load contents and set `settings.system_prompt_text` /
    `settings.rubric_text`.
  - Build `LLMConfigOverrides` with prompt/rubric overrides; this is the
    primary way prompt experiments are expressed.
- Create stub artefact and optional hydrator as in EXECUTE.
- Upload anchor essays to Content Service and treat them as **students** when
  building `EssayProcessingInputRefV1`:
  - `anchors=[]`, `students=anchor_files` in `build_essay_refs`.
  - This ensures CJ sees a pure anchor-only cohort without DB-owned anchors.
- Temporarily set `settings.assignment_id=None` before composing the request:
  - This triggers CJ GUEST behavior (no grade projection, no DB anchor
    hydration).
  - The original assignment ID is restored immediately after composing the
    envelope for logging consistency.
- Compose and write the CJ request envelope; publish to Kafka as in EXECUTE.
- When `await_completion=True` and Kafka callbacks complete:
  - Generate an alignment report via `alignment_report.generate_alignment_report`.
  - Log and print the report path.

## 5. Alignment Report Schema & Metrics

`alignment_report.generate_alignment_report` consumes:

- `hydrator.get_run_artefact()` – ENG5 artefact with:
  - `bt_summary`: per-essay BT scores and ranks.
  - `llm_comparisons`: head-to-head comparison records with winner/loser,
    confidence, and justification.
- `anchor_grade_map`: mapping from anchor ID → expert grade.
- Prompt and rubric text (for reproducibility).

The report contains:

- Summary metrics:
  - `total_comparisons`
  - `direct_inversions` – count of head-to-head cases where a lower expert
    grade beats a higher expert grade.
  - `zero_win_anchors` – count of anchors with no comparison wins.
  - `kendall_tau` – rank correlation coefficient between expected (expert)
    ranks and BT ranks.
- Per-anchor table:
  - Anchor ID, expert grade, BT score, actual rank, expected rank, wins,
    losses, win rate.
- Inversion table (when applicable):
  - Higher-grade anchor, lower-grade anchor, winner, confidence,
    truncated justification.
- Prompt appendices:
  - System prompt text.
  - Judge rubric text.

The corresponding unit tests in
`scripts/cj_experiments_runners/eng5_np/tests/unit/test_alignment_report.py`
are the executable spec for these semantics.

## 6. Testing Strategy

- **Unit Tests**
  - Alignment report functions and data classes.
  - Handler `execute` methods:
    - Happy-path behavior (exit code, logging hooks, stub artefact creation).
    - Key error paths (missing anchors preflight, missing prompt, missing CJ URL).
  - Protocol contract tests for handlers and core dependency protocols
    (ContentUploaderProtocol, AnchorRegistrarProtocol, KafkaPublisherProtocol,
    HydratorProtocol, ReportGeneratorProtocol) where applicable.

- **CLI Integration Tests**
  - Typer `CliRunner` tests for:
    - Basic PLAN/DRY_RUN invocations.
    - Mode-specific validation (e.g. EXECUTE requires `--assignment-id` and
      `--course-id`; ANCHOR_ALIGN_TEST accepts missing `--assignment-id`).
    - Propagation of exit codes from handlers.

## 7. Future Extensions

- Consider extracting shared upload/publish helpers used by EXECUTE and
  ANCHOR_ALIGN_TEST into a small orchestration module to reduce duplication.
- Add a how-to under `docs/how-to/` for running ENG5 prompt-tuning campaigns
  end-to-end (from prompt variant selection to alignment report comparison).
- If additional modes are introduced (e.g. regression replays, synthetic data
  runs), extend `ModeHandlerProtocol` and `HANDLER_MAP` while keeping handler
  responsibilities focused and testable.
