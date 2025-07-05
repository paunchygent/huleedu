---
description: Grafana Playbook Rules for implementation!!!
globs: 
alwaysApply: false
---
# 072: Grafana Playbook Rules

## 1. Dashboard Creation Standards

### 1.1. Dashboard Naming Convention
**MUST** follow pattern: `HuleEdu - <Category> - <Specific Purpose>`

Examples:
- `HuleEdu - System Health - Overview`
- `HuleEdu - Service - Batch Orchestrator Deep Dive`
- `HuleEdu - Business - Essay Processing Funnel`
- `HuleEdu - Troubleshooting - Correlation ID Tracker`

### 1.2. Panel Organization Principles
- **Top Row**: High-level health indicators (service status, error rates)
- **Middle Rows**: Detailed metrics (response times, throughput, business metrics)
- **Bottom Row**: Logs and troubleshooting panels
- **FORBIDDEN**: More than 12 panels per dashboard (cognitive overload)

### 1.3. Time Range Standards
**Default Time Ranges**: 1h, 6h, 24h, 7d
**Refresh Intervals**: 30s (live monitoring), 5m (historical analysis)
**Auto-refresh**: ON for operational dashboards, OFF for analysis dashboards

## 2. Essential Dashboard Templates

### 2.1. System Health Overview Template
**Purpose**: Single pane of glass for operational status
**Dashboard URL**: http://localhost:3000/d/huleedu-system-health/huleedu-system-health-overview

**Required Panels**:
1. Service Availability (Stat): `huleedu:service_availability:percent`
2. Error Rate Trend (Time Series): `huleedu:http_errors_5xx:rate5m`
3. HTTP Request Rate (Time Series): `huleedu:http_requests:rate5m`
4. Infrastructure Health (Stat): `huleedu:infrastructure_health:up`
5. Circuit Breaker Status (Stat): `huleedu:circuit_breaker:state_by_service`
6. Active Alerts (Table): `ALERTS{alertstate="firing"}`
7. Circuit Breaker State Changes (Time Series): `huleedu:circuit_breaker:changes_rate5m_by_service`

**Performance Optimizations**:
- Uses recording rules for faster query execution
- No regex patterns in queries
- 30s refresh interval for operational awareness

### 2.2. Service Deep Dive Template
**Purpose**: Detailed analysis of individual service performance
**Dashboard URL**: http://localhost:3000/d/huleedu-service-deep-dive/huleedu-service-deep-dive

**Required Panels**:
1. Request Rate by Status (Time Series): `huleedu:service_http_requests:rate5m{service="${service}"}`
2. Request Duration Percentiles (Time Series): Service-specific latency metrics
3. Error Rate by Endpoint (Table): Service-specific error tracking
4. Circuit Breaker State (Stat): `(${service}_circuit_breaker_state{job="${service}"} or llm_provider_circuit_breaker_state{job="${service}"} or bos_circuit_breaker_state{job="${service}"})`
5. Business Metrics (Stat): Service-specific KPIs
6. Circuit Breaker Transitions (Time Series): `rate((${service}_circuit_breaker_state_changes_total{job="${service}"} or llm_provider_circuit_breaker_state_changes_total{job="${service}"} or bos_circuit_breaker_state_changes_total{job="${service}"})[5m])`
7. Service Logs (Logs): `{container=~"huleedu_${service}"} |= "${log_filter}"`

**Features**:
- Service variable dropdown for easy switching
- Circuit breaker integration for services with external dependencies
- Business metrics tailored per service type

### 2.3. Troubleshooting Dashboard Template
**Purpose**: Correlation ID tracking and error investigation
**Required Panels**:
1. Correlation ID Tracer (Logs): `{correlation_id="$correlation_id"}` (with variable)
2. Service Event Timeline (Logs): Events by timestamp with correlation context
3. Error Pattern Analysis (Table): Error frequency by message pattern
4. Cross-Service Flow (Logs): Multi-service request tracing

## 3. Query Standards and Library

### 3.1. Standard PromQL Query Patterns

```promql
# Service Health Percentage
count(up{job=~".*_service"} == 1) / count(up{job=~".*_service"}) * 100

# Error Rate by Service (5-minute window)
sum(rate(http_requests_total{status_code=~"5.."}[5m])) by (job)

# 95th Percentile Response Time
histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket[5m])) by (le, job))

# Request Rate by Endpoint
sum(rate(http_requests_total[5m])) by (job, endpoint)

# Memory Usage by Service
container_memory_usage_bytes{name=~"huleedu_.*"} / 1024 / 1024 / 1024

# Custom Metrics Pattern
sum(rate(huleedu_<service>_<metric>[5m])) by (<relevant_labels>)

# Circuit Breaker State (Multi-service pattern)
(${service}_circuit_breaker_state{job="${service}"} or llm_provider_circuit_breaker_state{job="${service}"} or bos_circuit_breaker_state{job="${service}"})

# Circuit Breaker State Changes Rate
rate((${service}_circuit_breaker_state_changes_total{job="${service}"} or llm_provider_circuit_breaker_state_changes_total{job="${service}"} or bos_circuit_breaker_state_changes_total{job="${service}"})[5m])

# Circuit Breaker Recording Rules
huleedu:circuit_breaker:state_by_service
huleedu:circuit_breaker:changes_rate5m_by_service
```

### 3.2. Standard LogQL Query Patterns

```logql
# Trace by Correlation ID
{correlation_id="<correlation-id>"}

# Service-Specific Logs with Filter
{container=~"huleedu_${service}"} |= "${log_filter}"

# Service-Specific Error Logs
{container=~"huleedu_<service_name>"} | json | level="error"

# Cross-Service Event Flow
{container=~"huleedu_(batch_orchestrator_service|essay_lifecycle_service)"} | json | correlation_id="<id>"

# Error Pattern Detection
{container=~"huleedu_.+"} | json | level="error" | pattern "<_> ERROR: <error_pattern> <_>"

# Performance Log Analysis
{container=~"huleedu_<service>"} | json | line_format "{{.timestamp}} {{.event}} took {{.duration}}ms"
```

