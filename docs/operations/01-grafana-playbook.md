---
type: runbook
service: global
severity: high
last_reviewed: 2025-11-21
---

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
- API Error Rate: `sum(rate({__name__=~".*_http_requests_total",status_code=~"5.."}[5m])) by (service, endpoint)`

### Essay Processing Funnel (Future)

**Purpose**: Track essay flow through processing pipeline
**Key Questions Answered**:

- Where do essays get stuck in the pipeline?
- What's the processing throughput?
- Are there bottlenecks between services?

### Prompt Hydration Reliability

**Purpose**: Ensure downstream services successfully fetch student prompts from Content Service
**Key Questions Answered**:

- Are NLP or CJ services repeatedly failing to hydrate prompt references?
- Which failure modes (missing reference vs Content Service error) are most common?
- Did a deployment introduce sustained prompt fetch regressions?

**Key Panels**:

- Prompt Fetch Failures (rate): `sum(rate(huleedu_nlp_prompt_fetch_failures_total[5m])) by (reason)`
- CJ Prompt Failures (rate): `sum(rate(huleedu_cj_prompt_fetch_failures_total[5m])) by (reason)`
- Prompt Failure Burn-down: `increase(huleedu_nlp_prompt_fetch_failures_total[1h])` and `increase(huleedu_cj_prompt_fetch_failures_total[1h])`
- Alert Threshold Example: fire when `sum(rate(huleedu_cj_prompt_fetch_failures_total[15m])) > 0.05`

### ENG5 NP Runner (Phase 3.3)

For the end-to-end batch workflow (plan/dry-run/execute, CLI flags, failure handling) follow
`Documentation/OPERATIONS/ENG5-NP-RUNBOOK.md`. Complement that runbook with the following dashboards:

- LLM throughput/cost: `sum(rate(llm_requests_total{request_type="comparison"}[5m])) by (provider,model)`
- Prompt hydration health: reuse the panels above to ensure ENG5 batches pull instructions/prompts successfully.
- Admin readiness: `cj_admin_instruction_operations_total` spike detector—ENG5 instructions must exist before executing the runner.

After each run, cross-check the CLI summary and the artefact’s
`validation.runner_status` fields to confirm no partial data.

### CJ Admin Instruction Operations (Phase 3.2)

**Purpose**: Track authenticated admin CRUD activity for assignment instructions.
**Key Questions Answered**:

- Are admin users creating/updating instructions successfully?
- Are there spikes in failed operations (e.g., missing roles, invalid grade scale)?
- Which operations (create/list/get/delete) are exercised most often?

**Key Panels**:

- Success rate: `sum(rate(cj_admin_instruction_operations_total{status="success"}[5m])) by (operation)`
- Failure drill-down: `sum(rate(cj_admin_instruction_operations_total{status="failure"}[5m])) by (operation)`
- Rolling volume: `increase(cj_admin_instruction_operations_total[1h])`
- Alert example: trigger at `sum(rate(cj_admin_instruction_operations_total{status="failure"}[10m])) > 0.05`

## Key Query Library

### Essential PromQL Queries

```promql
# Service Health Check
up{job="content_service"}

# Service Response Times
histogram_quantile(0.95, sum(rate({__name__=~".*_http_request_duration_seconds_bucket"}[5m])) by (le, job))

# Error Rates by Service
rate({__name__=~".*_http_requests_total",status_code=~"5.."}[5m])

# Memory Usage by Container
container_memory_usage_bytes{name=~"huleedu_.*"}

# Prompt Hydration Failure Rate (NLP)
sum(rate(huleedu_nlp_prompt_fetch_failures_total[5m])) by (reason)

# Prompt Hydration Failure Rate (CJ)
sum(rate(huleedu_cj_prompt_fetch_failures_total[5m])) by (reason)

# Prompt Failure Spike Detection (combined)
sum(increase(huleedu_nlp_prompt_fetch_failures_total[1h]))
  + sum(increase(huleedu_cj_prompt_fetch_failures_total[1h]))

# CJ Admin Instruction Success Rate
sum(rate(cj_admin_instruction_operations_total{status="success"}[5m])) by (operation)

# CJ Admin Instruction Failures
sum(rate(cj_admin_instruction_operations_total{status="failure"}[5m])) by (operation)
```

