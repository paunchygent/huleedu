# How-To: Debugging with HuleEdu Observability Stack

**For**: Developers debugging HuleEdu services
**Tools**: Loki (logs), Prometheus (metrics), Jaeger (traces), Grafana (dashboards)
**Last Updated**: 2025-11-20

---

## Quick Start: Three-Tool Decision

| You Need To... | Use This Tool | Access Point |
|----------------|---------------|--------------|
| Find why a request failed | Loki | <http://localhost:3000> (Grafana → Explore → Loki) |
| Check if a service is down | Prometheus | <http://localhost:9090> |
| See why a request is slow | Jaeger | <http://localhost:16686> |

---

## Tutorial 1: Debug a Failed Request

**Scenario**: User reports "Batch submission failed"

### Step 1: Get the correlation_id

Option A: From user-facing response
```json
{
  "error": "Batch submission failed",
  "correlation_id": "abc-123-def-456"
}
```

Option B: From API Gateway logs
```bash
# Open Grafana → Explore → Loki
# Query:
{service="api_gateway_service", level="error"} | json | line_format "{{.correlation_id}} {{.error_message}}"
```

### Step 2: Trace across all services

```bash
# In Grafana Loki Explore:
{service=~".*"} | json | correlation_id="abc-123-def-456"
  | line_format "{{.timestamp}} [{{.service.name}}] {{.event}}"
```

**Sample Output**:
```
2025-11-20T10:00:01Z [api_gateway_service] Request received
2025-11-20T10:00:02Z [batch_orchestrator_service] Batch submitted
2025-11-20T10:00:03Z [cj_assessment_service] Processing batch
2025-11-20T10:00:04Z [llm_provider_service] LLM request sent
2025-11-20T10:00:05Z [llm_provider_service] ERROR: Rate limit exceeded  ← FOUND ISSUE
```

### Step 3: Check error frequency (Prometheus)

```promql
# In Prometheus UI (http://localhost:9090):
rate(anthropic_api_requests_total{status="429"}[5m])
```

### Step 4: Fix and Verify

After fix, verify using same correlation pattern:
```bash
{service="llm_provider_service", level="error"} | json
  | error_type="rate_limit_exceeded"
```

---

## Tutorial 2: Debug Slow Performance

**Scenario**: Dashboard shows 95th percentile latency > 5s

### Step 1: Check Prometheus for latency

```promql
# In Prometheus:
histogram_quantile(0.95,
  rate(http_request_duration_seconds_bucket{service="api_gateway_service"}[5m])
)
```

### Step 2: Find slow traces in Jaeger

1. Open <http://localhost:16686>
2. Service: `api_gateway_service`
3. Operation: `POST /api/v1/assessments/batch`
4. **Min Duration**: `5s`
5. Click "Find Traces"

### Step 3: Analyze trace waterfall

Click on a slow trace to see timeline:
```
api_gateway_service: POST /api/v1/assessments/batch (5.2s)
└─ batch_orchestrator_service: submit_batch (5.1s)
   └─ cj_assessment_service: process_batch (5.0s)
      └─ llm_provider_service: anthropic_api_call (4.8s) ← BOTTLENECK
```

### Step 4: Get detailed logs with trace_id

Copy trace_id from Jaeger (e.g., `73db05229e4a5d4a0728a76f164d192b`)

```bash
# In Grafana Loki:
{service=~".*"} | json | trace_id="73db05229e4a5d4a0728a76f164d192b"
  | line_format "{{.timestamp}} [{{.service.name}}] {{.event}} duration={{.duration_ms}}ms"
```

### Step 5: Root cause analysis

Check LLM provider metrics:
```promql
llm_provider_queue_depth  # If > 100, requests are queuing
rate(anthropic_api_requests_total[5m])  # Request rate
```

---

## Tutorial 3: Debug Stuck Batch Processing

**Scenario**: Batch 33 stuck at 34/50 comparisons for 10 minutes

