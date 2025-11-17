---
description: Grafana dashboard standards and operational patterns
globs: 
alwaysApply: false
---
# 072: Grafana Playbook Rules

## Dashboard Standards

### Naming Convention
**Pattern**: `HuleEdu - <Category> - <Specific Purpose>`

**Examples**:
- `HuleEdu - System Health - Overview`
- `HuleEdu - Service - Batch Orchestrator Deep Dive`
- `HuleEdu - Business - Essay Processing Funnel`
- `HuleEdu - Troubleshooting - Correlation ID Tracker`

### Panel Organization
- **Top Row**: High-level health indicators (service status, error rates)
- **Middle Rows**: Detailed metrics (response times, throughput, business metrics)
- **Bottom Row**: Logs and troubleshooting panels
- **Limit**: Maximum 12 panels per dashboard

### Time Range Standards
- **Default**: 1h, 6h, 24h, 7d
- **Refresh**: 30s (live monitoring), 5m (analysis)
- **Auto-refresh**: ON for operational, OFF for analysis

## Essential Dashboard Templates

### System Health Overview
**URL**: `/d/huleedu-system-health/huleedu-system-health-overview`

**Required Panels**:
1. Service Availability: `huleedu:service_availability:percent`
2. Error Rate Trend: `huleedu:http_errors_5xx:rate5m`
3. HTTP Request Rate: `huleedu:http_requests:rate5m`
4. Infrastructure Health: `huleedu:infrastructure_health:up`
5. Circuit Breaker Status: `huleedu:circuit_breaker:state_by_service`
6. Active Alerts: `ALERTS{alertstate="firing"}`

### Service Deep Dive Template
**URL**: `/d/huleedu-service-{service}/huleedu-service-{service}-deep-dive`

**Required Panels**:
1. Request Rate: `rate(http_requests_total{service="$service"}[5m])`
2. Error Rate: `rate(http_requests_total{service="$service",code=~"5.."}[5m])`
3. Response Time P95: `histogram_quantile(0.95, rate(http_request_duration_seconds_bucket{service="$service"}[5m]))`
4. Database Pool: `database_pool_active_connections{service="$service"}`
5. Memory Usage: `process_resident_memory_bytes{service="$service"}`
6. Service Logs: `{service="$service"} |= "ERROR"`

## Query Standards

### Standard Metrics Library
```promql
# Request rate
rate(http_requests_total{service="$service"}[5m])

# Error rate
rate(http_requests_total{service="$service",code=~"5.."}[5m]) / rate(http_requests_total{service="$service"}[5m])

# Response time percentiles
histogram_quantile(0.95, rate(http_request_duration_seconds_bucket{service="$service"}[5m]))

# Database connections
database_pool_active_connections{service="$service"}

# Circuit breaker state
circuit_breaker_state{service="$service"}

# Memory usage
process_resident_memory_bytes{service="$service"}
```

### Query Optimization Rules
- **Use recording rules** for complex queries accessed by multiple dashboards
- **Avoid regex** in frequently accessed queries
- **Limit time ranges** to necessary data (avoid `[1d]` for real-time dashboards)
- **Use rate()** for counters, not increase()

## Variable Standards

### Required Variables
```yaml
# Service selector
- name: service
  type: query
  query: label_values(http_requests_total, service)
  
# Instance selector  
- name: instance
  type: query
  query: label_values(http_requests_total{service="$service"}, instance)

# Time range selector
- name: range
  type: interval
  options: ["5m", "15m", "1h", "6h"]
```

## Alert Integration

### Alert Panel Configuration
```json
{
  "type": "table",
  "targets": [
    {
      "expr": "ALERTS{alertstate=\"firing\"}",
      "format": "table"
    }
  ],
  "transformations": [
    {
      "id": "organize",
      "options": {
        "excludeByName": {"__name__": true},
        "indexByName": {
          "alertname": 0,
          "severity": 1,
          "service": 2,
          "summary": 3
        }
      }
    }
  ]
}
```

### Alert Annotation Integration
```json
{
  "annotations": {
    "list": [
      {
        "name": "HuleEdu Alerts",
        "datasource": "Prometheus",
        "expr": "ALERTS_FOR_STATE{alertstate=\"firing\"}",
        "titleFormat": "{{alertname}}: {{summary}}",
        "textFormat": "{{description}}"
      }
    ]
  }
}
```

## Dashboard Maintenance

### Update Frequency
- **Operational dashboards**: Review monthly
- **Analysis dashboards**: Review quarterly
- **Service dashboards**: Update with each service deployment

### Version Control
- Export dashboard JSON to `observability/dashboards/`
- Include in Git with service changes
- Use semantic versioning for dashboard changes

### Performance Monitoring
- Monitor dashboard load times (target: <2s)
- Review query performance monthly
- Optimize slow queries using recording rules

## User Experience Guidelines

### Color Standards
- **Green**: Healthy/Normal (0-80% utilization)
- **Yellow**: Warning (80-90% utilization) 
- **Red**: Critical (>90% utilization)
- **Blue**: Informational metrics
- **Purple**: Business metrics

### Threshold Configuration
```yaml
# Standard thresholds
error_rate:
  green: 0-1%
  yellow: 1-5%
  red: >5%

response_time_p95:
  green: 0-100ms
  yellow: 100-500ms
  red: >500ms

cpu_usage:
  green: 0-70%
  yellow: 70-85%
  red: >85%
```

### Panel Sizing Standards
- **Single Stat**: 3x2 grid units
- **Time Series**: 6x4 grid units  
- **Table**: 12x4 grid units
- **Logs**: 12x6 grid units

## Operational Integration

### Incident Response Dashboards
1. **Primary**: System Health Overview
2. **Secondary**: Service-specific deep dive  
3. **Tertiary**: Correlation ID tracker for debugging

### Runbook Integration
- Link dashboard panels to relevant runbook sections
- Include dashboard URLs in alert descriptions
- Embed query examples in troubleshooting guides

### Team Access Patterns
- **Platform Team**: Full access to all dashboards
- **Service Teams**: Edit access to service-specific dashboards
- **Leadership**: View access to business metric dashboards
