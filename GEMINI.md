# HuleEdu Developer Reference

## Golden Rules
1. No vibe-coding: every production behavior change must be grounded in a decision, epic, and story/fix.
2. No legacy/deprecation clutter: this prototype codebase optimizes for clarity and fast iteration.
3. Respect SOLID, YAGNI, DDD, and SRP: leave code cleaner than you found it.
4. Use `.agent/rules/` and `docs/` as the primary source of truth.

## Platform Invariant
- Hemma (`hemma.hule.education`) is the canonical remote deployment and ML offloading platform for HuleEdu.
- Canonical sources:
  - `docs/operations/hemma-server-operations-huleedu.md`
  - `docs/operations/gpu-ai-workloads-on-hemma-huleedu.md`
  - `docs/decisions/0025-hemma-hosted-nlp-feature-offload-for-essay-scoring-research-binary-protocol.md`

## Session Start (Mandatory)
1. Read `.agent/rules/000-rule-index.md`.
2. Read task-relevant rules from the index before making changes.
3. Read `.claude/work/session/handoff.md` and `.claude/work/session/readme-first.md`.
4. Select working mode via `.agent/rules/110-ai-agent-interaction-modes.md`.
5. If introducing/updating third-party dependencies or complex workflows, use Context7 first.
6. For code-review tasks, create `.claude/archive/code-reviews/<what-is-being-reviewed_YYYY_MM_DD>.md` and update it each phase.

## Core Execution Invariants
- Keep command context explicit (local vs remote):
  - Local `pdm run ...` commands: use `pdm run run-local-pdm <script> [args]`
    (wrapper loads `.env`, enforces repo root, then runs `pdm run ...`).
  - Remote Hemma commands: prefer argv mode
    `pdm run run-hemma -- <command> [args]`
    (wrapper enforces `cd /home/paunchygent/apps/huleedu` on Hemma before execution;
    avoids shell quoting/operator drift).
  - Use `--shell "<command>"` only when shell operators are required.
- `./scripts/dev-shell.sh` remains valid for interactive local shells.
- Run `pdm` commands from repo root only.
- After each major task phase, update:
  - active task documents in `TASKS/`
  - `.claude/work/session/handoff.md`
  - `.claude/work/session/readme-first.md`
- Do not run git commands or delete files you did not create without user permission.
- For Hemma/repo alignment, use `git pull` / `git fetch` for tracked files; do not use `scp` for repo code sync.
- If executing inside a container, run `pdm run <command>` from the container root.
- If launching 2+ subagents, launch them in one parallel tool call.

## Documentation and Task Management (Mandatory)
- Use script aliases from `pyproject.toml` (do not call Python modules directly for these workflows).
- Create and maintain work with:
  - `pdm run new-task`
  - `pdm run new-doc`
  - `pdm run new-rule`
- `.claude/work/tasks/` is deprecated; use `TASKS/`.

Canonical validation flow:

```bash
pdm run validate-tasks
pdm run validate-docs
pdm run index-tasks --root "$(pwd)/TASKS" --out "/tmp/huleedu_tasks_index.md" --fail-on-missing
```

Specs:
- `TASKS/_REORGANIZATION_PROPOSAL.md`
- `docs/DOCS_STRUCTURE_SPEC.md`
- `.claude/CLAUDE_STRUCTURE_SPEC.md`

## ML / Essay Scoring Research (Mandatory Defaults)
Canonical runbook and skill:
- `docs/operations/ml-nlp-runbook.md`
- `scripts/codex_skills/essay-scoring-research/SKILL.md`

Mandatory defaults:
- Long runs must be detached (prefer `/usr/bin/screen`) and write driver logs under `output/essay_scoring/`.
- Reuse feature stores after first successful extraction:
  - `run`: `--reuse-feature-store-dir output/essay_scoring/<RUN>/feature_store`
  - `cv` / sweeps: `--reuse-cv-feature-store-dir output/essay_scoring/<CV_RUN>/cv_feature_store`
