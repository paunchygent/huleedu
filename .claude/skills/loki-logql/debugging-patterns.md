# Loki LogQL Debugging Patterns for HuleEdu

**Skill Extension**: loki-logql
**Purpose**: Debugging workflows using LogQL queries
**Last Updated**: 2025-11-20

---

## Pattern 1: Trace Request Across Services

```logql
# Step 1: Extract correlation_id from entry point
{service="api_gateway_service"} | json | line_format "{{.correlation_id}}"

# Step 2: Query all services with that correlation_id
{service=~".*"} | json | correlation_id="<extracted-id>"
  | line_format "{{.timestamp}} [{{.service.name}}] {{.event}}"
```

**CLI Version**:
```bash
CID=$(logcli query '{service="api_gateway_service"} | json | line_format "{{.correlation_id}}"' --limit=1)
logcli query "{service=~\".*\"} | json | correlation_id=\"${CID}\"" --limit=100
```

---

## Pattern 2: Find Errors for Specific Entity

```logql
# By batch_id
{service="cj_assessment_service", level="error"} | json | batch_id="33"

# By user_id (across all services)
{service=~".*", level="error"} | json | user_id="user-123"

# By organization
{service=~".*", level="error"} | json | org_id="org-456"
```

---

## Pattern 3: Time-Based Error Analysis

```logql
# Error frequency over time (5-minute windows)
sum by (service) (
  count_over_time({service=~".*", level="error"} [5m])
)

# Error spike detection (compare to 1 hour ago)
sum by (service) (
  count_over_time({service=~".*", level="error"} [5m])
) - sum by (service) (
  count_over_time({service=~".*", level="error"} [5m] offset 1h)
)
```

---

## Pattern 4: Export for Statistical Analysis

```bash
# Export all errors for a service
logcli query '{service="llm_provider_service", level="error"}' \
  --from="2025-11-20T10:00:00Z" --to="2025-11-20T20:00:00Z" \
  --limit=1000 --output=jsonl > errors.jsonl

# Group by error_type
jq -r '.error_type' < errors.jsonl | sort | uniq -c | sort -rn

# Calculate error rate per hour
jq -r '.timestamp[0:13]' < errors.jsonl | uniq -c

# Find most common correlation_ids (frequent errors)
jq -r '.correlation_id' < errors.jsonl | sort | uniq -c | sort -rn | head -10
```

---

## Pattern 5: Trace + Log Correlation

```bash
# Step 1: Find slow request in Loki
logcli query '{service="api_gateway_service"} | json | duration_ms > 5000' \
  --limit=1 --output=jsonl > slow.jsonl

# Step 2: Extract trace_id
TRACE_ID=$(jq -r '.trace_id' < slow.jsonl)

# Step 3: Get all logs for this trace
logcli query "{service=~\".*\"} | json | trace_id=\"${TRACE_ID}\""

# Step 4: View in Jaeger
open "http://localhost:16686/trace/${TRACE_ID}"
```

---

## Pattern 6: Filter JSON Logs from Mixed Formats

```bash
# Problem: Service outputs both console and JSON logs
# Solution: Filter to JSON lines first

# Export only JSON logs
docker logs huleedu_identity_service 2>&1 | grep -a '^{' > json_logs.txt

# Parse with jq
docker logs huleedu_identity_service 2>&1 | grep -a '^{' | jq 'select(.trace_id)'

# In LogQL (if using direct queries)
{service="identity_service"} | json  # This works if Loki only ingests JSON
```

---

## Pattern 7: Multi-Field Filtering

```logql
# AND conditions
{service="cj_assessment_service"} | json
  | batch_id="33"
  | level="error"

# OR conditions (regex)
{service="cj_assessment_service"} | json
  | error_type=~"timeout_error|rate_limit_exceeded"

# NOT condition
{service="llm_provider_service"} | json
  | error_type!="rate_limit_exceeded"
```

---

## Pattern 8: Extract Specific Fields