### 3.3. Business Intelligence Query Patterns

```promql
# Pipeline Execution Rate
sum(rate(huleedu_pipeline_execution_total{job="${service}"}[5m])) or vector(0)

# Spell Check Corrections Rate
sum(rate(huleedu_spellcheck_corrections_made{job="${service}"}[5m])) or vector(0)

# CJ Assessment Comparisons Rate
sum(rate(huleedu_cj_comparisons_made{job="${service}"}[5m])) or vector(0)

# File Upload Rate
sum(rate(file_service_files_uploaded_total{job="${service}"}[5m])) or vector(0)
```

## 4. Variable and Template Standards

### 4.1. Standard Dashboard Variables
**MUST implement these variables where applicable**:
- `$service`: Service selector for multi-service dashboards
- `$log_filter`: Log filtering for service deep dive
- `$correlation_id`: For troubleshooting dashboards
- `$time_range`: Custom time range selector
- `$environment`: If multi-environment deployment

### 4.2. Variable Configuration
```json
{
  "name": "service",
  "type": "query",
  "query": "label_values(up, job)",
  "refresh": "on_time_range_change",
  "regex": ".*_service",
  "multi": false,
  "includeAll": false
}
```

## 5. Alert Integration Patterns

### 5.1. Alert Status Panels
**MUST** include AlertManager integration in operational dashboards:
- Current active alerts table
- Alert history timeline
- Alert resolution tracking

### 5.2. Alert Context Links
**Configure alert annotations to link to relevant dashboards**:
```yaml
annotations:
  dashboard_url: "http://localhost:3000/d/huleedu-service-deep-dive/huleedu-service-deep-dive?var-service={{ $labels.job }}"
  runbook_url: "http://localhost:3000/d/huleedu-service-deep-dive/huleedu-service-deep-dive?var-service={{ $labels.service_name }}"
```

**Example Alert - Circuit Breaker Open**:
```yaml
- alert: CircuitBreakerOpen
  expr: |
    (
      llm_provider_circuit_breaker_state == 1 or
      bos_circuit_breaker_state == 1 or
      els_circuit_breaker_state == 1 or
      cj_assessment_circuit_breaker_state == 1 or
      class_management_circuit_breaker_state == 1 or
      file_service_circuit_breaker_state == 1 or
      spell_checker_circuit_breaker_state == 1
    )
  for: 30s
  labels:
    severity: critical
  annotations:
    summary: "Circuit breaker OPEN for {{ $labels.circuit_name }}"
    description: "Circuit breaker '{{ $labels.circuit_name }}' in service {{ $labels.service_name }} is OPEN, blocking all requests."
    dashboard_url: "http://localhost:3000/d/huleedu-service-deep-dive/huleedu-service-deep-dive?var-service={{ $labels.service_name }}"
```

## 6. Dashboard Maintenance Standards

### 6.1. Documentation Requirements
**Every dashboard MUST include**:
- Description panel explaining dashboard purpose
- Contact information for dashboard owner
- Last updated timestamp
- Links to relevant runbooks/documentation

### 6.2. Performance Optimization
- **Query Timeout**: 30s maximum for all queries
- **Panel Limits**: Maximum 1000 data points per time series panel
- **Refresh Strategy**: Use recording rules for expensive calculations
- **Data Source**: Prefer Prometheus for metrics, Loki for logs (don't mix unnecessarily)

### 6.3. Review and Update Cycle
- **Monthly Review**: Dashboard effectiveness and query performance
- **Post-Incident Updates**: Improve dashboards based on troubleshooting experience
- **Feature Release Updates**: Add new metrics when services are updated
- **Archive Policy**: Remove unused dashboards after 90 days of no access

## 7. User Experience Guidelines

### 7.1. Color and Visual Standards
- **Green**: Healthy/Success states
- **Yellow**: Warning/Degraded states  
- **Red**: Critical/Error states
- **Blue**: Informational/Neutral metrics
- **FORBIDDEN**: Rainbow color schemes (accessibility concern)

### 7.2. Panel Sizing and Layout
- **Full Width**: System health overview panels
- **Half Width**: Most metric panels (allows side-by-side comparison)
- **Quarter Width**: Single stat panels (availability percentages)
- **Full Width Bottom**: Log panels for debugging

### 7.3. Threshold Configuration
**Set meaningful thresholds for all stat panels**:
- Service Availability: Green >95%, Yellow 90-95%, Red <90%
- Error Rate: Green <0.01%, Yellow 0.01-0.1%, Red >0.1%
- Response Time: Green <100ms, Yellow 100-500ms, Red >500ms

## 8. Integration with Operational Workflows

### 8.1. Daily Monitoring Routine
1. **System Health Dashboard**: Check overall service status
2. **Alert Dashboard**: Review any active or recently resolved alerts
3. **Business Metrics Dashboard**: Verify processing throughput
4. **Update Team Chat**: Brief status summary if issues found

### 8.2. Incident Response Integration
1. **Start with Alerts**: AlertManager → Grafana dashboard links
2. **Service Deep Dive**: Use service-specific dashboards for investigation
3. **Correlation Tracking**: Use troubleshooting dashboard with correlation IDs
4. **Post-Incident**: Update runbooks and improve dashboard based on experience

---

**Dashboard Priority**: System Health → Service Deep Dive → Business Intelligence → Troubleshooting
**Update Frequency**: Real-time operational, Weekly business intelligence, Monthly troubleshooting enhancements
