# Grafana Dashboard Implementation Task

## Objective

Implement a comprehensive three-tier dashboard system for HuleEdu that follows the Progressive Disclosure Playbook, enabling efficient troubleshooting from system-wide overview to individual request tracing.

## Current State

### ✅ Observability Foundation Complete
- **Standardized Metrics**: All services use consistent naming (`<service_prefix>_<metric>_<unit>`)
- **Prometheus Integration**: Successfully scraping metrics from all services
- **Alert Rules**: Updated to use standardized metric patterns
- **Structured Logging**: JSON logging with correlation IDs implemented
- **Loki Integration**: Log aggregation configured via promtail

### ✅ Available Metrics by Service
```
Service-Level Operational Metrics:
- gateway_http_requests_total, gateway_http_request_duration_seconds
- cms_http_requests_total, cms_http_request_duration_seconds  
- bos_http_requests_total, bos_http_request_duration_seconds
- spell_checker_http_requests_total, spell_checker_operations_total
- file_service_http_requests_total, file_service_http_request_duration_seconds
- cj_assessment_http_requests_total, cj_assessment_http_request_duration_seconds

Business Intelligence Metrics:
- huleedu_pipeline_execution_total
- huleedu_spellcheck_corrections_made
- huleedu_phase_transition_duration_seconds
- huleedu_cj_comparisons_made
- huleedu_cj_assessment_duration_seconds

Infrastructure Metrics:
- kafka_message_queue_latency_seconds
- up (service availability)
- Standard container metrics (CPU, memory)
```

## Implementation Strategy: Progressive Disclosure Playbook

### Tier 1: System Health Dashboard (10,000-foot view)
**Purpose**: Answer "Is the HuleEdu platform operational right now?"
**Target Audience**: First responders, daily health checks

#### Required Panels:
1. **Service Availability Stat Panel**
   - Query: `count(up{job=~".*_service"} == 1) / count(up{job=~".*_service"}) * 100`
   - Display: Single large percentage with RED/GREEN thresholds
   - Thresholds: Green >95%, Yellow 90-95%, Red <90%

2. **Global Error Rate Time Series**
   - Query: `sum(rate({__name__=~".*_http_requests_total",status_code=~"5.."}[5m]))`
   - Display: Line graph with alert threshold overlay
   - Time Range: Last 6 hours default

3. **Active Alerts Panel**
   - Source: Alertmanager API integration
   - Display: Alert list with severity colors
   - Include: Alert name, service, duration, severity

4. **Core Infrastructure Health Grid**
   - Kafka: Connection status, lag metrics
   - PostgreSQL: Connection pools, query performance
   - Redis: Memory usage, connection count
   - Layout: 2x2 stat panel grid

#### Success Criteria:
- Dashboard loads in <2 seconds
- All panels show real data
- Color coding provides immediate visual health status
- Links to Tier 2 dashboards functional

### Tier 2: Service Deep Dive Dashboard (1,000-foot view)  
**Purpose**: Answer "What's happening inside a specific service showing problems?"
**Implementation**: Single template dashboard with `$service` variable

#### Required Variables:
- `$service`: Multi-select dropdown populated from `label_values(up, job)`
- `$time_range`: Time range selector (1h, 6h, 24h, 7d)

#### Required Panels:
1. **Request Rate & Duration Graphs**
   - Request Rate: `rate({__name__=~"${service}_http_requests_total"}[5m])`
   - Duration P95: `histogram_quantile(0.95, rate({__name__=~"${service}_http_request_duration_seconds_bucket"}[5m]))`
   - Display: Side-by-side time series

2. **Error Rate by Endpoint Table**
   - Query: `rate({__name__=~"${service}_http_requests_total",status_code=~"5.."}[5m]) by (endpoint)`
   - Display: Table with endpoint, error rate, total requests
   - Sort: By error rate descending

3. **Business Metrics Panel** (Conditional)
   - Batch Orchestrator: `huleedu_pipeline_execution_total`
   - Spell Checker: `huleedu_spellcheck_corrections_made`
   - CJ Assessment: `huleedu_cj_comparisons_made`
   - Display: Service-specific business metric graphs

4. **Live Logs Panel**
   - Query: `{service="${service}"} | json`
   - Display: Log stream with correlation ID highlighting
   - Filters: Error level dropdown, endpoint filter

#### Success Criteria:
- Service selection dynamically updates all panels
- Business metrics appear only for relevant services
- Logs correlate with metric spikes
- Drill-down links to Tier 3 functional

### Tier 3: Troubleshooting Dashboard (Ground-level view)
**Purpose**: Answer "What happened to a specific user request across all services?"
**Implementation**: Correlation ID-based distributed tracing

#### Required Variables:
- `$correlation_id`: Text input box for correlation ID
- `$time_window`: Time range around the correlation ID event

#### Required Panels:
1. **Correlation ID Input Panel**
   - Type: Text box variable
   - Validation: UUID format
   - Default: Empty with placeholder text

