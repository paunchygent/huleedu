---
description: Index of observability patterns and sub-rules
globs: 
alwaysApply: false
---
# 071: Observability Index

## Purpose
Observability patterns for monitoring, tracing, and debugging HuleEdu services.

## Sub-Rules

### 071: Core Patterns
- Location: `071-observability-core-patterns.mdc`
- Covers: Philosophy, correlation patterns, naming conventions
- When: Setting up any observability component

### 071.1: Prometheus Metrics
- Location: `071.1-prometheus-metrics-patterns.mdc`
- Covers: Metric types, service integration, label strategy
- When: Adding metrics to services

### 071.2: Jaeger Tracing
- Location: `071.2-jaeger-tracing-patterns.mdc`
- Covers: OpenTelemetry integration, trace propagation, debugging
- When: Adding distributed tracing

### 071.3: Grafana & Loki
- Location: `071.3-grafana-loki-patterns.mdc`
- Covers: Dashboard patterns, log queries, datasource configuration
- When: Creating dashboards or log analysis

### 072: Grafana Playbooks
- Location: `072-grafana-playbook-rules.mdc`
- Covers: Troubleshooting guides and runbooks
- When: Documenting operational procedures

## Quick Reference

### Stack Access
- Prometheus: http://localhost:9091
- Grafana: http://localhost:3000
- Jaeger UI: http://localhost:16686
- Loki: http://localhost:3100 (API only)

### Key Commands
```bash
# Start observability stack
pdm run obs-up

# Check metrics
docker exec <container> curl http://localhost:<port>/metrics

# Query Prometheus
docker exec huleedu_prometheus wget -qO- "http://localhost:9090/api/v1/query?query=up"
```

### Import Order
1. Read core patterns (071)
2. Read specific technology pattern (071.1, 071.2, or 071.3)
3. Apply patterns to service
