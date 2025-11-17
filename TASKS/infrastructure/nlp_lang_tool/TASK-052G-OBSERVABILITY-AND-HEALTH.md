---
id: 'TASK-052G-OBSERVABILITY-AND-HEALTH'
title: 'TASK-052G — Observability & Health'
type: 'task'
status: 'research'
priority: 'medium'
domain: 'infrastructure'
service: ''
owner_team: 'agents'
owner: ''
program: ''
created: '2025-09-09'
last_updated: '2025-11-17'
related: []
labels: []
---
# TASK-052G — Observability & Health

## Objective

Implement correlation middleware, structured logging, Prometheus metrics, and robust health reporting for Language Tool Service.

## Observability

- Correlation (Rule 043.2): `setup_correlation_middleware(app)`; DI provider for `CorrelationContext` (REQUEST scope).
- Logging: `huleedu_service_libs.logging_utils.configure_service_logging` with service name.
- Metrics:
  - `http_requests_total{method,endpoint,http_status}`
  - `http_request_duration_seconds{method,endpoint}`
  - `wrapper_duration_seconds{language}`
  - `api_errors_total{endpoint,error_type}`

## Health Endpoint `/healthz`

- Fields: `{ "status": "healthy", "jvm": {"running": bool, "heap_used_mb": int}, "uptime_seconds": float }`
- Fallback: if JVM not started yet, return `running: false` (still 200 if service otherwise OK).

## Acceptance Tests

- `/metrics` exposes Prometheus format and increments on requests.
- `/healthz` includes expected JSON keys and reflects wrapper state.

## Deliverables

- Middleware setup, metrics registration, and health blueprint implementation.

