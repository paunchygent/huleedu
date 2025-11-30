# HuleEdu Grafana Dashboards

Domain-organized dashboard system following SRP principles. Subdirectories map to Grafana folders via `foldersFromFilesStructure`.

## Directory Structure

```
dashboards/
├── system/                    # Platform-wide health
│   └── HuleEdu_System_Health_Overview.json
├── services/                  # Service-level monitoring
│   ├── HuleEdu_Service_Deep_Dive_Template.json
│   └── HuleEdu_LLM_Prompt_Cache.json
├── database/                  # PostgreSQL monitoring
│   ├── HuleEdu_Database_Health_Overview.json
│   ├── HuleEdu_Database_Deep_Dive.json
│   └── HuleEdu_Database_Troubleshooting.json
├── cj-assessment/             # Comparative Judgment domain
│   └── HuleEdu_CJ_Assessment_Deep_Dive.json
└── troubleshooting/           # Request tracing and debugging
    ├── HuleEdu_Troubleshooting.json
    └── tier3-distributed-tracing.json
```

## Dashboards by Domain

### System (`system/`)

| Dashboard | UID | Purpose |
|-----------|-----|---------|
| System Health Overview | `huleedu-system-health` | 10,000-foot platform health view |

### Services (`services/`)

| Dashboard | UID | Purpose |
|-----------|-----|---------|
| Service Deep Dive | `huleedu-service-deep-dive` | Per-service performance with variable templating |
| LLM Prompt Cache | `huleedu-llm-prompt-cache` | Prompt cache efficiency and token savings |

### Database (`database/`)

| Dashboard | UID | Purpose |
|-----------|-----|---------|
| Database Health Overview | `huleedu-database-health` | Cross-service PostgreSQL health |
| Database Deep Dive | `huleedu-database-deep-dive` | Service-specific database analysis |
| Database Troubleshooting | `huleedu-database-troubleshooting` | Connection pool and query investigation |

### CJ Assessment (`cj-assessment/`)

| Dashboard | UID | Purpose |
|-----------|-----|---------|
| CJ Assessment Deep Dive | `huleedu-cj-assessment-deep-dive` | BT SE diagnostics, quality flags, batch health |

### Troubleshooting (`troubleshooting/`)

| Dashboard | UID | Purpose |
|-----------|-----|---------|
| Troubleshooting | `huleedu-troubleshooting` | Correlation ID request tracing |
| Distributed Tracing | `tier3-distributed-tracing` | OpenTelemetry span visualization |

## Provisioning

Dashboards auto-load via Grafana provisioning with `foldersFromFilesStructure: true`. Subdirectories become Grafana folders.

**Reload options:**
- Wait 30 seconds for auto-scan
- Restart: `docker restart huleedu_grafana`
- Full cycle: `pdm run obs-down && pdm run obs-up`

## Alert Rules

Alert rules are organized by domain in `prometheus/rules/`:

| File | Domain |
|------|--------|
| `service-health-alerts.yml` | Service availability, error rates, LLM cache |
| `distributed-tracing-alerts.yml` | Tracing, latency, circuit breakers |
| `infrastructure-alerts.yml` | Kafka, Redis, PostgreSQL exporters |
| `database-alerts.yml` | Connection pools, query latency, transactions |
| `cj-assessment-alerts.yml` | BT SE diagnostics, quality flag spikes |

## Navigation Flow

```
System Health → Service Deep Dive → Troubleshooting
     ↓                ↓
Database Health → Database Deep Dive
     ↓
CJ Assessment (domain-specific)
```

All dashboards include top-bar navigation links.
