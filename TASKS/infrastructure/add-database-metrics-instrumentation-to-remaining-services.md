---
id: 'add-database-metrics-instrumentation-to-remaining-services'
title: 'Add Database Metrics Instrumentation to Remaining Services'
type: 'task'
status: 'completed'
priority: 'medium'
domain: 'infrastructure'
service: ''
owner_team: 'agents'
owner: ''
program: ''
created: '2025-11-30'
last_updated: '2025-11-30'
epic: 'EPIC-009'
related: ['docs/product/epics/observability-metrics-alignment-epic.md']
labels: ['observability', 'metrics', 'database']
---
# Add Database Metrics Instrumentation to Remaining Services

## Objective

Instrument the 7 services with PostgreSQL databases that are missing database metrics, enabling visibility in Grafana Database Health dashboards.

## Context

The Database Health dashboards only show 6 of 13 services with PostgreSQL databases. 7 services are missing `setup_database_monitoring()` instrumentation in their DI providers.

## Services Missing Database Metrics

| Service | Database Container | Priority | Notes |
|---------|-------------------|----------|-------|
| batch_conductor_service | huleedu_batch_conductor_db | Medium | Pipeline state operations |
| content_service | huleedu_content_service_db | Medium | Has custom metrics, needs standard DB metrics |
| file_service | huleedu_file_service_db | Medium | File metadata operations |
| identity_service | huleedu_identity_db | Medium | Multiple repositories |
| nlp_service | huleedu_nlp_db | Low | Kafka worker, no HTTP scraping |

**Note**: email_service and entitlements_service already have DatabaseMetrics instrumentation.

## Implementation Pattern

Follow existing pattern from instrumented services (e.g., `spellchecker_service`):

### 1. Add to service's `di.py`

```python
from huleedu_service_libs.database import DatabaseMetrics, setup_database_monitoring

@provide(scope=Scope.APP)
def provide_database_metrics(self, engine: AsyncEngine, settings: Settings) -> DatabaseMetrics:
    """Provide database metrics monitoring."""
    return setup_database_monitoring(
        engine=engine,
        service_name=settings.SERVICE_NAME
    )
```

### 2. Ensure SERVICE_NAME uses underscores

In `config.py`, use underscore format (NOT hyphens):
```python
SERVICE_NAME: str = "batch_conductor_service"  # correct
SERVICE_NAME: str = "batch-conductor-service"  # wrong - hyphens become underscores in Prometheus
```

### 3. Inject DatabaseMetrics into repository

Update repository provider to accept and use `DatabaseMetrics`:
```python
@provide(scope=Scope.APP)
async def provide_repository(
    self, settings: Settings, database_metrics: DatabaseMetrics, engine: AsyncEngine
) -> RepositoryProtocol:
    repo = PostgreSQLRepository(settings, database_metrics, engine)
    return repo
```

## Files to Modify Per Service

For each service in `services/<service_name>/`:
- `config.py` - Verify SERVICE_NAME format (underscores, not hyphens)
- `di.py` - Add `provide_database_metrics` provider
- Repository implementation - Accept DatabaseMetrics parameter

## Reference Implementation

See `services/spellchecker_service/di.py:243-247` for working example.

## Success Criteria

- [x] All 5 services instrumented with `setup_database_monitoring()` in their DI providers
- [x] Metrics visible in Prometheus (added email, entitlements, websocket, language_tool to prometheus.yml)
- [x] No duplicate metric registrations (shared engine pattern in batch_conductor_service)
- [x] Database Health Overview dashboard updated with all 10 services

## Implementation Summary

**Completed 2025-11-30:**

1. **Prometheus Configuration** (`observability/prometheus/prometheus.yml`):
   - Added 4 missing service scrape targets: email_service, entitlements_service, websocket_service, language_tool_service

2. **DatabaseMetrics Instrumentation** (5 services):
   - `services/batch_conductor_service/di.py` - Added shared AsyncEngine and DatabaseMetrics provider
   - `services/content_service/di.py` - Added DatabaseMetrics provider
   - `services/file_service/di.py` - Added DatabaseMetrics provider
   - `services/identity_service/di.py` - Added DatabaseMetrics provider
   - `services/nlp_service/di.py` - Added DatabaseMetrics provider (Kafka worker - no HTTP scraping)

3. **Grafana Dashboards** (3 dashboard files updated):
   - `HuleEdu_Database_Health_Overview.json` - Added 4 new services to all 6 panels
   - `HuleEdu_Database_Deep_Dive.json` - Added 4 new services to service selector
   - `HuleEdu_Database_Troubleshooting.json` - Added 4 new services to all 5 panels

**Note:** SERVICE_NAME format standardization (hyphens vs underscores) is a separate task per user decision.

## Related

- `libs/huleedu_service_libs/src/huleedu_service_libs/database/metrics.py` - DatabaseMetrics implementation
- `observability/grafana/dashboards/database/` - Database dashboards
- `observability/prometheus/rules/database-alerts.yml` - Database alert rules
