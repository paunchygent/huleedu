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
**MUST** follow pattern: `huleedu_<service>_<metric>_<unit>`

Examples:
- `huleedu_files_uploaded_total` (counter)
- `huleedu_spellcheck_corrections_made` (histogram)
- `huleedu_essay_processing_duration_seconds` (histogram)

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
**MUST** use huleedu-service-libs patterns:
- Metrics creation in startup_setup.py
- DI-provided CollectorRegistry (not metric instances)
- Access metrics via current_app.extensions["metrics"]
- **FORBIDDEN**: Creating Counter/Histogram in DI providers

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

## 8. Performance and Resource Management

### 8.1. Resource Limits
- Observability stack should use <500MB total memory
- Prometheus retention: 15 days default
- Loki retention: 30 days default
- Monitor observability stack resource usage weekly

### 8.2. Query Performance
- Use recording rules for expensive calculations
- Implement query timeouts in Grafana
- Monitor Prometheus query performance via internal metrics
- Optimize high-cardinality label usage

---

**Implementation Priority**: Core metrics → Alerts → Dashboards → Advanced features
**Review Cycle**: Monthly review of alert effectiveness and dashboard usage
