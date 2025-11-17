---
id: 'COMPLIANCE_GDPR_FERPA_OPERATIONALIZATION_PLAN'
title: 'Compliance Operationalization: GDPR/FERPA (Weeks 3–7)'
type: 'task'
status: 'research'
priority: 'medium'
domain: 'security'
service: ''
owner_team: 'agents'
owner: ''
program: ''
created: '2025-08-23'
last_updated: '2025-11-17'
related: []
labels: []
---
# Compliance Operationalization: GDPR/FERPA (Weeks 3–7)

Objective
- Operationalize privacy compliance: DSR (export/erasure), retention, audit logging, secret management strategy.

Scope
- In: DSR endpoints + processors, retention policy config + jobs, PII access audit logs, key/secrets mgmt plan.
- Out: Legal documentation (handled outside repo), enterprise audit UI.

References
- CMS for student/person data: `services/class_management_service/*`
- Content/File services for data storage: `services/content_service/*`, `services/file_service/*`
- Identity for account linkages: `services/identity_service/*`
- Observability: `observability/`
- Rules: `020`, `048`, `070`, `085`, `090`

Deliverables
1. DSR Export: API to export user data (JSON bundle + links to content).
2. DSR Erasure: API to queue erasure; background processors to purge across services.
3. Retention: Configurable retention windows and scheduled purge jobs (per service).
4. Audit Logging: PII access/change events with immutable logs.
5. Secrets/KMS Plan: Document plan to move prod secrets to Vault/Cloud KMS + key rotation.

Work Packages
1) DSR API (Gateway + CMS)
   - Gateway routes `/v1/privacy/export` & `/v1/privacy/erasure` (teacher/admin only).
   - CMS orchestration to publish DSR commands via Kafka; services consume and act.
   - Acceptance: Export returns downloadable bundle; erasure queued with status tracking.

2) Service Processors
   - Content/File: implement erasure handlers (delete content + metadata), retention sweeps.
   - Identity: erase PII or anonymize as appropriate; preserve legal audit records.
   - Acceptance: End-to-end erasure removes content and PII references; audit entries recorded.

3) Audit Logs
   - Append-only audit table per service; standard event format in `common_core` (new model).
   - Acceptance: Every DSR action and PII read/write yields audit record; Prometheus counter.

4) Retention Jobs
   - CRON-like worker in each service to purge aged records respecting business rules.
   - Acceptance: Dry-run + execution modes; metrics for purged counts.

5) Secrets/KMS
   - Author plan to move to Vault/Cloud Secrets + KMS; document key rotation cadence.
   - Acceptance: doc in `documentation/setup_environment/SECRETS_MANAGEMENT.md` updated; ops tasks listed.

Tests
- Contract/E2E tests covering export + erasure happy paths; negative cases (unauthorized).

Definition of Done
- DSR endpoints live; processors implemented in core data services; retention jobs running; audit logging enabled; plan for prod secrets/KMS documented.
