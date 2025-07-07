# HuleEdu Grafana Dashboards

This directory contains the three-tier dashboard system for HuleEdu monitoring.

## Dashboard Overview

### Tier 1: System Health Overview
- **File**: `HuleEdu_System_Health_Overview.json`
- **UID**: `huleedu-system-health`
- **Purpose**: 10,000-foot view of platform health
- **Key Panels**: Service availability, global error rate, active alerts, infrastructure status

### Tier 2: Service Deep Dive
- **File**: `HuleEdu_Service_Deep_Dive_Template.json`
- **UID**: `huleedu-service-deep-dive`
- **Purpose**: 1,000-foot view of individual service performance
- **Key Features**: Service variable templating, conditional business metrics, live logs

### Tier 3: Troubleshooting
- **File**: `HuleEdu_Troubleshooting.json`
- **UID**: `huleedu-troubleshooting`
- **Purpose**: Ground-level distributed tracing via correlation IDs
- **Key Features**: Correlation ID search, chronological log timeline, service involvement map

## Import Instructions

1. Access Grafana UI at http://localhost:3000
2. Navigate to Dashboards → Import
3. Upload each JSON file in order (Tier 1 → Tier 2 → Tier 3)
4. Select the appropriate Prometheus and Loki data sources when prompted

## Progressive Disclosure Navigation

- Tier 1 → Tier 2: Click on service metrics to drill down
- Tier 2 → Tier 3: Click on correlation IDs in logs to trace requests
- All dashboards have navigation links in the top bar

## Database Monitoring Dashboards

### Database Health Overview
- **File**: `HuleEdu_Database_Health_Overview.json`
- **UID**: `huleedu-database-health`
- **Purpose**: System-wide PostgreSQL database health monitoring
- **Key Panels**: Connection pools across all services, query performance, transaction success rates
- **Coverage**: All 6 PostgreSQL services (Batch Orchestrator, Essay Lifecycle, CJ Assessment, Class Management, Result Aggregator, Spell Checker)

### Database Service Deep Dive
- **File**: `HuleEdu_Database_Deep_Dive.json`
- **UID**: `huleedu-database-deep-dive`
- **Purpose**: Service-specific database performance analysis
- **Key Features**: Service selector variable, detailed connection pool metrics, query breakdown by operation
- **Usage**: Select service from dropdown to analyze database performance

### Database Troubleshooting
- **File**: `HuleEdu_Database_Troubleshooting.json`
- **UID**: `huleedu-database-troubleshooting`
- **Purpose**: Database performance correlation and investigation
- **Key Features**: Performance outliers, connection pool exhaustion detection, cross-service load correlation

## Import Instructions

1. Access Grafana UI at http://localhost:3000
2. Navigate to Dashboards → Import
3. Upload each JSON file in order (System → Service → Troubleshooting → Database dashboards)
4. Select the appropriate Prometheus and Loki data sources when prompted

## Progressive Disclosure Navigation

- Tier 1 → Tier 2: Click on service metrics to drill down
- Tier 2 → Tier 3: Click on correlation IDs in logs to trace requests
- Database Health → Database Deep Dive: Click on service-specific database metrics
- All dashboards have navigation links in the top bar

## Alert Integration

Prometheus alerts in `prometheus/rules/service_alerts.yml` include:
- `dashboard_url`: Links to relevant dashboard for investigation
- `runbook_url`: Links to operational playbook for resolution steps
- Database alerts link to appropriate database monitoring dashboards