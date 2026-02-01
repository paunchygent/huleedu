---
id: us-0073-dev-runner-and-kafka-wrapper-for-cj-workflows
title: 'US-007.3: Dev runner and Kafka wrapper for CJ workflows'
type: task
status: proposed
priority: medium
domain: assessment
service: cj_assessment_service
owner_team: agents
owner: ''
program: ''
created: '2025-11-28'
last_updated: '2026-02-01'
related: []
labels: []
---
# US-007.3: Dev runner and Kafka wrapper for CJ workflows

## Objective

Create simple utilities to run CJ workflows locally, enabling testing without full Kafka/Docker infrastructure.

## Context

Part of EPIC-007 (Developer Experience & Testing). Developers currently need full infrastructure to test CJ workflows. This story provides lightweight alternatives for local development and testing.

## Acceptance Criteria

- [ ] An in-process dev runner exists, e.g. `clients/python/cj_runner.py`, that:
  - Accepts an `AsyncEngine` or DSN
  - Instantiates `CJAssessmentServiceProvider`
  - Exposes a single `run_cj_assessment_workflow_in_process(request_data, correlation_id)` helper
- [ ] A small Kafka client wrapper exists, e.g. `clients/python/cj_kafka_client.py`, that:
  - Takes `ELS_CJAssessmentRequestV1`-shaped data
  - Publishes to `CJ_ASSESSMENT_REQUEST_TOPIC`
  - Returns the correlation ID and any useful tracing metadata
- [ ] Example usage is provided under `examples/`, showing:
  - How another service or script submits a batch via Kafka
  - How to run an end-to-end in-process test with the dev runner
- [ ] A how-to document exists under `docs/how-to/`, e.g. `docs/how-to/run-cj-assessment-locally.md`, describing:
  - Setup (DB, Kafka, env vars)
  - How to use the dev runner and Kafka client
  - How to inspect results

## Implementation Notes

Key files to create:
- `clients/python/cj_runner.py`
- `clients/python/cj_kafka_client.py`
- `examples/cj_assessment/submit_batch.py`
- `examples/cj_assessment/run_in_process.py`
- `docs/how-to/run-cj-assessment-locally.md`

## Related

- Parent epic: [EPIC-007: Developer Experience & Testing](../../../docs/product/epics/cj-developer-experience-and-testing.md)
- Related stories: US-007.1 (Test helpers), US-007.4 (Test architecture guardrails)