### Step 1: Query batch logs

```bash
# In Grafana Loki:
{service="cj_assessment_service"} | json | batch_id="33"
  | line_format "{{.timestamp}} {{.event}} {{.completed}}/{{.total}}"
```

### Step 2: Extract correlation_id

```bash
# Find batch_submitted event:
{service="cj_assessment_service"} | json
  | batch_id="33"
  | event="batch_submitted"
  | line_format "{{.correlation_id}}"
```

Output: `10e99e69-a4e2-4916-a862-2ca03baafa16`

### Step 3: Trace entire workflow

```bash
{service=~".*"} | json | correlation_id="10e99e69-a4e2-4916-a862-2ca03baafa16"
  | line_format "{{.timestamp}} [{{.service.name}}] {{.event}}"
```

### Step 4: Check for errors

```bash
{service=~".*", level="error"} | json
  | correlation_id="10e99e69-a4e2-4916-a862-2ca03baafa16"
```

### Step 5: Check queue metrics

```promql
# In Prometheus:
llm_provider_queue_depth  # Are requests backing up?
rate(cj_llm_requests_total{status="error"}[5m])  # Error rate
```

---

## Tutorial 4: Export Logs for Analysis

**Scenario**: Need to analyze error patterns across multiple batches

### Step 1: Install logcli (one-time setup)

```bash
# macOS
brew install logcli

# Or download from: https://github.com/grafana/loki/releases
```

### Step 2: Configure logcli

```bash
export LOKI_ADDR=http://localhost:3100
```

### Step 3: Export logs

```bash
logcli query '{service="cj_assessment_service", level="error"}' \
  --from="2025-11-20T10:00:00Z" \
  --to="2025-11-20T20:00:00Z" \
  --limit=1000 \
  --output=jsonl > errors.jsonl
```

### Step 4: Analyze with jq

```bash
# Count by error type
jq -r '.error_type' < errors.jsonl | sort | uniq -c | sort -rn

# Filter by batch_id
jq 'select(.batch_id == "33")' < errors.jsonl > batch33.jsonl

# Extract specific fields
jq -r '[.timestamp, .event, .error_type, .correlation_id] | @tsv' < batch33.jsonl
```

**Output**:
```
2025-11-20T10:05:23Z    comparison_failed    timeout_error    abc-123
2025-11-20T10:07:45Z    comparison_failed    validation_error def-456
```

---

## Tutorial 5: Validate OTEL Trace Context

**Scenario**: Verify services are emitting trace_id/span_id correctly

### Step 1: Run validation script

```bash
./scripts/validate_otel_trace_context.sh
```

**Sample Output**:
```
=== Validation Matrix ===
| Service               | Container Running | Logs Have trace_id | Format Valid | % With Context | Status |
| api_gateway_service   | YES               | YES                | YES          | 73%            | PASS   |
| spellchecker_service  | YES               | YES                | YES          | 10%            | PASS   |
```

### Step 2: Validate single service

```bash
./scripts/validate_otel_trace_context.sh api_gateway_service
```

### Step 3: Manual validation

```bash
# Check for trace_id in logs (filter JSON lines first)
docker logs huleedu_api_gateway_service 2>&1 | grep -a '^{' | jq 'select(.trace_id)' | head -3

# Verify format (32-char hex)
docker logs huleedu_api_gateway_service 2>&1 | grep -a '^{' | jq -r '.trace_id' | head -1 | wc -c
# Should output: 33 (32 chars + newline)
```

---

## Common Pitfalls

### Pitfall 1: Using High-Cardinality Fields as Labels

❌ **WRONG**:
```logql
{correlation_id="abc-123"}
```

✅ **CORRECT**:
```logql
{service="api_gateway_service"} | json | correlation_id="abc-123"
```

### Pitfall 2: Grepping Docker Logs Individually

