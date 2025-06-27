---
description: Observability Rules and Patterns for HuleDu
globs: 
alwaysApply: false
---
# 071: Observability Rules and Patterns

## 1. Core Philosophy
- **Business Insights First**: Every metric should answer a business or operational question
- **Correlation Over Collection**: Better to correlate existing data than collect more data
- **Actionable Alerts**: Alerts must have clear resolution steps - no "FYI" alerts
- **Documentation as Code**: All observability decisions must be documented in playbooks

## 2. Metrics Standards

### 2.1. Custom Metrics Naming Convention
**MUST** follow these established patterns based on metric purpose:

#### Service-Level Operational Metrics
Pattern: `<service_prefix>_<metric>_<unit>`
- API Gateway: `gateway_` → `gateway_http_requests_total`
- Class Management: `cms_` → `cms_http_requests_total`
- Batch Orchestrator: `bos_` → `bos_http_requests_total`
- Spell Checker: `spell_checker_` → `spell_checker_operations_total`
- File Service: `file_service_` → `file_service_files_uploaded_total`

#### Business Intelligence Metrics (Cross-Service)
Pattern: `huleedu_<metric>_<unit>`
- `huleedu_pipeline_execution_total` (BOS)
- `huleedu_spellcheck_corrections_made` (Spell Checker)
- `huleedu_phase_transition_duration_seconds` (BOS)

#### Shared Infrastructure Metrics
Pattern: `<descriptive_name>_<unit>`
- `kafka_message_queue_latency_seconds` (used across services)

**Use Service Prefix** for service-specific operational metrics (HTTP, errors, service operations)
**Use `huleedu_` Prefix** for business intelligence metrics that provide cross-service insights
**Use Descriptive Names** for shared infrastructure metrics

### 2.2. Metric Labels Strategy
- **Service Identification**: Always include service-identifying labels
- **Business Context**: Include labels that enable business analysis (file_type, validation_status)
- **Operational Context**: Include labels for debugging (endpoint, method, status_code)
- **FORBIDDEN**: High cardinality labels (user_id, correlation_id as labels)

### 2.3. Service Metrics Requirements
**ALL services MUST implement**:
- Standard health metrics via service library
- Service-specific business metrics (minimum 1-2 per service)
- Error rate tracking with status codes
- Request duration histograms with meaningful buckets

## 3. Alert Management

### 3.1. Alert Categories
- **Critical**: Service completely down, data loss risk
- **Warning**: Performance degradation, error rate increase
- **Info**: Capacity planning, trend notifications

### 3.2. Alert Design Principles
- **Clear Trigger Conditions**: Precise thresholds with context
- **Escalation Paths**: Defined ownership and escalation procedures
- **Resolution Documentation**: Every alert has runbook entry
- **Test Regularly**: Alert rules must be validated during deployments

### 3.3. Required Alert Rules
**MUST implement for all services**:
- ServiceDown: `up == 0` for >1 minute
- HighErrorRate: 5xx errors >0.1/sec for >2 minutes
- Service-specific business threshold alerts

## 4. Dashboard Standards

### 4.1. Dashboard Categories
- **System Health**: Cross-service operational view
- **Service Specific**: Individual service deep-dive
- **Business Intelligence**: Essay processing funnel, user behavior
- **Troubleshooting**: Correlation ID tracking, error investigation

### 4.2. Dashboard Design Principles
- **Answer Specific Questions**: Each dashboard addresses defined operational questions
- **Progressive Disclosure**: Start with overview, drill down to details
- **Consistent Time Ranges**: Standardize on 1h, 6h, 24h, 7d views
- **Performance Optimized**: Avoid high-cardinality queries in real-time panels

### 4.3. Required Dashboard Panels
**System Health Dashboard MUST include**:
- Service availability percentage
- Error rate by service
- Response time percentiles
- Resource utilization overview

## 5. Log Management

### 5.1. Structured Logging Requirements
- **JSON Format**: All services use structured JSON logging in containers
- **Correlation IDs**: All log entries include correlation_id when available
- **Standard Fields**: timestamp, level, service, event, correlation_id
- **Business Context**: Include relevant business identifiers (batch_id, essay_id)

### 5.2. Log Correlation Patterns
- Use correlation IDs for request tracing across services
- Promote key fields to Loki labels for fast querying
- Implement log sampling for high-volume debug logs
- Maintain log retention policies based on operational needs

## 6. Container Integration

### 6.1. Service Library Integration

