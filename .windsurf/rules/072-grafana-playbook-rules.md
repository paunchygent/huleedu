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
**Required Panels**:
1. Service Availability (Stat): `count(up{job=~".*_service"} == 1) / count(up{job=~".*_service"}) * 100`
2. Error Rate Trend (Time Series): `sum(rate(http_requests_total{status_code=~"5.."}[5m])) by (job)`
3. Response Time P95 (Time Series): `histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket[5m])) by (le, job))`
4. Active Alerts (Table): Alert status from AlertManager
5. Resource Usage (Time Series): Container memory/CPU utilization
6. Recent Error Logs (Logs): `{service=~".+"} | json | level="error"`

### 2.2. Service Deep Dive Template
**Purpose**: Detailed analysis of individual service performance
**Required Panels**:
1. Service Status (Stat): Service-specific health check
2. Request Rate (Time Series): `rate(http_requests_total{job="<service>"}[5m])`
3. Error Rate by Endpoint (Bar Chart): `rate(http_requests_total{job="<service>", status_code=~"5.."}[5m]) by (endpoint)`
4. Response Time Distribution (Heatmap): Request duration histograms
5. Custom Business Metrics: Service-specific counters/histograms
6. Service Logs (Logs): `{service="<service>"} | json`

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
```

### 3.2. Standard LogQL Query Patterns

```logql
# Trace by Correlation ID
{correlation_id="<correlation-id>"}

# Service-Specific Error Logs
{service="<service_name>"} | json | level="error"

# Cross-Service Event Flow
{service=~"batch_orchestrator_service|essay_lifecycle_service"} | json | correlation_id="<id>"

# Error Pattern Detection
{service=~".+"} | json | level="error" | pattern "<_> ERROR: <error_pattern> <_>"

# Performance Log Analysis
{service="<service>"} | json | line_format "{{.timestamp}} {{.event}} took {{.duration}}ms"
```

### 3.3. Business Intelligence Query Patterns

```promql
# File Upload Types Distribution
sum(rate(huleedu_files_uploaded_total[5m])) by (file_type)

# Spell Check Corrections Distribution
histogram_quantile(0.90, sum(rate(huleedu_spellcheck_corrections_made_bucket[5m])) by (le))

# Essay Processing Pipeline Throughput
sum(rate(huleedu_essays_processed_total[5m])) by (processing_stage)
```

## 4. Variable and Template Standards

### 4.1. Standard Dashboard Variables
**MUST implement these variables where applicable**:
- `$service`: Service selector for multi-service dashboards
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
  "multi": true,
  "includeAll": true
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
  dashboard_url: "http://grafana:3000/d/<dashboard-id>?var-service={{ $labels.job }}"
  runbook_url: "https://docs.huledu.com/runbooks/{{ $labels.alertname }}"
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