### Essential LogQL Queries

```logql
# Trace by Correlation ID
{service=~".*"} | json | correlation_id="<correlation-id>"

# All Error Logs
{level="error"} | json

# Service-Specific Logs
{service="batch_orchestrator_service"} | json

# Recent Failed Events
{service=~".+"} | json | level="error" | line_format "{{.timestamp}} [{{.level}}] {{.event}}"
```

### Query Best Practices

**Label-First Pattern** (Use labels to narrow scope, then JSON for filtering):

```logql
# ✅ CORRECT: Filter by labels first (uses index)
{service="cj_assessment_service", level="error"} | json | correlation_id="abc-123"

# ❌ WRONG: Scan all logs then filter (slow, no longer supported)
{correlation_id="abc-123"}  # This will fail - correlation_id is not a label
```

**Why This Matters**:
- **Labels are indexed**: Fast filtering (milliseconds) - use for service, level
- **JSON body fields are not indexed**: Require scanning filtered results (seconds) - use for correlation_id, batch_id, etc.
- **Always filter by labels first** to minimize scan volume

**Breaking Change (2025-11-19)**: Correlation ID Label Removed

**What changed**: `correlation_id` and `logger_name` are no longer Loki labels (removed for performance).

**Impact**: Queries using `{correlation_id="..."}` or `{logger_name="..."}` will fail.

**Migration**: Update all queries to use JSON parsing:
- **Old**: `{correlation_id="abc-123"}`
- **New**: `{service=~".*"} | json | correlation_id="abc-123"`

**Why**: High-cardinality labels (UUIDs) cause Loki index explosion. With 100K+ requests/day, correlation_id as a label would create millions of streams, causing severe performance degradation and potential Loki crashes.

### Accessing Loki Logs via Grafana

**Loki Stack Configuration**:
- **Service**: Deployed in `observability/docker-compose.observability.yml`
- **Grafana Access**: <http://localhost:3000>
- **Data Source**: Loki (pre-configured in Grafana)

**Log Collection Pipeline**:
```
Docker Container → json-file driver → /var/lib/docker/containers/*.log
                                           ↓
                                      Promtail (scrapes)
                                           ↓
                                      Loki (indexes)
                                           ↓
                                   Grafana (queries via LogQL)
```

**Docker Logging Driver Configuration**:
- All production services use `json-file` driver with bounded rotation
- Config: 100MB per file × 10 files = 1GB total per container
- Logs compressed and automatically scraped by Promtail
- No manual log shipping required

**Common Query Patterns**:
```logql
# All logs for a specific service
{container_name="huleedu_cj_assessment_service"}

# Filter by correlation ID across all services
{container_name=~"huleedu_.*"} |= "correlation_id" | json | correlation_id="abc-123"

# Error logs across all services
{container_name=~"huleedu_.*"} | json | level="error"

# Filter by service and log level
{container_name="huleedu_llm_provider_service"} | json | level="info" or level="debug"

# Trace a specific batch operation
{container_name=~"huleedu_.*"} | json | batch_id="ENG5-2016" | line_format "{{.timestamp}} {{.service}} {{.event}}"
```

**Accessing Logs via Grafana Explore**:
1. Navigate to Grafana: <http://localhost:3000>
2. Click **Explore** (compass icon in left sidebar)
3. Select **Loki** as the data source
4. Enter LogQL query in query editor
5. Click **Run Query** to view results

### Programmatic Log Access with logcli (LLM Integration)

For LLM agents and automation scripts that need programmatic log access, use `logcli` to query Loki from the command line and export structured log data.

#### Installation & Configuration

**Build from Source**:
```bash
git clone https://github.com/grafana/loki.git
cd loki
make logcli
sudo cp cmd/logcli/logcli /usr/local/bin/logcli
```

