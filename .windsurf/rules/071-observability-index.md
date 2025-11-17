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
- Location: `071.1-observability-core-patterns.md`
- Covers: Philosophy, correlation patterns, naming conventions
- When: Setting up any observability component

### 071.1: Prometheus Metrics
- Location: `071.1-prometheus-metrics-patterns.md`
- Covers: Metric types, service integration, label strategy
- When: Adding metrics to services

### 071.2: Jaeger Tracing
- Location: `071.2-jaeger-tracing-patterns.md`
- Covers: OpenTelemetry integration, trace propagation, debugging
- When: Adding distributed tracing

### 071.3: Grafana & Loki
- Location: `071.3-grafana-loki-patterns.md`
- Covers: Dashboard patterns, log queries, datasource configuration
- When: Creating dashboards or log analysis

### 072: Grafana Playbooks
- Location: `072-grafana-playbook-rules.md`
- Covers: Troubleshooting guides and runbooks
- When: Documenting operational procedures

## Quick Reference

### Stack Access

**Main Observability Components:**
- **Grafana Dashboard**: http://localhost:3000 (admin/admin)
- **Prometheus Metrics**: http://localhost:9091
- **Alertmanager**: http://localhost:9094/ (note trailing slash for browser)
- **Jaeger Tracing**: http://localhost:16686
- **Loki Logs**: http://localhost:3100 ✅ WORKING
  - **Labels**: container, correlation_id, level, logger_name, service, service_name
  - **Promtail**: Automatically ingesting from all Docker containers
  - **JSON Parsing**: Automatic structured log parsing

**Internal Container URLs (for Grafana data sources):**
- **Prometheus**: `http://prometheus:9090`
- **Loki**: `http://loki:3100` ✅ CONFIRMED WORKING
- **AlertManager**: `http://alertmanager:9093`

**Infrastructure Monitoring:**
- **Kafka Metrics**: http://localhost:9308/metrics
- **PostgreSQL Metrics**: http://localhost:9187/metrics
- **Redis Metrics**: http://localhost:9121/metrics
- **Node Metrics**: http://localhost:9100/metrics

**Quick Dashboard Access:**
- **System Health**: http://localhost:3000/d/huleedu-system-health/huleedu-system-health-overview
- **Service Deep Dive**: http://localhost:3000/d/huleedu-service-deep-dive/huleedu-service-deep-dive
- **Troubleshooting**: http://localhost:3000/d/huleedu-troubleshooting/huleedu-troubleshooting

### Key Commands
```bash
# Start observability stack
pdm run obs-up
# or
docker compose -f observability/docker-compose.observability.yml up -d

# Stop observability stack
pdm run obs-down

# Check all services status
pdm run dc-ps

# Check Prometheus targets (should show 14+ UP)
curl http://localhost:9091/api/v1/targets

# Test recording rules
curl "http://localhost:9091/api/v1/query?query=huleedu:service_availability:percent"

# Test Loki API (✅ WORKING)
curl "http://localhost:3100/loki/api/v1/labels"

# Test AlertManager (note trailing slash)
curl http://localhost:9094/

# Check service metrics
curl http://localhost:8080/metrics  # API Gateway
curl http://localhost:8090/metrics  # LLM Provider
# ... (see service table above for all endpoints)

# View logs for observability components
pdm run obs-logs
```

### Import Order
1. Read core patterns (071)
2. Read specific technology pattern (071.1, 071.2, or 071.3)
3. Apply patterns to service
