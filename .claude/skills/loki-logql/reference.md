# Loki LogQL Query Specialist - Detailed Reference

Comprehensive guide for querying HuleEdu logs using Loki and LogQL.

## Table of Contents

1. [Loki Architecture in HuleEdu](#loki-architecture-in-huleedu)
2. [LogQL Query Fundamentals](#logql-query-fundamentals)
3. [Common Query Patterns](#common-query-patterns)
4. [Promtail Configuration](#promtail-configuration)
5. [Performance Optimization](#performance-optimization)
6. [Integration with Grafana](#integration-with-grafana)
7. [Context7 Integration](#context7-integration)
8. [Best Practices](#best-practices)

---

## Loki Architecture in HuleEdu

### Stack Components

**Loki Service**:
- **External Port**: 3100
- **Internal URL**: `http://loki:3100`
- **Purpose**: Log aggregation and storage
- **Config**: `/observability/loki/loki-config.yml`

**Promtail Service**:
- **Purpose**: Log collection from Docker containers
- **Config**: `/observability/promtail/promtail-config.yml`
- **Network**: `huledu-reboot_huleedu_internal_network`
- **Scrape Interval**: 5 seconds

### Log Flow

```
Docker Container → Promtail → Loki → Grafana/API Query
                     ↓
              Label Extraction
              JSON Parsing
              Pipeline Stages
```

---

## LogQL Query Fundamentals

### Query Structure

```logql
{label_selector} |= "filter" | parser | label_filter
```

**Components**:
1. **Label Selector**: `{container="huleedu_content_service"}`
2. **Line Filter**: `|= "ERROR"` (contains), `!= "DEBUG"` (not contains)
3. **Parser**: `| json` (parse JSON logs)
4. **Label Filter**: `| level="error"` (filter on extracted labels)

### Label Selectors

**Exact Match**:
```logql
{container="huleedu_content_service"}
```

**Regex Match**:
```logql
{container=~"huleedu_.*"}               # All HuleEdu services
{container=~"huleedu_(content|batch).*"} # Specific services
```

**Multiple Labels**:
```logql
{container=~"huleedu_.*", level="error"}
```

### Line Filters

**Case-Sensitive Contains**:
```logql
{container=~"huleedu_.*"} |= "ERROR"
{container=~"huleedu_.*"} |= "correlation_id"
```

**Case-Insensitive** (use regex):
```logql
{container=~"huleedu_.*"} |~ "(?i)error"
```

**Multiple Filters** (AND):
```logql
{container=~"huleedu_.*"} |= "ERROR" |= "batch_id"
```

**Negation**:
```logql
{container=~"huleedu_.*"} != "DEBUG"
{container=~"huleedu_.*"} !~ "healthcheck"
```

### JSON Parser

**Parse JSON Logs**:
```logql
{container=~"huleedu_.*"} | json
```

**Extract Specific Fields**:
```logql
{container=~"huleedu_.*"} | json | level="error" | correlation_id!=""
```

**Available JSON Fields** (from structlog):
- `timestamp` - ISO timestamp
- `level` - Log level (INFO, ERROR, DEBUG, WARNING)
- `event` - Log message
- `correlation_id` - Request correlation ID
- `event_id` - Event ID (for Kafka events)
- `event_type` - Event type
- `source_service` - Service that emitted the event
- `logger_name` - Logger instance name
- Custom fields (varies by log message)

---

## Common Query Patterns

### 1. Correlation ID Tracing

**Most Common Pattern** (trace request across all services):
```logql
{container=~"huleedu_.*"} |= "correlation_id_value"
```

**With Time Range** (last 1 hour):
```logql
{container=~"huleedu_.*"} |= "correlation_id_value" [1h]
```

**Extract Full Context**:
```logql
{container=~"huleedu_.*"} | json | correlation_id="correlation_id_value"
```

**CRITICAL**: Never use `--since` arguments when searching for correlation IDs (per user's CLAUDE.md instructions)

### 2. Error Investigation

**All Errors Across Services**:
```logql
{container=~"huleedu_.*"} |= "ERROR"
```

**Errors with Correlation Context**:
```logql
{level="error"} | json | correlation_id!=""
```

**Service-Specific Errors**:
```logql
{container="huleedu_batch_orchestrator_service"} |= "ERROR"
```

**Errors by Type**:
```logql
{container=~"huleedu_.*"} | json | level="error" | event=~".*timeout.*"
```

### 3. Service Health Monitoring

**Service Startup/Shutdown**:
```logql
{container="huleedu_content_service"} |~ "started|stopped|shutdown"
```

**Kafka Connection Issues**:
```logql
{container=~"huleedu_.*"} | json | event=~".*kafka.*" | level="error"
```

**Database Errors**:
```logql
{container=~"huleedu_.*"} |~ "database|postgres|sqlalchemy" |= "error"
```

### 4. Event Processing Analysis

**All Events by Type**:
```logql
{container=~"huleedu_.*"} | json | event_type="EssaySubmittedEvent"
```

**Event Processing Errors**:
```logql
{container=~"huleedu_.*"} | json | event_id!="" | level="error"
```

**Queue Latency Issues**:
```logql
{container=~"huleedu_.*"} |= "kafka_message_queue_latency_seconds"
```

### 5. Performance Investigation

**Slow Requests** (if duration logged):
```logql
{container=~"huleedu_.*"} | json | duration > 5.0
```

**Rate Limiting Events**:
```logql
{container=~"huleedu_.*"} |~ "rate limit|throttle|quota"
```

### 6. Multi-Service Flow Tracing

**Follow Request Through Services**:
```logql
{container=~"huleedu_(content|batch|essay).*"} |= "correlation_id_value"
```

**Event Envelope Tracking**:
```logql
{container=~"huleedu_.*"} | json | event_id="event_id_value"
```

---

## Promtail Configuration

### Service Discovery

**Docker Service Discovery**:
```yaml
scrape_configs:
- job_name: huleedu_services
  docker_sd_configs:
    - host: unix:///var/run/docker.sock
      refresh_interval: 5s
      filters:
        - name: network
          values: [huledu-reboot_huleedu_internal_network]
```

**Auto-Labeling**:
- `container_name` → `container` label
- `service` from docker-compose → `service` label

### Pipeline Stages (Current HuleEdu Configuration)

**JSON Parsing** (extracts fields, preserves original line):
```yaml
- json:
    expressions:
      timestamp: timestamp
      level: level
      event: event
      correlation_id: correlation_id
      event_id: event_id
      event_type: event_type
      source_service: source_service
      logger_name: logger_name
```

**Timestamp Parsing**:
```yaml
- timestamp:
    source: timestamp
    format: RFC3339
    fallback_formats:
      - RFC3339Nano
      - "2006-01-02T15:04:05.000Z"
```

**Label Promotion** (LOW cardinality only):
```yaml
- labels:
    level:
    service:
```

### Label Strategy (2025-11-19: Cardinality Optimized)

**Promoted Labels** (indexed, fast queries, 25 streams total):
- `level` - Log level (5 values: debug, info, warning, error, critical)
- `service` - Service name (~15-20 services)
- `container` - Docker container name (auto-promoted by Promtail)

**JSON Body Fields** (queryable with `| json` filter):
- `correlation_id` - Request correlation ID (UUID per request - unbounded)
- `logger_name` - Logger instance (~50-100 Python loggers)
- `event` - Log message content (unbounded)
- `event_id`, `event_type`, `source_service` - Event metadata
- `timestamp` - ISO timestamp

**Query Pattern for High-Cardinality Fields**:
```logql
{service="content_service"} | json | correlation_id="<uuid>"
```

**Rationale**: Fields with >100 unique values/day stay in JSON body to prevent Loki index explosion (millions of streams). The current configuration maintains 25 streams for optimal performance.

---

## Performance Optimization

### Query Optimization

**Avoid**:
```logql
# Bad: Regex in high-frequency panels
{container=~"huleedu_.*"} |~ ".*error.*"

# Bad: Broad time ranges without filters
{container=~"huleedu_.*"} [24h]
```

**Prefer**:
```logql
# Good: Exact label match + line filter
{container="huleedu_batch_orchestrator_service"} |= "ERROR"

# Good: Narrow time range + specific label
{container=~"huleedu_.*", level="error"} [1h]
```

### Time Range Selection

**Performance Impact**:
- Last 5 minutes: Very fast
- Last 1 hour: Fast
- Last 6 hours: Moderate
- Last 24 hours: Slow
- Last 7 days: Very slow

**Best Practice**: Always specify the narrowest time range that covers your investigation period.

### Recording Rules

For complex queries used frequently, consider Prometheus recording rules:

```yaml
# Example: Count errors per service per minute
- record: huleedu:log_errors:rate1m
  expr: sum by (service) (rate({container=~"huleedu_.*"} |= "ERROR" [1m]))
```

---

## Integration with Grafana

### Troubleshooting Dashboard

**Location**: `/observability/grafana/dashboards/HuleEdu_Troubleshooting.json`

**Key Panels**:
1. **Correlation ID Search**: Variable input for correlation ID
2. **Chronological Timeline**: All logs sorted by timestamp
3. **Service Involvement**: Which services handled the request
4. **Error Aggregation**: Errors grouped by service

**Query Pattern**:
```logql
{container=~"huleedu_${service}"} |= "${correlation_id}" |= "${log_filter}"
```

### Service Deep Dive Dashboard

**Location**: `/observability/grafana/dashboards/HuleEdu_Service_Deep_Dive_Template.json`

**Live Logs Panel**:
```logql
{container=~"huleedu_${service}"} |= "${log_filter}"
```

**Variables**:
- `$service` - Service dropdown
- `$log_filter` - Text filter input

### Loki API Queries

**Direct API Access**:
```bash
# Query logs
curl "http://localhost:3100/loki/api/v1/query_range?query={container=\"huleedu_content_service\"}&limit=100"

# Get available labels
curl http://localhost:3100/loki/api/v1/labels

# Get label values
curl http://localhost:3100/loki/api/v1/label/container/values
```

---

## Context7 Integration

### When to Use Context7

Fetch latest Loki/LogQL documentation when:
- User asks about LogQL syntax not covered in this reference
- Need examples of advanced LogQL features (aggregations, metrics queries)
- Troubleshooting Promtail configuration issues
- Understanding Loki storage or retention settings
- New LogQL features or syntax changes

### Example Context7 Usage

```python
# Fetch Loki documentation
from context7 import get_library_docs

loki_docs = get_library_docs(
    library_id="/grafana/loki",
    topic="logql query syntax"
)

# Fetch Promtail configuration docs
promtail_docs = get_library_docs(
    library_id="/grafana/loki",
    topic="promtail configuration"
)
```

**Library IDs**:
- Loki: `/grafana/loki`
- LogQL: Part of Loki docs, use topic filtering

---

## Best Practices

### 1. Start Broad, Then Narrow

```logql
# Step 1: All logs for correlation ID
{container=~"huleedu_.*"} |= "correlation_id_value"

# Step 2: Only errors
{container=~"huleedu_.*"} |= "correlation_id_value" |= "ERROR"

# Step 3: Specific service errors
{container="huleedu_batch_orchestrator_service"} |= "correlation_id_value" |= "ERROR"
```

### 2. Use Promoted Labels First

```logql
# Fast: Uses promoted label index
{level="error"}

# Slower: Requires JSON parsing
{container=~"huleedu_.*"} | json | level="error"
```

### 3. Combine Line Filters Before Parsing

```logql
# Efficient: Filter before parsing
{container=~"huleedu_.*"} |= "ERROR" | json | correlation_id!=""

# Inefficient: Parse all logs first
{container=~"huleedu_.*"} | json | level="error"
```

### 4. Limit Results

```logql
# Add limit to prevent overwhelming results
{container=~"huleedu_.*"} |= "ERROR" | limit 100
```

### 5. Use Appropriate Time Ranges

- **Real-time debugging**: Last 15-30 minutes
- **Recent issue investigation**: Last 1-6 hours
- **Historical analysis**: Last 24 hours (but expect slower queries)
- **Trend analysis**: Use Prometheus metrics instead

### 6. Never Use --since for Correlation IDs

Per user's CLAUDE.md:
```bash
# WRONG: Using --since argument
docker logs huleedu_content_service --since 1h | grep "correlation_id"

# CORRECT: Use Loki query
{container="huleedu_content_service"} |= "correlation_id_value"
```

---

## Troubleshooting Common Issues

### No Results Returned

**Check**:
1. Container name matches: `{container=~"huleedu_.*"}`
2. Time range includes the event
3. Line filter is case-sensitive: use `|~` for case-insensitive
4. JSON parsing syntax: `| json` before label filters

### Slow Queries

**Solutions**:
1. Narrow time range
2. Use exact container match instead of regex
3. Add line filters before JSON parsing
4. Use promoted labels when possible

### Missing Labels

**Verify**:
1. Promtail is running: `docker compose -f observability/docker-compose.observability.yml ps`
2. Promtail has access to Docker socket
3. Container is on correct network
4. Labels are promoted in Promtail config

---

## Related Resources

- **examples.md**: Real-world debugging scenarios from HuleEdu
- **SKILL.md**: Quick reference and activation criteria
- `/observability/LOGQL_SYNTAX_FIX.md`: LogQL syntax corrections and patterns
- `/observability/promtail/promtail-config.yml`: Promtail configuration
- `.claude/rules/071.4-loki-log-querying-patterns.md`: Observability rule for Loki
