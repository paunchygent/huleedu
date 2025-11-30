---
type: epic
id: EPIC-009
title: Observability & Metrics Alignment
status: draft
phase: 1
sprint_target: TBD
created: 2025-11-30
last_updated: 2025-11-30
---

# EPIC-009: Observability & Metrics Alignment

## Summary

Align the HuleEdu observability stack to ensure consistent metrics collection, Prometheus scraping, and dashboard coverage across all services.

**Business Value**: Complete visibility into all service health, database performance, and system behavior for proactive monitoring and rapid incident response.

**Scope Boundaries**:
- **In Scope**: Prometheus configuration for missing services, DatabaseMetrics instrumentation, dashboard enhancements
- **Out of Scope**: SERVICE_NAME standardization (separate infrastructure task), new alerting rules, production AlertManager configuration

## User Stories

### US-009.1: Add Missing Services to Prometheus Configuration

**As a** system operator
**I want** all HTTP-enabled services to be scraped by Prometheus
**So that** I have complete visibility into service metrics.

**Acceptance Criteria**:
- [ ] Add email_service (port 8080) to prometheus.yml
- [ ] Add entitlements_service (port 8083) to prometheus.yml
- [ ] Add websocket_service (port 8080) to prometheus.yml
- [ ] Add language_tool_service (port 8085) to prometheus.yml
- [ ] All new targets show "UP" in Prometheus targets page at <http://localhost:9091>

**Files to Modify**:
- `observability/prometheus/prometheus.yml`

**Complexity**: Low

---

### US-009.2: Add DatabaseMetrics to batch_conductor_service

**As a** developer
**I want** batch_conductor_service to emit standard database metrics
**So that** I can monitor PostgreSQL performance for pipeline state operations.

**Acceptance Criteria**:
- [ ] Create database monitoring setup function following spellchecker_service pattern
- [ ] Add DatabaseMetrics provider to di.py
- [ ] Wire DatabaseMetrics into PostgreSQLBatchStateRepositoryImpl
- [ ] Verify `batch_conductor_service_database_*` metrics in /metrics endpoint

**Files to Modify**:
- `services/batch_conductor_service/metrics.py` (create)
- `services/batch_conductor_service/di.py`
- `services/batch_conductor_service/implementations/postgres_batch_state_repository.py`

**Reference**: `services/spellchecker_service/di.py:243-247`

---

### US-009.3: Add DatabaseMetrics to content_service

**As a** developer
**I want** content_service to emit standard database metrics alongside existing custom metrics
**So that** connection pool and query performance are observable.

**Acceptance Criteria**:
- [ ] Add database monitoring (coexisting with PrometheusContentMetrics)
- [ ] Add DatabaseMetrics provider to di.py
- [ ] Wire into ContentRepository
- [ ] Verify both custom and standard database metrics appear in /metrics

**Files to Modify**:
- `services/content_service/metrics.py` (extend)
- `services/content_service/di.py`
- `services/content_service/implementations/content_repository_impl.py`

---

### US-009.4: Add DatabaseMetrics to file_service

**As a** developer
**I want** file_service to emit standard database metrics
**So that** file metadata database operations are observable.

**Acceptance Criteria**:
- [ ] Create database monitoring setup function
- [ ] Add DatabaseMetrics provider to di.py
- [ ] Wire into FileRepository
- [ ] Verify `file_service_database_*` metrics in /metrics endpoint

**Files to Modify**:
- `services/file_service/metrics_database.py` (create)
- `services/file_service/di.py`
- `services/file_service/implementations/file_repository_impl.py`

---

### US-009.5: Add DatabaseMetrics to identity_service

**As a** developer
**I want** identity_service to emit standard database metrics
**So that** authentication and session database operations are observable.

**Acceptance Criteria**:
- [ ] Create database monitoring setup function
- [ ] Add DatabaseMetrics provider to di.py
- [ ] Wire into all repository implementations (UserRepo, SessionRepo, UserProfileRepo, AuditLogger)
- [ ] Verify `identity_service_database_*` metrics in /metrics endpoint

