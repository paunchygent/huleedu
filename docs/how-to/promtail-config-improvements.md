# Promtail Configuration: Current Working Solution (2025-11-19)

## Overview

The Promtail pipeline configuration has been optimized for HuleEdu's structlog JSON logs while maintaining compatibility with non-JSON log lines (Quart/Hypercorn output).

### Key Design Decisions

1. **No `output` stage**: Preserves original log lines instead of replacing with extracted fields
2. **Low-cardinality labels**: Only `service` and `level` promoted to labels (25 streams total)
3. **High-cardinality JSON fields**: `correlation_id`, `logger_name`, `event` remain in JSON body, queryable with `| json`
4. **Graceful non-JSON handling**: Console and Hypercorn logs pass through unchanged

### Current Working Configuration

```yaml
pipeline_stages:
  # Stage 1: Parse JSON (extracts fields but preserves original line content)
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

  # Stage 2: Parse timestamp from JSON when available
  - timestamp:
      source: timestamp
      format: RFC3339
      fallback_formats:
        - RFC3339Nano
        - "2006-01-02T15:04:05.000Z"

  # Stage 3: Promote ONLY low-cardinality fields to labels
  - labels:
      level:
      service:
```

## Why This Configuration Works

### ❌ What Doesn't Work: Using `output` Stage
The `output` stage attempts to replace log line content with a specific field:
```yaml
- output:
    source: event  # ❌ FAILS for non-JSON lines
```

**Problem**: When non-JSON lines (Quart startup, Hypercorn output) hit this stage, the `event` field doesn't exist, causing "context canceled" errors and blocking ALL log ingestion.

### ✅ What Works: Preserving Original Lines
Extract JSON fields WITHOUT replacing the log line content:
```yaml
- json:
    expressions:
      event: event
      correlation_id: correlation_id
      # ... other fields
```

**Result**:
- JSON logs appear in Loki as: `{"logger_name": "content.app", "event": "...", ...}`
- Non-JSON logs appear unchanged: `[2025-11-19 19:35:04 +0000] [68] [INFO] Running...`
- All fields are queryable with `| json` filter

## Query Patterns

### Basic Log Retrieval
```logql
{service="content_service"}
{service="batch_orchestrator_service"}
{level="error"}
```

### JSON Field Filtering
```logql
# Filter by correlation_id (for request tracing)
{service="content_service"} | json | correlation_id="<uuid>"

# Filter by event message
{service="content_service"} | json | event="Content Service startup completed successfully"

# Filter by logger name
{service="content_service"} | json | logger_name="content.app"

# Cross-service correlation tracing
{service=~".*"} | json | correlation_id="<uuid>"
```

### Error Investigation
```logql
# All errors with JSON fields
{level="error"} | json

# Errors with correlation context
{level="error"} | json | correlation_id!=""

# Service-specific errors
{service="batch_orchestrator_service", level="error"} | json
```

## Performance & Cardinality

### Label Strategy (Current: 25 Streams)
**Promoted to labels** (indexed, fast queries):
- `service` (~15-20 values)
- `level` (5 values: debug, info, warning, error, critical)

**Kept in JSON body** (queryable with `| json`):
- `correlation_id` (UUID per request - unbounded)
- `logger_name` (~50-100 Python loggers)
- `event` (log message content - unbounded)
- `event_id`, `event_type`, `source_service`, etc.

**Why**: Fields with >100 unique values/day stay in JSON body to prevent Loki index explosion.

## Validation Results

1. ✅ **Zero pipeline errors**: No "could not transfer logs" failures
2. ✅ **JSON logs visible**: Full structure preserved in Loki
3. ✅ **Fields extractable**: `| json` accesses all fields
4. ✅ **Filtering works**: Correlation ID and event queries return results
5. ✅ **Low cardinality**: 25 streams (optimal performance)

## Configuration Location

**File**: `observability/promtail/promtail-config.yml`

After changes:
```bash
docker restart huleedu_promtail
```

## Important Notes

1. **Original log lines preserved**: JSON logs show full JSON structure, not just the `event` field
2. **Backwards compatible**: Works with both JSON (structlog) and non-JSON (Quart/Hypercorn) logs
3. **Cardinality optimized**: Only low-cardinality fields promoted to labels
4. **Query performance**: Use `| json` filter for high-cardinality field queries
