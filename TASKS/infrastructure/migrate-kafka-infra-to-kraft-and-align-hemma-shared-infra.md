---
id: 'migrate-kafka-infra-to-kraft-and-align-hemma-shared-infra'
title: 'Migrate Kafka infra to KRaft and align Hemma shared infra'
type: 'story'
status: 'done'
priority: 'high'
domain: 'infrastructure'
service: ''
owner_team: 'agents'
owner: ''
program: 'huledu_alpha_launch'
created: '2026-02-01'
last_updated: '2026-02-01'
related: []
labels: []
---
# Migrate Kafka infra to KRaft and align Hemma shared infra

## Objective

Replace the ZooKeeper-based Kafka dev/prod infrastructure with a KRaft-based Kafka
deployment that is supported, multi-arch, and operationally aligned with Hemma’s
shared infra model (shared `hule-network`, shared-postgres, shared observability),
while keeping local dev as a staging environment with strong prod parity.

## Context

- Hemma currently cannot pull `bitnami/zookeeper:*` (Docker Hub images moved), which
  blocks Kafka startup in production-like environments.
- KRaft removes ZooKeeper entirely, simplifying long-term ops and reducing moving parts.
- We want “public surface = nginx-proxy routed API/BFF/WS only” enforced by config;
  infra services must not accidentally bind to public interfaces on Hemma.

## Plan

1. Switch `docker-compose.infrastructure.yml` Kafka to KRaft (drop `zookeeper` service).
2. Keep host tooling compatibility by retaining `localhost:9093` as the default host
   Kafka bootstrap port, but bind host ports to `127.0.0.1` so nothing is exposed
   publicly on Hemma by accident.
3. Update local dev orchestration scripts + runbooks that referenced ZooKeeper.
4. Add a Hemma-specific master compose (`docker-compose.hemma.yml`) that does **not**
   include the repo’s observability stack; Hemma uses the shared observability stack.
5. Validate locally (compose config, format/lint/typecheck, docs/task validators).
6. Validate on Hemma (bring up `kafka` + `redis`, ensure health, run topic bootstrap).

## Success Criteria

- `docker compose up -d kafka redis` succeeds (no ZooKeeper required) and Kafka becomes
  healthy within 60s.
- Internal services can use `kafka:9092`; host tools can use `localhost:9093`.
- On Hemma, Kafka and Redis host ports bind to `127.0.0.1` only.
- `kafka_topic_setup` completes successfully against the KRaft broker.
- Docs + scripts no longer reference ZooKeeper for platform infra.
- `pdm run validate-docs`, `pdm run validate-tasks`, `pdm run index-tasks` pass.

## Status Update (2026-02-01)

Completed:
- KRaft Kafka in place (`apache/kafka:3.8.0`), no ZooKeeper dependency.
- Hemma compose layering enforces localhost-only infra + research services.
- Local + Hemma validation performed; docs + TASKS validators passing.

## Related

- Programme hub: `TASKS/programs/huledu_alpha_launch/hub.md`
- ADR: `docs/decisions/0028-kafka-infra-move-to-kraft-drop-zookeeper-and-align-hemma-shared-deployment.md`