- For ELLIPSE CV-first runs, always pass canonical inputs:
  - `--ellipse-train-path`
  - `--ellipse-test-path`
  - `--splits-path`
- Track progress via `output/essay_scoring/<RUN>/progress.json` (not log parsing).
- CV runs must produce residual diagnostics:
  - `reports/residual_diagnostics.md`
  - `artifacts/residuals_*.{csv,jsonl}`

## Testing and Quality Gates
- Always run:

```bash
pdm run format-all
pdm run lint-fix --unsafe-fixes
pdm run typecheck-all
```

- Use root-aware tests:

```bash
pdm run pytest-root <path-or-nodeid> [pytest args]
```

- Reference methodology rules:
  - `.agent/rules/075-test-creation-methodology.md`
  - `.agent/rules/075.1-parallel-test-creation-methodology.md`

## Docker Development (Canonical Surface)
Use these script aliases:

```bash
pdm run dev-start [service]
pdm run dev-build [service]
pdm run dev-build-start [service]
pdm run dev-build-clean [service]
pdm run dev-restart [service]
pdm run dev-recreate [service]
pdm run dev-stop [service]
pdm run dev-logs [service]
pdm run dev-check
```

For container debugging patterns, use:
- `.agent/rules/046-docker-container-debugging.md`

## Hemma Remote Development (Condensed)
Canonical references:
- `docs/operations/hemma-server-operations-huleedu.md`
- `docs/operations/gpu-ai-workloads-on-hemma-huleedu.md`
- `docs/operations/hemma-alpha-rollout-days-1-3.md`
- `docs/decisions/0025-hemma-hosted-nlp-feature-offload-for-essay-scoring-research-binary-protocol.md`
- `scripts/codex_skills/huledu-devops-hemma/SKILL.md`

SSH hygiene:
- Run from Hemma repo root: `/home/paunchygent/apps/huleedu`.
- Prefer a single SSH command that includes `cd`, or a heredoc for multi-line sequences.

Examples:

```bash
ssh hemma /bin/bash -c 'cd /home/paunchygent/apps/huleedu && ./scripts/validate-production-config.sh'
```

```bash
ssh hemma /bin/bash -s <<'EOF'
set -euo pipefail
cd /home/paunchygent/apps/huleedu
./scripts/validate-production-config.sh
sudo docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
EOF
```

Tunnels:

```bash
ssh hemma -L 18085:127.0.0.1:8085 -N
ssh hemma -L 19000:127.0.0.1:9000 -N
curl -fsS http://127.0.0.1:18085/healthz
curl -fsS http://127.0.0.1:19000/healthz
```

Long-running Mac-side research jobs:

```bash
/usr/bin/screen -S essay_scoring_run -dm /bin/bash -lc '<command>'
/usr/bin/screen -r essay_scoring_run
/usr/bin/screen -S essay_scoring_run -X quit
```

## Stable Details Offloaded to Rules (Read, Do Not Re-copy Here)
- Architecture and principles: `.agent/rules/010-foundational-principles.md`
- Service boundaries and mandates: `.agent/rules/020-architectural-mandates.md`
- Async patterns and DI: `.agent/rules/042-async-patterns-and-di.md`
- Event contracts: `.agent/rules/052-event-contract-standards.md`
- Database and migrations: `.agent/rules/085-database-migration-standards.md`
- PDM/dependency management: `.agent/rules/081-pdm-dependency-management.md`, `.agent/rules/083-pdm-standards-2025.md`
- Testing standards: `.agent/rules/070-testing-and-quality-assurance.md`, `.agent/rules/075-test-creation-methodology.md`
- Documentation standards: `.agent/rules/090-documentation-standards.md`

## Documentation Standards
- Keep docs in sync with code changes.
- Use Google-style docstrings for public interfaces.
- Document environment variables.
- Include concise examples where useful.
