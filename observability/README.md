# HuleEdu Observability Stack

This directory contains all configuration files for the HuleEdu observability stack.

## Directory Structure

```
observability/
├── docker-compose.observability.yml  # Main observability stack definition
├── prometheus/                       # Prometheus configuration
│   ├── prometheus.yml               # Main Prometheus config
│   └── rules/                       # Alert rules
│       └── service_alerts.yml
├── promtail/                        # Log collector configuration
│   ├── promtail-config.yml          # Active Promtail config
│   └── promtail-config-original.yml # Original config (backup)
├── alertmanager/                    # Alert manager configuration
│   └── alertmanager.yml
├── grafana/                         # Grafana dashboards
│   └── dashboards/                  # JSON dashboard definitions
│       ├── HuleEdu_System_Health_Overview.json
│       ├── HuleEdu_Service_Deep_Dive_Template.json
│       └── HuleEdu_Troubleshooting.json
└── loki/                            # Loki configuration (uses defaults)
```

## Starting the Observability Stack

From the project root:

```bash
# Start the entire observability stack
docker compose -f observability/docker-compose.observability.yml up -d

# Or use the convenience script
pdm run obs-up
```

## Stopping the Observability Stack

```bash
# Stop all observability services
docker compose -f observability/docker-compose.observability.yml down

# Or use the convenience script
pdm run obs-down
```

## Accessing Services

- **Prometheus**: http://localhost:9091
- **Grafana**: http://localhost:3000 (admin/admin)
- **Alertmanager**: http://localhost:9094
- **Loki**: http://localhost:3100 (API only)

## Configuration Files

### Prometheus
- Main config: `prometheus/prometheus.yml`
- Alert rules: `prometheus/rules/service_alerts.yml`
- Scrape targets are auto-discovered via Docker labels

### Promtail
- Active config: `promtail/promtail-config.yml`
- Collects logs from all Docker containers
- Parses JSON logs and extracts labels

### Grafana
- Dashboards: `grafana/dashboards/`
- Import guide: See [documentation/user_guides/grafana-dashboard-import-guide.md](../documentation/user_guides/grafana-dashboard-import-guide.md)

### Alertmanager
- Config: `alertmanager/alertmanager.yml`
- Currently configured for local development (no external notifications)

## Common Operations

### View logs
```bash
docker compose -f observability/docker-compose.observability.yml logs -f [service]
```

### Restart a service
```bash
docker compose -f observability/docker-compose.observability.yml restart [service]
```

### Update configurations
1. Edit the relevant config file
2. Restart the affected service
3. Verify changes in the UI

## Troubleshooting

See the [Grafana Dashboard Import Guide](../documentation/user_guides/grafana-dashboard-import-guide.md) for common issues and solutions.