2. **Distributed Trace Timeline**
   - Query: `{correlation_id="${correlation_id}"} | json | line_format "{{.timestamp}} [{{.service}}] {{.level}}: {{.message}}"`
   - Display: Log panel sorted by timestamp
   - Features: Service name highlighting, log level colors

3. **Service Involvement Map**
   - Query: `count by (service) ({correlation_id="${correlation_id}"})`
   - Display: Stat panel showing which services handled the request
   - Layout: Horizontal bar chart

4. **Request Flow Metrics**
   - Queries: Service-specific request counts during correlation ID timeframe
   - Display: Time series overlay showing request volume
   - Purpose: Identify bottlenecks or failures

#### Success Criteria:
- Correlation ID search returns chronological trace
- Service involvement clearly visible
- Logs provide complete request story
- Performance metrics contextualize log events

## Implementation Tasks

### Phase 1: Foundation Setup
- [ ] Create Grafana folder structure: `/HuleEdu/System Health`, `/HuleEdu/Service Deep Dive`, `/HuleEdu/Troubleshooting`
- [ ] Configure Prometheus data source with proper retention settings
- [ ] Configure Loki data source with correlation ID label extraction
- [ ] Set up Alertmanager data source for alert panel integration

### Phase 2: Tier 1 Dashboard
- [ ] Create "HuleEdu System Health" dashboard
- [ ] Implement service availability stat panel with thresholds
- [ ] Build global error rate time series with annotations
- [ ] Add active alerts panel with Alertmanager integration
- [ ] Create infrastructure health grid (Kafka, PostgreSQL, Redis)
- [ ] Configure refresh rates and time ranges
- [ ] Add drill-down links to Tier 2 dashboards

### Phase 3: Tier 2 Dashboard  
- [ ] Create "HuleEdu Service Deep Dive" template dashboard
- [ ] Implement `$service` variable with dynamic population
- [ ] Build request rate and duration panels with service filtering
- [ ] Create error rate by endpoint table
- [ ] Add conditional business metrics panels per service
- [ ] Integrate Loki log panel with service filtering
- [ ] Configure drill-down links to Tier 3 dashboard

### Phase 4: Tier 3 Dashboard
- [ ] Create "HuleEdu Troubleshooting" dashboard
- [ ] Implement correlation ID input variable
- [ ] Build distributed trace timeline from Loki
- [ ] Create service involvement map
- [ ] Add contextual metrics panels
- [ ] Configure time range correlation with log events

### Phase 5: Integration & Polish
- [ ] Update alert rules with dashboard links in annotations
- [ ] Add dashboard links to runbooks in `01-Grafana-Playbook.md`
- [ ] Create dashboard screenshots for documentation
- [ ] Implement dashboard versioning and backup strategy
- [ ] Configure dashboard permissions and sharing

## Technical Requirements

### Data Sources Configuration
- **Prometheus**: `http://prometheus:9090` with 15-day retention
- **Loki**: `http://loki:3100` with correlation_id label promotion
- **Alertmanager**: `http://alertmanager:9093` for alert integration

### Dashboard Standards
- **Refresh Rate**: 30s default, 5s for troubleshooting
- **Time Ranges**: 1h, 6h, 24h, 7d with custom option
- **Color Scheme**: Consistent RED/YELLOW/GREEN for health states
- **Panel Titles**: Clear, actionable descriptions
- **Tooltips**: Include units, calculation methods

### Performance Targets
- **Load Time**: <3 seconds for any dashboard
- **Query Performance**: <1 second for individual panels
- **Resource Usage**: <100MB RAM per active dashboard session

## Success Criteria

### Functional Requirements
- [ ] All three dashboard tiers operational and interconnected
- [ ] Service variable correctly filters all relevant panels
- [ ] Correlation ID tracing provides complete request visibility
- [ ] Alert-to-dashboard linking reduces incident response time
- [ ] Log integration eliminates context switching

### Quality Requirements  
- [ ] Dashboards follow industry-standard progressive disclosure
- [ ] Visual design provides immediate status clarity
- [ ] Performance meets <3 second load time requirement
- [ ] Error handling gracefully manages missing data
- [ ] Documentation enables team self-service

### Business Requirements
- [ ] Solo developer can troubleshoot incidents without escalation
- [ ] Mean time to detection (MTTD) reduced by 50%
- [ ] Mean time to resolution (MTTR) reduced by 40%
- [ ] Operational overhead remains minimal for small team
- [ ] Dashboard maintenance requires <2 hours/month

## Deliverables

1. **Three Production Dashboards**: System Health, Service Deep Dive, Troubleshooting
2. **Updated Documentation**: Grafana Playbook with dashboard usage guides
3. **Alert Integration**: All alerts link to relevant dashboards and runbooks
4. **Team Training Materials**: Screenshots and usage examples
5. **Maintenance Procedures**: Dashboard backup, version control, update process

---

**Priority**: High  
**Estimated Effort**: 2-3 sprints  
**Dependencies**: Observability standardization (✅ Complete)  
**Success Metrics**: MTTD/MTTR reduction, team self-service capability