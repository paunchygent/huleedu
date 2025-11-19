---
id: "logging-file-persistence-and-docker-config"
title: "Logging File Persistence & Docker Configuration"
type: "task"
status: "complete"
priority: "high"
domain: "infrastructure"
service: "platform"
owner_team: "agents"
owner: ""
program: ""
created: "2025-11-19"
last_updated: "2025-11-19"
completed: "2025-11-19"
related:
  - ".claude/research/validation/logging-persistence-audit-2025-11-19.md"
  - ".claude/research/validation/logging-configuration-investigation-2025-11-19.md"
  - ".claude/work/session/handoff.md"
labels: []
---

# TASK-LOGGING-FILE-PERSISTENCE-AND-DOCKER-CONFIG – Logging Persistence, Docker Drivers & ENG5 Runner

This task captures the follow-up work from the 2025-11-19 logging audit and review.
It builds on:

- `.claude/research/validation/logging-persistence-audit-2025-11-19.md`
- `.claude/research/validation/logging-configuration-investigation-2025-11-19.md`
- `.claude/work/session/handoff.md` (Logging Audit section)

The goal is to:

- Finalize **Result Aggregator** logging settings usage.
- Add unit tests for **file-based logging** in `logging_utils.py`.
- Wire **Docker logging drivers** across services.
- Add **ENG5 runner** file logging and update documentation.

---

## PR 1 – Result Aggregator Settings Logging Cleanup

**Goal:** Align Result Aggregator Service logging configuration with standard settings
patterns by reusing the existing `settings` singleton instead of instantiating a
separate `Settings()` instance only for logging.

**Status:** ✅ Complete (2025-11-19)

### Files

- `services/result_aggregator_service/app.py` (modified: lines 22, 32)
- `services/result_aggregator_service/config.py` (reference only)

### Checklist

- **Logging configuration reuse**
  - **[✅]** Replace module-level `_settings = Settings()` usage in
    `services/result_aggregator_service/app.py` with the existing shared
    `settings` instance:
    - Import: `from services.result_aggregator_service.config import settings`.
    - Call `configure_service_logging("result_aggregator_service", log_level=settings.LOG_LEVEL)`.
  - **[✅]** Ensure no duplicate `Settings()` instantiations are left in the
    module solely for logging configuration.

- **Consistency with other services**
  - **[✅]** Confirm the final pattern matches existing services such as
    Batch Orchestrator, Content, File, and CJ Assessment (top-level
    `configure_service_logging(..., log_level=settings.LOG_LEVEL)` followed
    by `create_service_logger(...)`).

- **Validation**
  - **[✅]** Run `pdm run format-all` from repo root.
  - **[✅]** Run `pdm run lint-fix --unsafe-fixes` from repo root.
  - **[✅]** Run `pdm run typecheck-all` from repo root.
  - **[✅]** Run a focused test subset for Result Aggregator (if present) via
    `pdm run pytest-root services/result_aggregator_service/tests`.

---

## PR 2 – File-Based Logging Unit Tests (logging_utils)

**Goal:** Add unit tests that validate file-based logging behavior in
`configure_service_logging()`, including environment variable parsing,
path handling, directory creation, and rotation settings.

**Status:** ✅ Complete (2025-11-19)

### Files

- `libs/huleedu_service_libs/src/huleedu_service_libs/logging_utils.py`
- `libs/huleedu_service_libs/tests/test_logging_utils_file_handler.py` (created - 310 LoC)
- `libs/huleedu_service_libs/tests/test_jwt_settings.py` (fixed pre-existing test failure)

### Checklist

- **Test scaffolding**
  - **[✅]** Create new test module:
    - `libs/huleedu_service_libs/tests/test_logging_utils_file_handler.py` (placed in tests/ root per project structure).
  - **[✅]** Use `tmp_path` or an equivalent temporary directory fixture to
    avoid polluting the real filesystem.

- **Default behavior (no file logging)**
  - **[✅]** Test that when `LOG_TO_FILE` is unset/false and `log_to_file` is
    left as `None`, `configure_service_logging("test-service", log_level="INFO")`:
    - Configures logging successfully.
    - Does **not** create any log file under the temp directory.

- **Env-driven file logging**
  - **[✅]** With environment variables set (using monkeypatch):
    - `LOG_TO_FILE=true`.
    - `LOG_FILE_PATH` pointing inside the temporary directory.
    - `LOG_MAX_BYTES` and `LOG_BACKUP_COUNT` set to small values.
  - **[✅]** Call `configure_service_logging("test-service", log_level="INFO")` and
    emit at least one log line via `create_service_logger("test")`.
  - **[✅]** Assert that:
    - The log file exists at `LOG_FILE_PATH`.
    - The parent directory was created (if it did not exist before).
    - Rotation settings (`maxBytes`, `backupCount`) match env values.

- **Explicit argument override**
  - **[✅]** Test that passing `log_to_file=True` and `log_file_path` explicitly
    works even when environment variables are not set, and that the file
    is created under the specified path.

- **Idempotent configuration**
  - **[✅]** Call `configure_service_logging()` twice in a row and emit logs
    each time; assert that logging still works and that log files are not
    duplicated in unexpected locations (baseline check that `force=True`
    in `logging.basicConfig` behaves as intended in this context).

- **Validation**
  - **[✅]** Run `pdm run pytest-root libs/huleedu_service_libs/tests/test_logging_utils_file_handler.py` (11/11 passed).
  - **[✅]** Run `pdm run typecheck-all` (1271 files, success).

---

## PR 3 – Docker Compose Logging Drivers (json-file)