#### Quart Services (Standard Pattern)
**MUST** use established patterns:
- **Metrics Definition**: Create `<service>/metrics.py` with `get_http_metrics()` and `get_business_metrics()` functions
- **Metrics Storage**: Store in `app.extensions["metrics"]` during startup
- **Middleware Setup**: Call `setup_standard_service_metrics_middleware(app, "service_prefix")` in `@app.before_serving`
- **Port Configuration**: Document metrics endpoint port in service README

```python
# metrics.py - Standard pattern for Quart services
def get_http_metrics() -> dict[str, Any]:
    all_metrics = get_metrics()
    return {
        "request_count": all_metrics.get("request_count"),
        "request_duration": all_metrics.get("request_duration"),
    }

# app.py - Middleware setup
@app.before_serving
async def startup() -> None:
    await initialize_services(app, settings, container)
    from huleedu_service_libs.metrics_middleware import setup_standard_service_metrics_middleware
    setup_standard_service_metrics_middleware(app, "service_prefix")

# startup_setup.py - Storage in app extensions
metrics = get_http_metrics()
app.extensions = getattr(app, "extensions", {})
app.extensions["metrics"] = metrics
```

#### FastAPI Services (Different Pattern)
- **Metrics Class**: Define all metrics in dedicated `<service>/app/metrics.py`
- **DI Provider**: Provide both metrics class and `CollectorRegistry` via Dishka with `Scope.APP`
- **Injection Pattern**: Inject metrics class into route handlers using `FromDishka[MetricsClass]`

```python
# FastAPI pattern (API Gateway example)
class GatewayMetrics:
    def __init__(self) -> None:
        self.http_requests_total = Counter(...)

@router.post("/endpoint")
async def handler(metrics: FromDishka[GatewayMetrics]):
    metrics.http_requests_total.inc()
```

### 6.2. Docker Compose Patterns
- Observability stack in separate docker-compose.observability.yml
- Volume mounts for configuration files
- Proper service dependencies (alertmanager depends on prometheus)
- Health checks for all observability containers

## 7. Development Workflow Integration

### 7.1. Testing Observability
- Use Grafana dashboards during E2E test execution
- Validate new metrics appear in Prometheus during development
- Test alert rules with controlled service failures
- Document metric behaviors in test scenarios

### 7.2. Deployment Monitoring
- **REQUIRED**: Monitor service health for 15 minutes post-deployment
- Validate new metrics are collecting data
- Check alert rule functionality after configuration changes
- Update playbook documentation with lessons learned

## 8. Service Ports and Testing Patterns

### 8.1. Metrics Endpoint Ports
**Direct Service Access:**
- `file_service`: Port 7001 → `curl http://localhost:7001/metrics`
- `cj_assessment_service`: Port 9090 → `curl http://localhost:9090/metrics` (inside container)
- `batch_orchestrator_service`: Port 5000 → `curl http://localhost:5000/metrics`
- `spell_checker_service`: Port 8002 → `curl http://localhost:8002/metrics`

**Docker External Mapping:**
- `cj_assessment_service`: Port 8095 → `curl http://localhost:8095/metrics` (from host)

### 8.2. Prometheus Query Testing
**From Host:**
```bash
# BROKEN - host curl often fails with JSON parsing
curl -s "http://localhost:9090/api/v1/query?query=up"

# WORKING - query from inside Prometheus container
docker exec huleedu_prometheus wget -qO- "http://localhost:9090/api/v1/query?query=up"
```

**Container Rebuild Protocol:**
- After modifying service code, ALWAYS rebuild containers before testing
- Pattern: `docker compose down && docker build <services> && docker compose up -d`
- Metrics middleware changes require container rebuild to take effect

### 8.3. Middleware Troubleshooting
**Missing Metrics Data (metrics defined but no values):**
- Check `setup_standard_service_metrics_middleware(app, "prefix")` call in `@app.before_serving`
- Verify `app.extensions["metrics"]` contains `"request_count"` and `"request_duration"` keys
- Ensure metrics initialization happens BEFORE middleware setup in startup sequence

**Port Access Issues:**
- Use `docker exec <container> curl http://localhost:<port>/metrics` for direct testing
- External port mapping may differ from internal container ports
- Check `prometheus.yml` for correct target configuration

## 9. Performance and Resource Management

### 9.1. Resource Limits
- Observability stack should use <500MB total memory
- Prometheus retention: 15 days default
- Loki retention: 30 days default
- Monitor observability stack resource usage weekly

### 9.2. Query Performance
- Use recording rules for expensive calculations
- Implement query timeouts in Grafana
- Monitor Prometheus query performance via internal metrics
- Optimize high-cardinality label usage

---

**Implementation Priority**: Core metrics → Alerts → Dashboards → Advanced features
**Review Cycle**: Monthly review of alert effectiveness and dashboard usage