**Download Pre-built Binary**:
```bash
# Download from Grafana releases (check for latest version)
wget https://github.com/grafana/loki/releases/download/v3.1.0/logcli-linux-amd64.zip
unzip logcli-linux-amd64.zip
sudo mv logcli-linux-amd64 /usr/local/bin/logcli
chmod +x /usr/local/bin/logcli
```

**Required Configuration**:
```bash
# Set Loki endpoint (required)
export LOKI_ADDR=http://localhost:3100

# Optional: Multi-tenant setups
export LOKI_ORG_ID=tenant1
export LOKI_USERNAME=user
export LOKI_PASSWORD=pass
```

#### LLM Log Export Workflow

**Use Case**: Export bounded log chunks for LLM analysis

**Workflow**: Query → Export JSONL → Filter (jq) → Feed to LLM

**Example** - Export CJ Assessment errors for batch 33 analysis:
```bash
# Step 1: Query Loki with label filters (fast), export as JSONL
logcli query '{service="cj_assessment_service", level="error"}' \
  --from="2025-11-19T10:00:00Z" \
  --to="2025-11-19T20:00:00Z" \
  --limit=500 \
  --output=jsonl \
  > cj_errors.jsonl

# Step 2: Filter by high-cardinality field (batch_id) using jq
jq -r 'select(.batch_id == "33")' < cj_errors.jsonl > batch_33_errors.jsonl

# Step 3: Format for LLM readability (TSV with key fields)
jq -r '[.timestamp, .level, .event, .message, .correlation_id] | @tsv' \
  < batch_33_errors.jsonl > batch_33_for_llm.txt

# Step 4: Feed to LLM agent for analysis
# (LLM reads batch_33_for_llm.txt and provides diagnostic analysis)
```

**Key Patterns for LLM Agents**:
- **Always use `--output=jsonl`** for structured data (easiest to parse)
- **Filter by labels first** (`{service="...", level="..."}`) to minimize scan volume
- **Use absolute time ranges** (`--from`/`--to`) for reproducible queries
- **Bound result sets** (`--limit`) to prevent overwhelming LLM context windows
- **Extract with jq** for high-cardinality field filtering (correlation_id, batch_id, user_id)

#### Background Job Monitoring (ENG5 Runner)

**Use Case**: Real-time monitoring of long-running batch jobs

**Pattern**: Tail logs with `--tail` flag, filter with grep

**Example** - Monitor ENG5 serial-bundle batch progress:
```bash
# Real-time tail of CJ + LLM Provider services for specific batch
logcli query --tail \
  '{service=~"cj_assessment|llm_provider"} | json | bos_batch_id="serial-bundle-20251119"' \
  | grep -E "batch_submitted|comparison_completed|batch_completed|error"
```

**Export batch timeline** for post-execution analysis:
```bash
# Export all events for batch (structured JSONL)
logcli query '{service=~".*"} | json | bos_batch_id="serial-bundle-20251119"' \
  --from="2025-11-19T14:00:00Z" \
  --to="2025-11-19T16:00:00Z" \
  --output=jsonl \
  > batch_timeline.jsonl

# Create sorted timeline (timestamp, service, event)
jq -r '[.timestamp, ."service.name", .event] | @tsv' \
  < batch_timeline.jsonl | sort > timeline.txt
```

#### Output Format Reference

**JSONL (for LLM/automation)** - Structured, one JSON object per line:
```bash
logcli query '{service="cj_assessment_service"}' --output=jsonl
```

**Raw (messages only)** - Just log message content, no metadata:
```bash
logcli query '{service="cj_assessment_service"}' --output=raw
```

**Default (formatted)** - Human-readable with timestamps and labels (not ideal for automation)

#### Query Label Metadata

**List all available labels**:
```bash
logcli labels
```

**List values for a specific label** (e.g., discover all service names):
```bash
logcli labels service --since=24h
```

**Analyze label cardinality**:
```bash
logcli series '{service="cj_assessment_service"}' --analyze-labels
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

**Last Updated**: 2025-11-20 – Added logcli CLI documentation for programmatic access, LLM integration, and background job monitoring
**Next Review**: After service log volume increases
