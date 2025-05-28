# CLAUDE AI Agent Directives for HuleEdu (DDD/EDA Microservices)

- CRITICAL: Consult `.cursor/rules/` BEFORE ANY TASK (`000-rule-index.mdc`). Rules are NON-NEGOTIABLE.
- Adhere strictly to DDD/EDA microservice architecture. No "vibe coding" or deviations.
- Tech Stack: Python 3.11+, Quart, PDM monorepo, Pydantic (v2 standards, `051`), Kafka, Docker.
- Services: batch_orchestrator, content, spell_checker (active); essay (placeholder). Common Core for shared models/events.
- Development Workflow: Use PDM monorepo. MANDATORY QA: `pdm run format-all`, `lint-all`, `typecheck-all`, `test-all`.

---

- Utilize modes defined in `.cursor/rules/110.x-*.mdc`.
- Follow `.cursor/rules/050-python-coding-standards.mdc` (Strict Typing, DI via Protocols/Dishka, Ruff compliance).
- Implement Unit, Contract, Integration, E2E tests (`.cursor/rules/070-testing-and-quality-assurance.mdc`). Run with `pdm run test-all`.
- Use `common_core.events.EventEnvelope` per `.cursor/rules/030-event-driven-architecture-eda-standards.mdc`. Thin events principle.
- Google-style docstrings, update documentation, cite sources `file:start-end:path` (`.cursor/rules/090-documentation-standards.mdc`).
- Agents are network-disabled. SKIP network-dependent tasks (PyPI, Kafka/DB conn, external APIs, CI/CD). Document skipped parts, defer to network-enabled agents. COMPLETE local tasks.
- No access to `.env*` or sensitive files. Respect `.gitignore`. No secrets in code/logs. Sandbox is read-only with explicit write approval.
- Check rules (`110.4`), Tests, Linting, Types. Use proper exception handling.

---

- Project Context: Phase 1.2 (Testing, observability, refinements). Key Concepts: BatchUpload, ProcessedEssay, EssayStatus, EventEnvelope, Contract. Service Responsibilities: Batch Orchestrator, Content, Spell Checker, Essay (placeholder), Common Core.
- Success: Rules + Quality Gates pass, Docs updated, Tests cover changes, Architecture maintained, Code Review Ready (Typing, Error Handling, Logging w/ correlation ID, Pydantic Contracts).
