---
description: Core observability patterns and principles for HuleEdu services
globs: 
alwaysApply: false
---
# 071: Observability Core Patterns

## 1. Philosophy
- **Business Insights First**: Metrics answer operational questions
- **Correlation Over Collection**: Better to correlate than collect more
- **Actionable Alerts**: Must have clear resolution steps

## 2. Standard Patterns

### 2.1. Service Identification
```python
# Every service MUST expose standard labels
service_name: str  # e.g., "batch_orchestrator_service"
service_version: str  # from SERVICE_VERSION env var
environment: str  # "development", "production"
```

### 2.2. Correlation Pattern
```python
# All operations MUST propagate correlation_id
correlation_id: UUID  # In logs, metrics labels, traces
```

### 2.3. Structured Logging
```python
# Use service library logger
from huleedu_service_libs.logging_utils import create_service_logger
logger = create_service_logger("service.module")

# Log with context
logger.info("Operation completed", extra={
    "correlation_id": str(correlation_id),
    "batch_id": batch_id,
    "duration_ms": duration
})
```

## 3. Integration Requirements

### 3.1. Every Service MUST
- Expose `/metrics` endpoint (Prometheus format)
- Use structured JSON logging
- Include correlation_id in all telemetry
- Implement health check endpoint

### 3.2. Observability Stack Location
- Configuration: `observability/docker-compose.observability.yml`
- Dashboards: `observability/grafana/dashboards/`
- Alerts: `observability/prometheus/rules/`

## 4. Naming Conventions

### 4.1. Metrics
- Service-specific: `<service_prefix>_<metric>_<unit>`
- Business metrics: `huleedu_<metric>_<unit>`
- Infrastructure: `<descriptive_name>_<unit>`

### 4.2. Dashboards
- System overview: `HuleEdu_System_Health_Overview.json`
- Service specific: `HuleEdu_<Service>_Deep_Dive.json`
- Troubleshooting: `HuleEdu_Troubleshooting_<Scenario>.json`
