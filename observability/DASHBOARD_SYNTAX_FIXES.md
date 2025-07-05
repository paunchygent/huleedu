# Dashboard PromQL Syntax Error Fixes

## Executive Summary

Fixed critical PromQL syntax errors in Grafana dashboards that were causing "syntax error: unexpected IDENTIFIER" at position 166 and preventing dashboard data display.

## Root Cause Analysis

### 1. Dashboard Query Issues

- **Complex OR chain queries**: Dashboard queries used complex chained `or` statements with multiple service-specific metrics
- **Incorrect metric usage**: Used `rate()` function on `up` metric (which is a gauge, not a counter)
- **Long query strings**: The original query causing the error was 191 characters long

### 2. Recording Rule Syntax Issues

- **Excessive parentheses**: Recording rule `huleedu:service_http_requests:rate5m` had unnecessary parentheses around each `label_replace` function
- **Inconsistent label names**: Different services used different label names for HTTP status codes (`status_code`, `status`, `http_status`)

## Fixes Applied

### 1. Dashboard Query Fixes

#### Before

```promql
(rate(http_requests_total{job="${service}"}[5m]) or rate(file_service_http_requests_total{job="${service}"}[5m]) or rate(cj_assessment_http_requests_total{job="${service}"}[5m]) or vector(0))
```

#### After

```promql
huleedu:service_http_requests:rate5m{service="${service}"}
```

### 2. Recording Rule Fixes

#### Before

```yaml
expr: |
  (
    label_replace(
      sum(rate(http_requests_total[5m])) by (job), 
      "service", "$1", "job", "(.*)"
    )
  ) or (
    label_replace(
      sum(rate(bos_http_requests_total[5m])) by (job), 
      "service", "$1", "job", "(.*)"
    )
  ) or ...
```

#### After

```yaml
expr: |
  label_replace(
    sum(rate(http_requests_total[5m])) by (job), 
    "service", "$1", "job", "(.*)"
  ) or
  label_replace(
    sum(rate(bos_http_requests_total[5m])) by (job), 
    "service", "$1", "job", "(.*)"
  ) or ...
```

### 3. Service Availability Query Fixes

#### Before

```promql
rate(up{job="${service}"}[5m])
```

#### After

```promql
avg_over_time(up{job="${service}"}[5m])
```

### 4. Label Standardization

Standardized all HTTP status code labels to use `status_code` across all services:

- `file_service_http_requests_total{status=~"5.."}` → `file_service_http_requests_total{status_code=~"5.."}`
- `cms_http_requests_total{http_status=~"5.."}` → `cms_http_requests_total{status_code=~"5.."}`
- `gateway_http_requests_total{http_status=~"5.."}` → `gateway_http_requests_total{status_code=~"5.."}`

## Character Position 166 Analysis

The original error "syntax error: unexpected IDENTIFIER" at position 166 was caused by:

- Character at position 166: 'v' (from "vector" in the OR chain)
- Context: `'${service}"}[5m]) or vector(0)'`

The error occurred because the complex OR chain with parentheses and template variables was not properly parsed by the PromQL engine.

## Validation Results

All configuration files now pass validation:

- ✅ Prometheus configuration is valid
- ✅ Recording rules are valid  
- ✅ Alert rules are valid
- ✅ Dashboard queries are optimized

## Files Modified

1. `/observability/prometheus/rules/recording_rules.yml` - Fixed recording rule syntax and label consistency
2. `/observability/grafana/dashboards/HuleEdu_Service_Deep_Dive_Template.json` - Simplified dashboard queries

## Expected Impact

- Dashboards will now display data instead of 500 errors
- Recording rules will generate proper aggregated metrics
- Query performance improved by using recording rules instead of complex runtime queries
- Consistent metric labeling across all services

## Next Steps

1. Deploy updated observability configuration
2. Verify dashboard functionality in Grafana
3. Monitor recording rule metric generation
4. Update any remaining dashboards that use the old query patterns
