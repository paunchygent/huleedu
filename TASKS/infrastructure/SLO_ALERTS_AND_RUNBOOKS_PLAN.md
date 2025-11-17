---
id: 'SLO_ALERTS_AND_RUNBOOKS_PLAN'
title: 'SLOs, Alerts, and Runbooks (Weeks 7–9)'
type: 'task'
status: 'research'
priority: 'medium'
domain: 'infrastructure'
service: ''
owner_team: 'agents'
owner: ''
program: ''
created: '2025-08-23'
last_updated: '2025-11-17'
related: []
labels: []
---
# SLOs, Alerts, and Runbooks (Weeks 7–9)

Objective
- Define service SLOs, implement Prometheus alerts, and document runbooks including DLQ replay procedures.

Scope
- In: SLO definitions, alert rules, DLQ topics/process, runbooks per service.
- Out: External incident tooling configuration (tracked elsewhere).

References
- Observability: `observability/*` (Prometheus, Grafana, Loki, Jaeger)
- Kafka: resilient publisher/outbox (`libs/huleedu_service_libs/kafka/*`, `outbox/*`)
- Rules: `071-observability-index.mdc`, `073-health-endpoint-implementation.mdc`

Deliverables
1. SLOs: availability, latency, error rate per HTTP service; processing throughput for workers.
2. Alerts: Prometheus rules for error budget burn and key error conditions.
3. DLQ: Standard DLQ topics and replay script with safeguards.
4. Runbooks: Service-specific runbooks for common failures and on-call.

Work Packages
1) Define SLOs
   - Add `observability/` docs with SLO tables per service.
   - Acceptance: SLOs reviewed and published.

2) Prometheus Alerts
   - Create/extend `observability/prometheus/prometheus.yml` and rules files.
   - Acceptance: Alerts fire in dev with synthetic failures; documented in Grafana.

3) DLQ + Replay
   - Define `<topic>.dlq` per critical topic; add producer to route poison messages.
   - Add `scripts/kafka_replay_dlq.py` with filters and rate control.
   - Acceptance: Replay tested in dev; safeguards inplace.

4) Runbooks
   - Add `observability/DEPLOYMENT_VALIDATION.md` updates + per-service runbooks.
   - Acceptance: Each service README links to its runbook; steps tested.

Definition of Done
- SLOs defined; alerts configured; DLQ and replay script validated; runbooks committed and linked.
