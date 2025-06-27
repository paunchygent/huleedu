# Observability Stack Migration Notes

## What Was Moved

All observability-related configuration files have been moved from the project root to the `observability/` directory:

### Files Moved:
- `prometheus.yml` → `observability/prometheus/prometheus.yml`
- `prometheus/rules/` → `observability/prometheus/rules/`
- `promtail-config.yml` → `observability/promtail/promtail-config.yml`
- `promtail-config-original.yml` → `observability/promtail/promtail-config-original.yml`
- `alertmanager.yml` → `observability/alertmanager/alertmanager.yml`
- `grafana/dashboards/` → `observability/grafana/dashboards/`
- `docker-compose.observability.yml` → `observability/docker-compose.observability.yml`

### Updates Made:

1. **Docker Compose Paths**: Updated all volume mount paths in `docker-compose.observability.yml`
2. **Network Configuration**: Added external network declaration for standalone operation
3. **PDM Scripts**: Updated all `obs-*` scripts to use the new location
4. **Symlink**: Created `grafana-dashboards` symlink in root for easy access

## How to Use

### Starting Services:
```bash
# From project root
docker compose -f observability/docker-compose.observability.yml up -d

# Or use PDM script
pdm run obs-up
```

### Managing Services:
```bash
# View logs
pdm run obs-logs

# Restart services
pdm run obs-restart

# Stop services
pdm run obs-down
```

### Important Notes:

1. **Network Dependency**: The observability stack requires the main infrastructure to be running first (for the network)
2. **Config Changes**: When editing configs, remember they're now in `observability/` subdirectories
3. **Dashboard Import**: Dashboards are now at `observability/grafana/dashboards/`

## Benefits:

- ✅ Cleaner root directory
- ✅ Logical organization
- ✅ All observability configs in one place
- ✅ Easier to manage and backup
- ✅ PDM scripts still work seamlessly