```logql
# Single field
{service="api_gateway_service"} | json | line_format "{{.correlation_id}}"

# Multiple fields (CSV-like)
{service="api_gateway_service"} | json
  | line_format "{{.timestamp}},{{.method}},{{.path}},{{.status_code}},{{.duration_ms}}"

# Formatted output
{service="api_gateway_service"} | json
  | line_format "{{.timestamp}} [{{.method}}] {{.path}} status={{.status_code}} duration={{.duration_ms}}ms"
```

---

## Pattern 9: Count Operations

```logql
# Count logs per service
sum by (service) (count_over_time({service=~".*"} [1h]))

# Count errors by service
sum by (service) (count_over_time({service=~".*", level="error"} [1h]))

# Count specific events
sum by (service) (
  count_over_time({service=~".*"} | json | event="batch_submitted" [1h])
)
```

---

## Pattern 10: Validation Queries

```logql
# Check if trace_id exists in logs
{service="api_gateway_service"} | json | trace_id!=""

# Count logs with trace context
count_over_time({service="api_gateway_service"} | json | trace_id!="" [5m])

# Validate trace_id format (32-char hex) - use CLI
logcli query '{service="api_gateway_service"} | json | trace_id!=""' \
  --limit=1 --output=jsonl | jq -r '.trace_id' | grep -E '^[0-9a-f]{32}$'
```

---

## Common Mistakes

### Mistake 1: High-Cardinality Labels
```logql
# WRONG
{correlation_id="abc-123"}

# RIGHT
{service="api_gateway_service"} | json | correlation_id="abc-123"
```

### Mistake 2: No Label Filter
```logql
# SLOW (scans all logs)
{service=~".*"} | json | batch_id="33"

# FAST (uses label index)
{service="cj_assessment_service"} | json | batch_id="33"
```

### Mistake 3: Forgetting JSON Parse
```logql
# WRONG (treats JSON as raw text)
{service="api_gateway_service"} | correlation_id="abc-123"

# RIGHT
{service="api_gateway_service"} | json | correlation_id="abc-123"
```

---

## Performance Tips

1. **Always filter by labels first**:
   ```logql
   {service="...", level="..."} | json | ...  # Uses index
   ```

2. **Use specific time ranges**:
   ```bash
   --from="2025-11-20T10:00:00Z" --to="2025-11-20T11:00:00Z"
   ```

3. **Limit result sets**:
   ```bash
   --limit=500
   ```

4. **Filter JSON lines in shell**:
   ```bash
   grep -a '^{' | jq '...'
   ```

---

## Integration with Prometheus

```bash
# Step 1: Identify issue in Prometheus
curl -s 'http://localhost:9090/api/v1/query?query=rate(http_requests_total{status_code="500"}[5m])'

# Step 2: Query Loki for error logs
logcli query '{service="api_gateway_service", level="error"}' --limit=100

# Step 3: Extract correlation_id and trace across services
CID=$(logcli query '{service="api_gateway_service", level="error"}' --limit=1 --output=jsonl | jq -r '.correlation_id')
logcli query "{service=~\".*\"} | json | correlation_id=\"${CID}\""
```

---

## Useful CLI Commands

```bash
# Set Loki address (one-time)
export LOKI_ADDR=http://localhost:3100

# Query with absolute time range
logcli query '{service="api_gateway_service"}' \
  --from="2025-11-20T10:00:00Z" \
  --to="2025-11-20T11:00:00Z"

# Output formats
--output=default    # Human-readable
--output=jsonl      # One JSON object per line
--output=raw        # Raw log lines only

# Tail logs (real-time)
logcli query '{service="api_gateway_service"}' --tail

# Labels query
logcli labels  # List all labels
logcli labels service  # List all values for 'service' label
```

---

## References

- Rule 071.5: LLM Debugging with Observability
- `.claude/skills/loki-logql/reference.md`: LogQL syntax
- Loki Docs: <https://grafana.com/docs/loki/latest/logql/>
