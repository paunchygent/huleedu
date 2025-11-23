---
id: "111-cloud-vm-execution-standards"
type: "operational"
created: 2025-11-10
last_updated: 2025-11-17
scope: "all"
---
# 111: Claude Cloud VM Execution Standards

## 1. Scope & Objectives
- Applies to all Claude Code cloud (web) sessions operating inside the managed Ubuntu 24.04 VM.
- Ensures consistency with repository tooling and highlights hard limitations (no Docker/services).
- Supplements, but does not replace, core workflow rules (`000`, `110.x`, `090`).

## 2. Environment Baseline
- **User/Shell**: `root`, `/bin/bash`
- **Repo Root**: `/home/user/huledu-reboot`
- **Python**: 3.11.14 with `.venv/`
- **PDM**: 2.26.1 (add `/root/.local/bin` to `PATH` before invoking)
- **Git**: Feature branch `claude/...` via proxy remote; commit/push to assigned branch only.

## 3. Supported Capabilities
1. **Python Tooling**
   - Prefer `.venv/bin/python` and `.venv/bin/pytest` for execution.
   - Export PATH before PDM commands: `export PATH=$PATH:/root/.local/bin && pdm <command>`.
   - Valid scripts: `pdm run format-all`, `lint-fix`, `lint-all`, `typecheck-all`.
2. **Testing**
   - Run unit/integration tests (non-Docker) via `.venv/bin/pytest <path> -v`.
   - Use markers to skip Docker/e2e suites (`-m "not docker and not e2e"`).
3. **File & Repo Operations**
   - Use IDE tooling (Read, Edit, Write, Grep, Glob) for file access/modification.
   - Git commands (`status`, `diff`, `add`, `commit`, `push`) are fully functional.

## 4. Prohibited / Failing Actions
- Docker-dependent workflows (`pdm run dev-*`, `prod-*`, `db-*`, `docker compose`, `docker run`) always fail.
- Services, databases, Kafka, or Redis cannot be started; no external network services.
- `.env` secrets unavailable; tests depending on real credentials must be skipped or adapted.

## 5. Required Workflow
1. **Startup Checklist**
   - Confirm repo root (`pwd`), review `git status`, read relevant task docs (`CLAUDE.md`, `000-rule-index`, `HANDOFF`, `README_FIRST`).
2. **Implementation / Review Loop**
   - Investigate with IDE tools → modify code → run format/lint/typecheck → execute targeted pytest suites → document updates per Rule `090` → commit and push.
3. **Bug Investigation**
   - Reproduce via `.venv/bin/pytest <nodeid> -v --tb=short`, inspect history (`git log`, `git blame`), confine fixes to root cause without Docker assumptions.
4. **Communication**
   - Proactively state Docker/service limitations when tasks request disallowed operations and propose lint/type/test alternatives.

## 6. Validation & Troubleshooting
- PATH issues: print `echo $PATH`; call `/root/.local/bin/pdm` directly if required.
- Missing tests: verify relative paths, list files, or run single-node identifiers.
- Document any newly discovered limitations in task notes and propose rule updates if standards evolve.

---
**Last Reviewed:** 2025-11-09