**Goal:** Apply the shared `x-logging: &default-logging` anchor to all
application services in `docker-compose.services.yml` and development services in
`docker-compose.dev.yml` to enforce bounded `json-file` logging with rotation
and compression.

**Status:** ✅ Complete (2025-11-19)

### Files

- `docker-compose.services.yml` (modified: added logging to 19 services)

### Checklist

- **Production/services compose**
  - **[✅]** For each service under `services:` in `docker-compose.services.yml`,
    add:
    - `logging: *default-logging`
    - Ensure indentation and YAML structure remain correct.
  - **[✅]** Verify there are no conflicting `logging:` entries for any
    service.

- **Development compose**
  - **[✅]** Dev services retain unbounded logging per user preference (for debugging flexibility)

- **Validation**
  - **[✅]** Run `docker compose -f docker-compose.yml -f docker-compose.services.yml config`
    to validate YAML and merged configuration.

---

## PR 4 – ENG5 Runner File Logging

**Goal:** Add file-based logging to the ENG5 NP runner execute mode so that
serial-bundle validation runs and production-like ENG5 batches have
persistent logs on disk.

**Status:** ✅ Complete (2025-11-19)

### Files

- `scripts/cj_experiments_runners/eng5_np/logging_support.py` (added configure_execute_logging)
- `scripts/cj_experiments_runners/eng5_np/cli.py` (conditional logging + user notification)
- `scripts/cj_experiments_runners/eng5_np/tests/test_logging_integration.py` (6 tests created)

### Checklist

- **Log file path & naming**
  - **[✅]** Define a log file path pattern for execute mode runs:
    - `.claude/research/data/eng5_np_2016/logs/eng5-{batch_id}-{timestamp}.log`
  - **[✅]** Ensure the parent directory is created with
    `mkdir(parents=True, exist_ok=True)` before the handler is attached.

- **File handler integration**
  - **[✅]** In `cli.py`, for `--mode execute` only, extend the existing
    logging setup (via `logging_support.configure_service_logging` or
    equivalent) to:
    - Add a `RotatingFileHandler` pointing at the computed log file path.
    - Keep stdout logging unchanged for real-time feedback.
  - **[✅]** Reuse the same rotation defaults as services where practical
    (`LOG_MAX_BYTES`, `LOG_BACKUP_COUNT`) or define ENG5-specific safe
    defaults.

- **User visibility**
  - **[✅]** CLI displays log file location when execute mode starts
  - **[✅]** Help text documents file logging feature

- **Validation**
  - **[✅]** Created 6 integration tests (all passing):
    - Directory creation, filename pattern, structured logs, rotation settings, verbose/info levels
  - **[✅]** Tests validate service-standard rotation (100MB/10 files)

---

## PR 5 – Documentation & Rule Updates

**Goal:** Document the new logging behavior (file logging, Docker drivers,
ENG5 runner logging) in service READMEs and update logging standards.

**Status:** ✅ Complete (2025-11-19)

### Files

- `.claude/rules/043-service-configuration-and-logging.md` (added section 3.2)
- `docs/operations/01-grafana-playbook.md` (added Loki access section)

### Checklist

- **Service-level docs**
  - **[✅]** Per user preference: Documentation in rules and docs/ only (not service READMEs)

- **Rule 043 update**
  - **[✅]** Add a "File-based logging" subsection (3.2) describing:
    - The optional nature of file logging.
    - Standard environment variables (LOG_TO_FILE, LOG_FILE_PATH, LOG_MAX_BYTES, LOG_BACKUP_COUNT).
    - Expected default behavior (stdout-only when disabled).
    - Docker logging interaction (stdout → json-file → Promtail → Loki).

- **Observability & Loki**
  - **[✅]** Added to Grafana playbook:
    - Loki access via Grafana (port 3000)
    - Log collection pipeline diagram
    - Docker json-file driver configuration (100MB × 10 files)
    - Common LogQL query patterns

- **Validation**
  - **[✅]** Run `pdm run format-all` and `pdm run lint-fix --unsafe-fixes` to
    ensure docs and any incidental code snippets remain clean.

---

## Implementation Status Summary (Initial)

### Current

- Centralized logging configuration (`configure_service_logging` and
  `create_service_logger`) is implemented and reviewed.
- File-based logging support with `RotatingFileHandler` is implemented and
  opt-in via environment variables.
- Three historically inconsistent services (API Gateway, LLM Provider,
  Result Aggregator) have been updated to call `configure_service_logging`.
- Docker `x-logging` anchor is defined in `docker-compose.services.yml` but
  not yet applied to all services.

### Remaining

- Result Aggregator settings reuse cleanup (PR 1).
- File-based logging unit tests (PR 2).
- Docker logging wiring for all services (PR 3).
- ENG5 runner file logging for execute mode (PR 4).
- Documentation and rule updates (PR 5).

---

## Success Criteria

- Result Aggregator Service uses the shared `settings` instance for logging
  configuration without duplicate `Settings()` instantiation.
- `configure_service_logging()` is covered by unit tests that validate
  file logging behavior, directory creation, and env var parsing.
- All services in `docker-compose.services.yml` and dev services in
  `docker-compose.dev.yml` use the shared `json-file` logging driver with
  bounded size, rotation, and compression.
- ENG5 NP runner execute mode writes structured logs to per-run files
  under `.claude/research/data/eng5_np_2016/logs/` while preserving
  console output.
- Documentation and rules clearly describe file-based logging, Docker
  logging configuration, and Loki access so operators and developers
  can use the new capabilities confidently.
