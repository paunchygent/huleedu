---
id: "roadmap-90-day-execution"
title: "90-Day Execution Roadmap (Alpha ➜ Beta)"
type: "task"
status: "research"
priority: "medium"
domain: "architecture"
service: ""
owner_team: "agents"
owner: ""
program: ""
created: "2025-08-23"
last_updated: "2025-11-17"
related: []
labels: []
---
# 90-Day Execution Roadmap (Alpha ➜ Beta)

Objective: Close the highest-impact gaps to reach EdTech Beta parity: SSO/RBAC, LTI/SIS integrations, compliance operationalization, multi‑tenancy, schema governance, SLOs/runbooks, and API productization.

References
- Rules: `.cursor/rules/020-architectural-mandates.mdc`, `042-async-patterns-and-di.mdc`, `048-structured-error-handling-standards.mdc`, `070-testing-and-quality-assurance.mdc`, `085-database-migration-standards.mdc`, `090-documentation-standards.mdc`, `110.*`
- Tooling: `pyproject.toml` scripts, `docker-compose*.yml`, `observability/`
- Services: `services/*`, shared libs: `libs/common_core`, `libs/huleedu_service_libs`

## Milestones

1) Identity & Access (Weeks 1–3)
- OIDC SSO (Google for Education), RBAC/ABAC roles, token introspection hardening.
- Owners: Identity + API Gateway teams.

2) LMS & SIS Integrations (Weeks 2–6)
- LTI 1.3 adapter (NRPS, AGS). OneRoster import pipeline + Clever/ClassLink connectors.
- Owners: API Gateway + new LTI Adapter + CMS.

3) Compliance Operationalization (Weeks 3–7)
- DSR (export/erasure), retention policies, audit logging, secrets manager/KMS plan.
- Owners: Platform + CMS + File/Content + Identity.

4) Multi‑tenancy (Weeks 5–8)
- Tenant ID in DB/event models, per‑tenant rate limits/quotas and LLM cost tracking.
- Owners: All service owners, coordinated via Platform.

5) Event Schema Governance (Weeks 6–8)
- JSON Schema/Avro registry, CI gate on breaking changes, contract tests expansion.
- Owners: Platform + common_core.

6) SLOs, Alerts, Runbooks (Weeks 7–9)
- Define SLOs, Prometheus alert rules, DLQ/runbook docs and replay scripts.
- Owners: Platform + each service owner.

7) API Productization (Weeks 8–10)
- API keys, quotas, public OpenAPI, doc site updates, versioning policy.
- Owners: API Gateway + Docs.

## Workstreams (link to detailed plans)
- Identity & RBAC: `TASKS/IDENTITY_SSO_AND_RBAC_PLAN.md`
- LTI (LMS): `TASKS/LTI_LMS_INTEGRATION_PLAN.md`
- SIS (OneRoster/Clever/ClassLink): `TASKS/SIS_INTEGRATION_ONEROSTER_CLEVER_CLASSLINK_PLAN.md`
- Compliance (GDPR/FERPA): `TASKS/COMPLIANCE_GDPR_FERPA_OPERATIONALIZATION_PLAN.md`
- Multi‑tenancy: `TASKS/MULTI_TENANCY_IMPLEMENTATION_PLAN.md`
- Schema Governance & CI: `TASKS/EVENT_SCHEMA_GOVERNANCE_AND_CI_PLAN.md`
- SLOs/Alerts/Runbooks: `TASKS/SLO_ALERTS_AND_RUNBOOKS_PLAN.md`
- API Productization: `TASKS/API_PRODUCTIZATION_AND_DOCS_PLAN.md`

## Definition of Done (Beta Readiness)
- SSO live (OIDC), baseline RBAC enforced at gateway and services.
- LTI 1.3 flow passes LMS certification against one target LMS; OneRoster CSV import functional.
- DSR export/erasure endpoints implemented with audit trail; retention job(s) configured.
- Tenant ID enforced in DB schemas and events; per‑tenant rate limits and LLM usage tracking working.
- Event schemas versioned and validated in CI; breaking changes blocked.
- SLOs defined and alerts firing in dev with documented runbooks; DLQ replay procedure validated.
- Public API docs published with API keys/quotas; versioning and deprecation policy documented.

---

Execution notes
- Use `pdm run dev` for builds; restart services with `pdm run restart <service>` or `pdm run restart-all`.
- Validate changes with `pdm run test-all` and `pdm run typecheck-all` before PRs.
