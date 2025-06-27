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

## Alert Integration

Prometheus alerts in `prometheus/rules/service_alerts.yml` include:
- `dashboard_url`: Links to relevant dashboard for investigation
- `runbook_url`: Links to operational playbook for resolution steps