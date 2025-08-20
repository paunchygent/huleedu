# T014 — ELS Repository and Service Results SRP/DDD Refactor

## Context

The Essay Lifecycle Service has two large modules that concentrate multiple concerns:

- `services/essay_lifecycle_service/implementations/essay_repository_postgres_impl.py` (~1062 LoC)
- `services/essay_lifecycle_service/implementations/service_result_handler_impl.py` (~858 LoC)

They currently mix responsibilities across connection/session lifecycle, schema bootstrap, data mapping, CRUD and query operations, idempotency workflows, event-orchestration, tracing, and batch completion coordination. This violates SRP and increases cognitive load, making the code harder to evolve and test.

This task performs a clean refactor aligned with our architectural mandates (Rules 010, 020, 030, 042, 048, 050), keeping the public Protocols and DI contracts intact while splitting responsibilities into focused modules. We explicitly avoid rollback strategies, legacy pathways, or temporary compatibility layers.

## Goals

- Enforce SRP within ELS persistence and event result handling layers.
- Preserve the public interfaces: `EssayRepositoryProtocol` and `ServiceResultHandler`.
- Move infra/bootstrap concerns to DI and APP-scoped providers per Rule 042.
- Separate read vs write responsibilities (CQRS-lite) inside the repository implementation.
- Keep orchestration separate from domain transitions via `EssayStateMachine`.
- Maintain structured error handling and metrics instrumentation.

## Non-Goals

- No rollback plan, legacy shims, or backward-compat layers for old module paths.
- No changes to event contracts or Kafka topics.
- No redesign of domain types or state machine semantics.

## End-State Architecture (High-Level)

Public contracts remain unchanged:

- `services.essay_lifecycle_service.protocols.EssayRepositoryProtocol`
- `services.essay_lifecycle_service.protocols.ServiceResultHandler`

Implementation is split by concern:

1) Repository (Infrastructure Layer)

- `implementations/repository/postgres_repository.py` (facade implementing the Protocol; delegates)
- `implementations/repository/session_and_monitoring.py` (engine/session/metrics wiring; APP scope)
- `implementations/repository/bootstrap.py` (schema init + test bootstrap helpers; APP scope)
- `implementations/repository/mappers.py` (DB↔domain mapping)
- `implementations/repository/queries_read.py` (read operations; CQRS-lite)
- `implementations/repository/queries_write.py` (mutations)
- `implementations/repository/idempotency_ops.py` (content idempotency + slot assignment)

2) Service Results (Application Layer)

- `implementations/service_results/spellcheck_handler.py`
- `implementations/service_results/cj_handler.py`
- `implementations/service_results/nlp_handler.py`
- `implementations/service_results/state_transition.py` (build machine + trigger)
- `implementations/service_results/metadata_utils.py` (merge/normalize processing metadata)
- Optional: `implementations/service_results/uow.py` (minimal UoW helpers if beneficial)

`DefaultServiceResultHandler` remains the façade but delegates to the modules above.

## Scope of Changes

1) Repository Refactor

- Extract engine/session/metrics to `session_and_monitoring.py` (APP-scoped provider in DI)
- Extract schema init and test-only bootstrap SQL to `bootstrap.py` (APP-scoped, called in DI)
- Keep `PostgreSQLEssayRepository` as a thin façade in `postgres_repository.py`, injected with `async_sessionmaker` from DI (stop creating engine inside the class)
- Move mapping helpers to `mappers.py`
- Split reads into `queries_read.py` and writes into `queries_write.py`
- Move content idempotency/slot-assign flows to `idempotency_ops.py`

2) Service Result Handling Refactor

- Keep `DefaultServiceResultHandler` signatures; move logic:
  - Spellcheck → `spellcheck_handler.py`
  - CJ Assessment (completed/failed) → `cj_handler.py`
  - NLP completion → `nlp_handler.py`
  - Shared: state machine build/trigger, metadata utilities
- Remove any HTTP-coupling (e.g., `current_app.tracer` checks); prefer injected tracer or OTEL global tracer from DI where available.

3) DI Adjustments (Rule 042)

- Provide `AsyncEngine` and `async_sessionmaker` at APP scope (already present, verify usage)
- Call `bootstrap.initialize_db_schema` in DI startup path (APP scope) where applicable
- Provide the repository façade with injected `session_factory` (instead of self-creating engine)
- Keep `ServiceResultHandler` provider but construct it with delegates (or pass delegates into its constructor)

## Acceptance Criteria

- Public Protocols unchanged (`EssayRepositoryProtocol`, `ServiceResultHandler`)
- `DefaultServiceResultHandler` class remains importable at its current path
- Repository implementation moved under `implementations/repository/` with the façade class implementing the Protocol
- Service result handling split into event-specific modules; façade delegates
- No references to engine creation inside the repository façade
- DI providers instantiate engine/session and inject them into repository façade
- Structured errors and metrics remain active
- All tests pass: `pdm run test-all`
- Linting/type checks pass: `pdm run lint` and `pdm run typecheck-all`

## Implementation Plan

1) Prepare repository module structure

- Create `implementations/repository/` package with the files listed above
- Move code from `essay_repository_postgres_impl.py` into the appropriate modules
- Convert `PostgreSQLEssayRepository` to depend on DI-provided `async_sessionmaker`
- Remove engine creation and monitoring from the class; wire via DI

2) Prepare service results structure

- Create `implementations/service_results/` package and move per-event logic
- Add `state_transition.py` and `metadata_utils.py` for shared concerns
- Refactor `DefaultServiceResultHandler` to delegate to the new modules

3) Update DI providers

- Ensure APP-scoped engine and session factory providers are used by repository façade
- Move schema bootstrap (and test helpers) to DI bootstrap path via `bootstrap.py`
- Inject tracer via DI where needed (fall back to global OTEL tracer), avoid HTTP app context

4) Validate

- Run `pdm run lint`, `pdm run typecheck-all`, and `pdm run test-all`
- Verify event routes (`batch_command_handlers.py`) and `worker_main.py` continue to operate
- Scan for any imports that still point to old monolith modules and update them

## Risks and Considerations

- Large file moves will impact import paths; we are intentionally not adding legacy re-exports to avoid back-compat layers in this prototype.
- Keep transaction boundaries consistent: repository methods continue to accept `session` for UoW orchestration by handlers.
- Maintain the “no business data persistence in ELS for CJ” rule; only state/metadata changes.

## Follow-ups (Optional, Not Required for This Task)

- Consider introducing a separate Query Protocol if read models grow further (explicit CQRS boundary).
- Add contract tests around repository façade to lock behavior.
