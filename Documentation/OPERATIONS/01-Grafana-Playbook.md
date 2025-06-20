# HuleEdu Grafana Playbook

**Purpose**: This document serves as the team's shared brain for observability. It contains dashboard guides, key queries, and alert runbooks to empower effective debugging and monitoring.

## Dashboard Guides

### System Health Overview

**Purpose**: Provides at-a-glance view of service availability and performance
**Key Questions Answered**:

- Are all services operational?
- What's the current error rate across services?
- Are there any resource bottlenecks?

**Key Panels**:

- Service Health: `count(up{job=~".*_service"} == 1) / count(up{job=~".*_service"}) * 100`
- API Error Rate: `sum(rate(http_requests_total{status_code=~"5.."}[5m])) by (endpoint)`

### Essay Processing Funnel (Future)

**Purpose**: Track essay flow through processing pipeline
**Key Questions Answered**:

- Where do essays get stuck in the pipeline?
- What's the processing throughput?
- Are there bottlenecks between services?

## Key Query Library

### Essential PromQL Queries

```promql
# Service Health Check
up{job="content_service"}

# Service Response Times
histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket[5m])) by (le, job))

# Error Rates by Service
rate(http_requests_total{status_code=~"5.."}[5m])

# Memory Usage by Container
container_memory_usage_bytes{name=~"huleedu_.*"}
```

### Essential LogQL Queries

```logql
# Trace by Correlation ID
{correlation_id="<correlation-id>"}

# All Error Logs
{service=~".+"} | json | level="error" or level="critical"

# Service-Specific Logs
{service="batch_orchestrator_service"} | json

# Recent Failed Events
{service=~".+"} | json | level="error" | line_format "{{.timestamp}} [{{.level}}] {{.event}}"
```

## Alert Runbooks

### ServiceDown Alert

**Trigger**: Service has been unreachable for more than 1 minute
**Severity**: Critical

**Investigation Steps**:

1. Check container status: `docker ps | grep <service_name>`
2. Check container logs: `docker logs huleedu_<service_name>`
3. Check resource usage: `docker stats huleedu_<service_name>`

**Resolution Steps**:

1. Attempt service restart: `docker compose restart <service_name>`
2. If restart fails, check for configuration issues in docker-compose files
3. If persistent, check for resource constraints or dependency issues
4. **Escalate**: If service fails to restart after 2 attempts, notify on-call lead

### HighErrorRate Alert

**Trigger**: Service experiencing >0.1 5xx errors per second for 2+ minutes
**Severity**: Warning

**Investigation Steps**:

1. Identify affected endpoints in Grafana dashboard
2. Check recent deployments or configuration changes
3. Review service logs for error patterns: `{service="<service_name>"} | json | level="error"`

**Resolution Steps**:

1. If recent deployment, consider rollback
2. Check for downstream dependency issues
3. Monitor for auto-recovery within 10 minutes
4. **Escalate**: If error rate persists >15 minutes, notify team lead

## Usage Patterns

### Daily Monitoring Workflow

1. **Morning Check**: Review System Health Overview dashboard
2. **During Development**: Use correlation ID tracking for debugging
3. **Post-Deployment**: Monitor error rates and response times for 15 minutes
4. **Issue Investigation**: Start with service logs, then correlate with metrics

### E2E Test Monitoring

When running comprehensive tests:

1. Open Essay Processing Funnel dashboard
2. Watch real-time metrics during test execution
3. Note any delays or bottlenecks in pipeline flow
4. Use correlation IDs to trace specific test scenarios

### Troubleshooting Workflow

1. **Start with Alerts**: Check Prometheus alerts page for active issues
2. **Service Level**: Use service-specific dashboards for detailed investigation
3. **Log Correlation**: Use correlation IDs to trace request flow
4. **Resource Check**: Monitor container resources if performance issues suspected

## Best Practices

- **Always use correlation IDs** when investigating multi-service issues
- **Check both metrics and logs** - metrics show what, logs show why
- **Monitor after changes** - Always observe systems for 15 minutes post-deployment
- **Document new queries** - Add useful queries to this playbook for team sharing
- **Update runbooks** - Refine alert responses based on actual incident experience

---

**Last Updated**: Phase 2A Implementation
**Next Review**: After API Gateway integration