❌ **WRONG**:
```bash
docker logs huleedu_cj_assessment_service | grep "batch_id"
docker logs huleedu_batch_orchestrator | grep "batch_id"
docker logs huleedu_llm_provider | grep "batch_id"
```

✅ **CORRECT**:
```logql
{service=~".*"} | json | batch_id="33"
```

### Pitfall 3: Mixed Log Formats

**Problem**: Services output both console and JSON logs

❌ **WRONG**:
```bash
docker logs huleedu_identity_service | jq '.'
# ERROR: parse error (console logs aren't JSON)
```

✅ **CORRECT**:
```bash
docker logs huleedu_identity_service 2>&1 | grep -a '^{' | jq '.'
```

**Root Cause**: Logger created at module import time (before `configure_service_logging()`)

---

## Dashboards

### Grafana Dashboards

Pre-configured dashboards available at <http://localhost:3000>:

1. **Troubleshooting Dashboard** (ID: troubleshooting)
   - Correlation ID search
   - Service log panels
   - Error timeline

2. **Service Health Dashboard**
   - Uptime per service
   - Request rate
   - Error rate
   - Latency (p50, p95, p99)

3. **LLM Provider Dashboard**
   - Queue depth
   - Request rate by provider (Anthropic)
   - Error rate by type
   - Token usage

### Accessing Dashboards

```bash
# Open Grafana
open http://localhost:3000

# Default credentials:
# Username: admin
# Password: admin (change on first login)
```

---

## Advanced: Correlation ID + Trace ID

When both exist, use strategically:

**Use trace_id for**:
- Precise timing analysis
- Span relationships
- Performance bottleneck identification

**Use correlation_id for**:
- Full workflow context (includes non-traced operations)
- Business logic debugging
- Cross-service request flow

**Combined workflow**:
```bash
# 1. Get all logs for correlation_id
logcli query '{service=~".*"} | json | correlation_id="abc-123"' --output=jsonl > workflow.jsonl

# 2. Extract trace_id
TRACE_ID=$(jq -r '.trace_id // empty' < workflow.jsonl | grep -v '^$' | head -1)

# 3. View precise timing in Jaeger
open "http://localhost:16686/trace/${TRACE_ID}"

# 4. Get detailed context from Loki
logcli query "{service=~\".*\"} | json | trace_id=\"${TRACE_ID}\""
```

---

## Troubleshooting the Observability Stack

### Loki not accessible

```bash
# Check Loki container
docker ps | grep loki

# Check Loki health
curl http://localhost:3100/ready
```

### Jaeger not accessible

```bash
# Check Jaeger container
docker ps | grep jaeger

# Check Jaeger health
curl http://localhost:16686/api/services
```

### Prometheus not accessible

```bash
# Check Prometheus container
docker ps | grep prometheus

# Check Prometheus health
curl http://localhost:9090/-/healthy
```

### No traces in Jaeger

**Possible causes**:
1. Services not sending traces to Jaeger
2. OTEL_EXPORTER_OTLP_ENDPOINT not configured
3. No active HTTP requests (spans only created during requests)

**Verification**:
```bash
# Check if service has OTEL endpoint configured
docker inspect huleedu_api_gateway_service | jq '.[0].Config.Env | .[] | select(. | contains("OTEL_EXPORTER"))'

# Trigger a request (API Gateway on port 8080 in Docker, 4001 locally)
curl -X GET http://localhost:8080/healthz

# Check Jaeger after 10 seconds
curl -s "http://localhost:16686/api/traces?service=api_gateway_service&limit=10" | jq '.data | length'
```

---

## References

- Rule 071.5: LLM Debugging with Observability
- `.claude/skills/loki-logql/reference.md`: LogQL syntax reference
- `scripts/validate_otel_trace_context.sh`: OTEL validation tool
- Loki Documentation: <https://grafana.com/docs/loki/latest/>
- Jaeger Documentation: <https://www.jaegertracing.io/docs/>