**Files to Modify**:
- `services/identity_service/metrics.py` (create)
- `services/identity_service/di.py`
- Multiple repository implementations in `services/identity_service/implementations/`

**Complexity**: High (multiple repositories)

---

### US-009.6: Add DatabaseMetrics to nlp_service

**As a** developer
**I want** nlp_service to have database metrics infrastructure
**So that** DB operations are instrumented for future observability.

**Acceptance Criteria**:
- [ ] Create database monitoring setup function
- [ ] Add DatabaseMetrics provider to di.py
- [ ] Wire into NlpRepository
- [ ] Document limitation: Kafka worker with no HTTP endpoint for Prometheus scraping

**Note**: nlp_service is a pure Kafka worker. Metrics will be registered but not scrapeable via HTTP. Consider push gateway in future enhancement.

**Files to Modify**:
- `services/nlp_service/metrics.py` (create or extend)
- `services/nlp_service/di.py`
- `services/nlp_service/repositories/nlp_repository.py`

---

### US-009.7: Enhance Dashboards with Full Service Coverage

**As a** system operator
**I want** Grafana dashboards to include all instrumented services
**So that** I have complete visibility across the platform.

**Acceptance Criteria**:
- [ ] Database Health Overview includes batch_conductor, content, file, identity panels
- [ ] System Health Overview includes email, entitlements, websocket, language_tool availability
- [ ] Service Deep Dive template variable includes all services
- [ ] No broken panels or "No data" errors for configured services

**Files to Modify**:
- `observability/grafana/dashboards/system/HuleEdu_System_Health_Overview.json`
- `observability/grafana/dashboards/database/HuleEdu_Database_Health_Overview.json`
- `observability/grafana/dashboards/services/HuleEdu_Service_Deep_Dive_Template.json`

**Note**: Use Context7 for Grafana JSON best practices before modifications.

---

## Technical Architecture

### DatabaseMetrics Pattern

Reference implementation from `services/spellchecker_service/di.py`:

```python
from huleedu_service_libs.database import DatabaseMetrics, setup_database_monitoring

@provide(scope=Scope.APP)
def provide_database_metrics(
    self, engine: AsyncEngine, settings: Settings
) -> DatabaseMetrics:
    return setup_database_monitoring(
        engine=engine, service_name=settings.SERVICE_NAME
    )
```

### Prometheus Scrape Target Pattern

```yaml
- job_name: '<service_name>'
  static_configs:
    - targets: ['<container_name>:<port>']
  metrics_path: '/metrics'
```

### Current Instrumentation State

**12 services in Prometheus**: content, batch_orchestrator, spellchecker, essay_lifecycle_api, file, cj_assessment, class_management, llm_provider, api_gateway, result_aggregator, identity, batch_conductor

**4 services missing from Prometheus**: email (8080), entitlements (8083), websocket (8080), language_tool (8085)

**1 service not scrapeable**: nlp_service (Kafka worker, no HTTP)

## Implementation Order

| Order | Story | Rationale |
|-------|-------|-----------|
| 1 | US-009.1 | Unblocks visibility for existing /metrics endpoints |
| 2 | US-009.2 | Critical pipeline service |
| 3 | US-009.3 | Core data service |
| 4 | US-009.4 | File upload operations |
| 5 | US-009.5 | Auth service (high complexity) |
| 6 | US-009.6 | Worker service (limited scraping benefit) |
| 7 | US-009.7 | Depends on all instrumentation being complete |

## Related Tasks

- `TASKS/infrastructure/add-database-metrics-instrumentation-to-remaining-services.md` - Covers US-009.2 through US-009.6

## Dependencies

- `huleedu_service_libs.database` module (exists)
- Docker network connectivity for Prometheus scraping
- Grafana provisioning for dashboard updates

## Notes

- SERVICE_NAME standardization (underscores vs hyphens) is tracked separately as an infrastructure task
- nlp_service metrics require future enhancement (push gateway or HTTP sidecar)
- Dashboard JSON modifications should be validated with Context7 for Grafana best practices
