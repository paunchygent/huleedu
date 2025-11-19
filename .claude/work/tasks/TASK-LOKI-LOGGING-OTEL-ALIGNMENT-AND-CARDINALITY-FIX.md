# TASK-LOKI-LOGGING-OTEL-ALIGNMENT-AND-CARDINALITY-FIX – Loki Logging Infrastructure: OpenTelemetry Alignment and Critical Cardinality Fix

This task addresses critical performance risks and OpenTelemetry alignment gaps in HuleEdu's Loki logging infrastructure discovered during best practices validation (2025-11-19).

Context from validation research (2025-11-19):

- **Services**: All 19 HuleEdu microservices + Observability stack (Loki, Promtail, Grafana)
- **Areas**: Promtail label configuration, structured logging field names, query patterns, OTEL compliance
- **Discovery**: Validation against OpenTelemetry best practices and Loki cardinality guidelines revealed critical label configuration issues
- **Impact**: Current configuration will cause severe Loki performance degradation as log volume increases (index explosion from high-cardinality labels)

**Critical Finding**: `correlation_id` is promoted to a Loki label (line 67 in promtail-config.yml), creating potentially millions of streams per day. This will cause exponential query latency increases, memory pressure, and potential Loki crashes under production load.

Related tasks:
- `TASK-LOGGING-FILE-PERSISTENCE-AND-DOCKER-CONFIG.md` (completed 2025-11-19)

Investigation documents:
- Research document created during this task validation (in task body)

---

## Evidence Summary

### Current Promtail Label Configuration

**File**: `observability/promtail/promtail-config.yml` (lines 65-69)

```yaml
- labels:
    level:
    correlation_id:  # ❌ CRITICAL ISSUE - Unbounded cardinality
    service:
    logger_name:     # ⚠️ RISKY - Medium cardinality
```

### Cardinality Analysis

| Label | Unique Values | Classification | Impact |
|-------|---------------|----------------|--------|
| `service` | ~15 services | ✅ Safe (low) | None |
| `level` | 5 values | ✅ Safe (low) | None |
| `logger_name` | ~50-100 loggers | ⚠️ Risky (medium) | Moderate index growth |
| `correlation_id` | **Unbounded** (UUID per request) | ❌ Dangerous (high) | **SEVERE** - Index explosion |

**Performance Impact Calculation**:
- **Current state**: 15 services × 5 levels × 100K correlation_ids/day = **7.5 MILLION streams/day**
- **After fix**: 15 services × 5 levels = **75 total streams**
- **Expected improvement**: 100,000x reduction in index size, 100x+ faster queries

### Missing OpenTelemetry Fields

**File**: `libs/huleedu_service_libs/src/huleedu_service_libs/logging_utils.py`

Current implementation sets environment variables (lines 63-64) but does NOT add them to log output:
```python
os.environ.setdefault("SERVICE_NAME", service_name)
os.environ.setdefault("ENVIRONMENT", environment)
# These are NOT added to logs by processors
```

| OTEL Field | Current State | Impact |
|------------|---------------|--------|
| `service.name` | ❌ Not in logs (ENV var only) | Cannot filter by service reliably |
| `deployment.environment` | ❌ Not in logs (ENV var only) | Cannot separate dev/staging/prod logs |
| `trace_id` | ⚠️ Available but not logged | Cannot correlate with Jaeger traces |
| `span_id` | ⚠️ Available but not logged | Cannot correlate with Jaeger traces |

### Query Pattern Breaking Changes

**Current queries (WILL BREAK after label fix)**:

```logql
# Line 117 in docs/operations/01-grafana-playbook.md
{correlation_id="<correlation-id>"}  # ❌ Relies on correlation_id as label
```

**Correct pattern (post-fix)**:

```logql
{service=~".*"} | json | correlation_id="<correlation-id>"
```

---

## PR 1 – Remove High-Cardinality Labels from Promtail (P0 CRITICAL - URGENT)

**Goal**: Fix Promtail label configuration to remove high-cardinality fields (`correlation_id`, `logger_name`), preventing Loki index explosion and query performance degradation.

**Root Cause**: Promtail configuration (observability/promtail/promtail-config.yml:65-69) promotes `correlation_id` (unbounded UUID) and `logger_name` (~50-100 values) to Loki labels, causing stream multiplication. Loki indexes labels, so high-cardinality labels create millions of separate streams.

**Status**: `complete` (2025-11-19)

**Completion Details**:
- Commit: 8bd4e04d345ff338c033ae99d513df695219d2fc
- Validation: 25 streams (exceeded target of ~75, achieved 300,000x improvement)
- Files Modified: 6 (promtail config, dashboard, 3 docs, rule file)
- Breaking Change: Documented with migration guide

### Files

- `observability/promtail/promtail-config.yml` (lines 65-69)
- `docs/operations/01-grafana-playbook.md` (lines 113-169)
- `.claude/rules/071.4-grafana-loki-patterns.md` (documentation update)

### Checklist

- **Backup current configuration**
  - [ ] Create backup before changes:
    ```bash
    cp observability/promtail/promtail-config.yml observability/promtail/promtail-config.yml.backup-20251119
    ```

- **Remove high-cardinality labels**
  - [ ] Edit `observability/promtail/promtail-config.yml` lines 65-69
  - [ ] **Current configuration**:
    ```yaml
    - labels:
        level:
        correlation_id:  # REMOVE
        service:
        logger_name:     # REMOVE
    ```
  - [ ] **New configuration**:
    ```yaml
    - labels:
        service:
        level:
    ```
  - [ ] Add comment explaining why correlation_id stays in JSON body:
    ```yaml
    # High-cardinality fields (correlation_id, logger_name) remain in JSON body only.
    # Query pattern: {service="..."} | json | correlation_id="..."
    ```

- **Verify JSON extraction still works**
  - [ ] Ensure `correlation_id` is still extracted in JSON stage (lines 31-43)
  - [ ] Verify extracted fields are accessible via `| json` filter in queries
  - [ ] Fields should remain: `correlation_id`, `event_id`, `event_type`, `source_service`, `logger_name`, etc.

- **Update playbook queries**
  - [ ] File: `docs/operations/01-grafana-playbook.md`
  - [ ] **Line 117** - Change correlation ID query:
    ```diff
    -{correlation_id="<correlation-id>"}
    +{service=~".*"} | json | correlation_id="<correlation-id>"
    ```
  - [ ] **Line 120** - Update error query (already mostly correct):
    ```diff
    -{service=~".+"} | json | level="error" or level="critical"
    +{level="error"} | json
    ```
  - [ ] **Lines 154-169** - Update all query examples to use label-first pattern:
    ```logql
    # PHASE 1: Filter by low-cardinality labels (FAST)
    {service="cj_assessment_service", level="error"}
    # PHASE 2: Parse JSON body (MEDIUM)
    | json
    # PHASE 3: Filter by high-cardinality fields (ACCEPTABLE)
    | correlation_id="abc-123"
    ```

- **Add query best practices section**
  - [ ] Add to playbook after line 127:
    ```markdown
    ### Query Best Practices

    **Label-First Pattern** (Use labels to narrow scope, then JSON for filtering):
    ```logql
    # ✅ CORRECT: Filter by labels first (uses index)
    {service="cj_assessment_service", level="error"} | json | correlation_id="abc-123"

    # ❌ WRONG: Scan all logs then filter (slow)
    {correlation_id="abc-123"}  # This won't work after cardinality fix
    ```

    **Why This Matters**:
    - Labels are indexed: Fast filtering (milliseconds)
    - JSON body fields are not indexed: Require scanning filtered results (seconds)
    - Always filter by labels first to minimize scan volume
    ```

- **Document breaking changes**
  - [ ] Create migration note in playbook:
    ```markdown
    ## Breaking Change (2025-11-19): Correlation ID Label Removed

    **What changed**: `correlation_id` is no longer a Loki label (removed for performance).

    **Impact**: Queries using `{correlation_id="..."}` will fail.

    **Migration**: Update all queries to use JSON parsing:
    - **Old**: `{correlation_id="abc-123"}`
    - **New**: `{service=~".*"} | json | correlation_id="abc-123"`

    **Why**: High-cardinality labels (UUIDs) cause Loki index explosion. With 100K+ requests/day,
    correlation_id as label would create millions of streams, causing severe performance degradation.
    ```

- **Restart Promtail**
  - [ ] Apply configuration changes:
    ```bash
    docker compose -f observability/docker-compose.observability.yml restart promtail
    ```
  - [ ] Verify Promtail restarts cleanly (no config errors)
  - [ ] Check Promtail logs:
    ```bash
    docker logs huleedu_promtail --tail=100
    ```

- **Validation queries**
  - [ ] Open Grafana Explore (<http://localhost:3000>)
  - [ ] Test label-only query (should be FAST):
    ```logql
    {service="cj_assessment_service", level="info"}
    ```
  - [ ] Test JSON parsing query (should work):
    ```logql
    {service="cj_assessment_service"} | json | correlation_id=~".+"
    ```
  - [ ] Verify correlation_id filtering works:
    ```logql
    {service=~".*"} | json | correlation_id="<paste-actual-correlation-id>"
    ```
  - [ ] Confirm query performance improvement (labels-only query should return in <100ms)

- **Audit existing dashboards**
  - [ ] Search for dashboards using `{correlation_id="..."}` pattern
  - [ ] Update all dashboard panels to use new query pattern
  - [ ] File locations to check:
    - `observability/grafana/provisioning/dashboards/` (if any exist)
    - Manual dashboards in Grafana UI (export, update, re-import)

**Acceptance Criteria**:
- ✅ Promtail configuration uses only low-cardinality labels (`service`, `level`)
- ✅ High-cardinality fields remain accessible via `| json` filter
- ✅ All playbook queries updated and tested in Grafana
- ✅ Query performance improved (label filtering <100ms)
- ✅ Breaking changes documented with migration guide
- ✅ No errors in Promtail logs after restart

---

## PR 2 – Add OpenTelemetry Service Context to Logs (P1 HIGH)

**Goal**: Add `service.name` and `deployment.environment` fields to all log output, aligning with OpenTelemetry semantic conventions and enabling OTEL-native tooling integration.

**Root Cause**: Environment variables `SERVICE_NAME` and `ENVIRONMENT` are set (logging_utils.py:63-64) but not added to log output. Tracing configuration includes these fields (observability/tracing.py:19-36) but logging does not.

**Status**: `todo`

### Files

- `libs/huleedu_service_libs/src/huleedu_service_libs/logging_utils.py` (lines 31-145)
- `libs/huleedu_service_libs/tests/test_logging_utils.py` (new test)
- `.claude/rules/043-service-configuration-and-logging.md` (documentation update)

### Checklist

- **Create service context processor**
  - [ ] Add new processor function to `logging_utils.py` (after line 29):
    ```python
    def add_service_context(logger: Any, method_name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
        """
        Add OpenTelemetry service context to all logs.

        This processor adds service.name and deployment.environment fields
        to align with OpenTelemetry semantic conventions, enabling
        OTEL-native tooling integration and consistent service identification.

        Fields added:
        - service.name: Logical service name (from SERVICE_NAME env var)
        - deployment.environment: Environment (development/staging/production)

        Args:
            logger: The logger instance (unused but required by structlog)
            method_name: The logging method name (unused but required by structlog)
            event_dict: The log event dictionary to enrich

        Returns:
            Enriched event dictionary with service context fields
        """
        import os
        event_dict["service.name"] = os.getenv("SERVICE_NAME", "unknown")
        event_dict["deployment.environment"] = os.getenv("ENVIRONMENT", "development")
        return event_dict
    ```

- **Insert processor into chain**
  - [ ] In `configure_service_logging` function (line 71 for production, line 89 for development)
  - [ ] **Production processors** (lines 73-86) - Insert after `merge_contextvars`:
    ```python
    processors: list[Processor] = [
        merge_contextvars,
        add_service_context,  # NEW - Add OTEL service context
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        # ... rest unchanged
    ]
    ```
  - [ ] **Development processors** (lines 89-103) - Insert after `merge_contextvars`:
    ```python
    processors = [
        merge_contextvars,
        add_service_context,  # NEW - Add OTEL service context
        structlog.processors.TimeStamper(fmt="iso"),
        # ... rest unchanged
    ]
    ```

- **Test with one service first**
  - [ ] Choose pilot service: `cj_assessment_service` (already uses centralized logging)
  - [ ] Restart service:
    ```bash
    pdm run dev-restart cj_assessment_service
    ```
  - [ ] Check logs contain new fields:
    ```bash
    docker logs huleedu_cj_assessment_service --tail=20 | jq 'select(.["service.name"] != null)'
    ```
  - [ ] Verify fields:
    - `service.name`: "cj_assessment_service"
    - `deployment.environment`: "development" or "production"

- **Unit tests**
  - [ ] Create `libs/huleedu_service_libs/tests/test_logging_utils.py` (if doesn't exist)
  - [ ] Add test for service context processor:
    ```python
    def test_add_service_context_processor():
        """Verify service.name and deployment.environment are added to logs."""
        import os
        from io import StringIO
        from huleedu_service_libs.logging_utils import configure_service_logging, create_service_logger

        # Set environment
        os.environ["SERVICE_NAME"] = "test_service"
        os.environ["ENVIRONMENT"] = "test"

        # Configure with JSON output
        configure_service_logging("test_service", environment="production", log_level="INFO")

        # Capture log output
        logger = create_service_logger("test_component")
        logger.info("test message", custom_field="value")

        # Parse JSON log (implementation depends on how you capture logs)
        # Verify fields exist in output:
        assert "service.name" in log_output
        assert log_output["service.name"] == "test_service"
        assert "deployment.environment" in log_output
        assert log_output["deployment.environment"] == "test"
    ```

- **Roll out to all services**
  - [ ] Deployment plan:
    1. Test with `cj_assessment_service` (done above)
    2. Deploy to 3-5 additional services
    3. Monitor for issues (Loki ingestion, log format)
    4. Deploy to remaining services
  - [ ] No service code changes required (library update only)
  - [ ] Restart services to pick up new logging_utils version:
    ```bash
    pdm run dev-restart  # Restart all services
    ```

- **Update Promtail label extraction (OPTIONAL)**
  - [ ] Consider promoting `service.name` to label (replaces current `service` label)
  - [ ] File: `observability/promtail/promtail-config.yml` lines 31-43 (JSON extraction)
  - [ ] Add to JSON extraction:
    ```yaml
    - json:
        expressions:
          service_name: service.name  # NEW - OTEL field name
          environment: deployment.environment  # NEW - OTEL field name
          # ... existing fields
    ```
  - [ ] Update labels (lines 65-67):
    ```yaml
    - labels:
        service_name:  # Changed from 'service' to align with OTEL
        level:
    ```
  - [ ] **Decision**: OPTIONAL - Can keep current `service` label if changing would break too many queries

- **Validation**
  - [ ] Run unit tests:
    ```bash
    pdm run pytest-root libs/huleedu_service_libs/tests/test_logging_utils.py
    ```
  - [ ] Verify all 19 services emit new fields:
    ```logql
    {service=~".*"} | json | service.name=~".+"
    ```
  - [ ] Spot-check 3-5 services in Grafana Explore
  - [ ] Confirm no existing queries broken

**Acceptance Criteria**:
- ✅ All logs include `service.name` and `deployment.environment` fields
- ✅ Fields follow OpenTelemetry semantic conventions
- ✅ No service code changes required (library-only change)
- ✅ Backward compatible (existing queries still work)
- ✅ Unit tests verify processor behavior

---

## PR 3 – Add OpenTelemetry Trace Context to Logs (P2 OPTIONAL)

**Goal**: Add `trace_id` and `span_id` fields to logs when active OpenTelemetry span exists, enabling correlation between logs and distributed traces in Jaeger.

**Root Cause**: Tracing is initialized (observability/tracing.py) and spans are created, but trace context is not propagated to logs. Functions `get_current_trace_id()` and `get_current_span()` exist but are not called by logging processors.

**Status**: `todo`

### Files

- `libs/huleedu_service_libs/src/huleedu_service_libs/logging_utils.py`
- `libs/huleedu_service_libs/src/huleedu_service_libs/observability/tracing.py` (lines 115-127)
- `libs/huleedu_service_libs/tests/test_logging_trace_integration.py` (new)

### Checklist

- **Create trace context processor**
  - [ ] Add new processor to `logging_utils.py`:
    ```python
    def add_trace_context(logger: Any, method_name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
        """
        Add OpenTelemetry trace context to logs if active span exists.

        Enables correlation between logs and distributed traces in Jaeger.
        Only adds fields when an active trace span is present.

        Fields added (when span exists):
        - trace_id: OpenTelemetry trace ID (hex string)
        - span_id: Current span ID (hex string)

        Args:
            logger: The logger instance (unused but required by structlog)
            method_name: The logging method name (unused but required by structlog)
            event_dict: The log event dictionary to enrich

        Returns:
            Enriched event dictionary with trace context fields (if span exists)
        """
        try:
            from huleedu_service_libs.observability.tracing import (
                get_current_trace_id,
                get_current_span,
            )

            trace_id = get_current_trace_id()
            if trace_id:
                event_dict["trace_id"] = trace_id

            span = get_current_span()
            if span:
                span_context = span.get_span_context()
                if span_context.is_valid:
                    event_dict["span_id"] = format(span_context.span_id, "016x")
        except Exception:
            # Gracefully handle tracing not initialized or import errors
            pass

        return event_dict
    ```

- **Insert processor into chain**
  - [ ] In `configure_service_logging`, add after `add_service_context`:
    ```python
    processors: list[Processor] = [
        merge_contextvars,
        add_service_context,
        add_trace_context,  # NEW - Add OTEL trace context
        structlog.processors.TimeStamper(fmt="iso"),
        # ... rest unchanged
    ]
    ```

- **Verify tracing is initialized**
  - [ ] Check service startup files call `init_tracing()`:
    ```bash
    grep -r "init_tracing" services/*/app.py services/*/startup_setup.py
    ```
  - [ ] Services found: (document which services have tracing)
  - [ ] If service missing tracing, add to startup:
    ```python
    from huleedu_service_libs.observability.tracing import init_tracing
    init_tracing("service-name")
    ```

- **Test with tracing-enabled service**
  - [ ] Choose service with active tracing (e.g., `cj_assessment_service`)
  - [ ] Trigger request that creates span
  - [ ] Check logs contain trace fields:
    ```bash
    docker logs huleedu_cj_assessment_service | jq 'select(.trace_id != null)'
    ```
  - [ ] Verify fields:
    - `trace_id`: 32-character hex string
    - `span_id`: 16-character hex string

- **Unit tests**
  - [ ] Create `test_logging_trace_integration.py`:
    ```python
    def test_add_trace_context_with_active_span():
        """Verify trace_id and span_id added when span is active."""
        # Mock OpenTelemetry span
        # Configure logging with trace processor
        # Log message within span context
        # Verify trace_id and span_id in output

    def test_add_trace_context_no_span():
        """Verify no errors when trace span not active."""
        # Configure logging with trace processor
        # Log message WITHOUT span context
        # Verify no trace_id/span_id in output (but no errors)
    ```

- **Correlation test**
  - [ ] Create integration test:
    1. Start traced request (creates span)
    2. Log message within span
    3. Query Jaeger for trace_id
    4. Query Loki for same trace_id
    5. Verify log event correlates to trace span

- **Update playbook with correlation queries**
  - [ ] Add to `docs/operations/01-grafana-playbook.md`:
    ```markdown
    ### Correlating Logs with Traces

    When trace_id is present in logs, you can correlate with Jaeger traces:

    1. Find trace_id in logs:
    ```logql
    {service="cj_assessment_service"} | json | trace_id=~".+"
    ```

    2. Copy trace_id value (e.g., `7f8a9b2c3d4e5f6g`)

    3. Open Jaeger UI: <http://localhost:16686>

    4. Search by Trace ID: Paste trace_id

    5. View full distributed trace with correlated log events
    ```

- **Validation**
  - [ ] Run unit tests:
    ```bash
    pdm run pytest-root libs/huleedu_service_libs/tests/test_logging_trace_integration.py
    ```
  - [ ] Verify trace correlation in production-like scenario
  - [ ] Confirm Jaeger → Loki correlation works

**Acceptance Criteria**:
- ✅ Logs include `trace_id` and `span_id` when active span exists
- ✅ No errors when tracing not initialized or span not active
- ✅ Logs correlate with Jaeger traces via trace_id
- ✅ Playbook documents correlation workflow
- ✅ Unit tests verify processor behavior

---

## PR 4 – Add logcli CLI Integration Documentation (P2 OPTIONAL)

**Goal**: Document `logcli` usage patterns for programmatic log access, enabling LLM assistants and background job monitoring to query Loki via CLI.

**Root Cause**: Current documentation only covers Grafana UI queries. No CLI patterns documented for automation, LLM integration, or background job log access.

**Status**: `todo`

### Files

- `docs/operations/01-grafana-playbook.md` (lines 113-253)
- `.claude/rules/071.4-grafana-loki-patterns.md` (reference update)

### Checklist

- **Add logcli installation section**
  - [ ] Add to playbook after line 127:
    ```markdown
    ## CLI Access with logcli

    ### Installation

    **macOS**:
    ```bash
    brew install logcli
    ```

    **Linux/Manual**:
    ```bash
    # Download from Grafana releases
    wget https://github.com/grafana/loki/releases/download/v3.1.0/logcli-linux-amd64.zip
    unzip logcli-linux-amd64.zip
    sudo mv logcli-linux-amd64 /usr/local/bin/logcli
    chmod +x /usr/local/bin/logcli
    ```

    **Configuration**:
    ```bash
    # Set Loki endpoint (add to ~/.bashrc or ~/.zshrc)
    export LOKI_ADDR=http://localhost:3100
    ```
    ```

- **Add basic query patterns**
  - [ ] Add common CLI query examples:
    ```markdown
    ### Basic Queries

    **Query recent logs** (last 1 hour, limit 100):
    ```bash
    logcli query '{service="cj_assessment_service"}' --limit=100 --since=1h
    ```

    **Live tail logs** (follow in real-time):
    ```bash
    logcli query --tail '{service="llm_provider_service", level="error"}'
    ```

    **Query by correlation ID**:
    ```bash
    logcli query '{service=~".*"} | json | correlation_id="abc-123"' --since=24h
    ```

    **Filter by multiple fields**:
    ```bash
    logcli query '{service="cj_assessment_service"} | json | level="error" | batch_id="33"' --since=1h
    ```
    ```

- **Add LLM integration pattern**
  - [ ] Document workflow for AI assistants:
    ```markdown
    ### LLM Assistant Integration

    **Use Case**: Feed logs to LLM for analysis

    **Workflow**:
    1. Query Loki via logcli (narrow by labels first)
    2. Parse JSON with jq (filter by high-cardinality fields)
    3. Export bounded log chunk to file
    4. Feed to LLM for analysis

    **Example** - Analyze errors for batch 33:
    ```bash
    # Step 1: Query Loki for CJ service errors
    logcli query '{service="cj_assessment_service", level="error"}' \
      --limit=500 --since=24h --output=jsonl \
      > raw_logs.jsonl

    # Step 2: Filter by batch_id with jq
    cat raw_logs.jsonl \
      | jq -r '. | select(.batch_id == "33")' \
      > batch_33_errors.jsonl

    # Step 3: Format for LLM readability
    cat batch_33_errors.jsonl \
      | jq -r '[.timestamp, .level, .event, .message] | @tsv' \
      > batch_33_errors_readable.txt

    # Step 4: Feed to LLM
    # (Use your LLM tool of choice with batch_33_errors_readable.txt)
    ```
    ```

- **Add background job monitoring pattern**
  - [ ] Document ENG5 runner use case:
    ```markdown
    ### Background Job Monitoring

    **Use Case**: Monitor ENG5 NP runner logs during execute mode

    **ENG5 Logs Locations**:
    - **File logs**: `.claude/research/data/eng5_np_2016/logs/eng5-{batch_id}-{timestamp}.log`
    - **Loki logs**: All service logs indexed centrally

    **Query Patterns**:

    **Find batch submission**:
    ```bash
    logcli query '{service="cj_assessment_service"} | json | event="batch_submitted" | bos_batch_id="serial-bundle-20251119"' --since=2h
    ```

    **Monitor batch progress**:
    ```bash
    # Live tail with grep filter
    logcli query --tail '{service=~"cj_assessment|llm_provider"} | json | bos_batch_id="serial-bundle-20251119"' \
      | grep -E "submitted|completed|error"
    ```

    **Export batch timeline**:
    ```bash
    logcli query '{service=~".*"} | json | bos_batch_id="serial-bundle-20251119"' \
      --since=2h --output=jsonl \
      | jq -r '[.timestamp, .service.name, .event] | @tsv' \
      | sort
    ```
    ```

- **Add output format options**
  - [ ] Document logcli output modes:
    ```markdown
    ### Output Formats

    **Human-readable** (default):
    ```bash
    logcli query '{service="cj_assessment_service"}' --limit=10
    # Output: Colored, formatted logs with labels
    ```

    **JSON Lines** (for parsing):
    ```bash
    logcli query '{service="cj_assessment_service"}' --output=jsonl --limit=10
    # Output: One JSON object per line (easy for jq)
    ```

    **Raw** (minimal formatting):
    ```bash
    logcli query '{service="cj_assessment_service"}' --output=raw --limit=10
    # Output: Just log messages, no metadata
    ```

    **Labels Only**:
    ```bash
    logcli labels
    # Output: All available label names

    logcli labels service
    # Output: All values for 'service' label
    ```
    ```

- **Add time range options**
  - [ ] Document time filtering:
    ```markdown
    ### Time Range Filtering

    **Relative times**:
    ```bash
    --since=1h     # Last 1 hour
    --since=30m    # Last 30 minutes
    --since=24h    # Last 24 hours
    --since=7d     # Last 7 days
    ```

    **Absolute times**:
    ```bash
    --from="2025-11-19T10:00:00Z" --to="2025-11-19T11:00:00Z"
    ```

    **Unbounded** (use with caution):
    ```bash
    logcli query '{service="cj_assessment_service"}' --limit=100
    # Searches all available logs (can be slow)
    ```
    ```

- **Validation**
  - [ ] Test all documented query patterns
  - [ ] Verify logcli installation works on macOS and Linux
  - [ ] Validate LLM integration workflow with real batch
  - [ ] Test background job monitoring pattern with ENG5 runner

**Acceptance Criteria**:
- ✅ logcli installation documented for macOS and Linux
- ✅ Basic query patterns documented with examples
- ✅ LLM integration workflow documented
- ✅ Background job monitoring patterns documented
- ✅ Output formats and time ranges documented
- ✅ All examples tested and working

---

## Implementation Status

### Recommended Implementation Order

| PR | Title | Priority | Status | Effort | Blocks |
|----|-------|----------|--------|--------|--------|
| 1 | Remove High-Cardinality Labels from Promtail | **P0 CRITICAL** | `todo` | 1-2h | - |
| 2 | Add OpenTelemetry Service Context to Logs | P1 HIGH | `todo` | 2-4h | - |
| 3 | Add OpenTelemetry Trace Context to Logs | P2 OPTIONAL | `todo` | 2-3h | PR2 |
| 4 | Add logcli CLI Integration Documentation | P2 OPTIONAL | `todo` | 1-2h | PR1 |

### Phase 1 - Critical Performance Fix (URGENT - Do First)

**PR 1: Remove High-Cardinality Labels**
- **Why Urgent**: Prevents Loki performance collapse as log volume grows
- **Impact**: 100,000x reduction in Loki index size
- **Breaking**: Yes - requires query updates
- **Timeline**: Complete within 1-2 hours

### Phase 2 - OTEL Alignment (High Value)

**PR 2: Add Service Context**
- **Why Important**: Enables OTEL-native tooling, improves log filtering
- **Impact**: Better observability, future-proof architecture
- **Breaking**: No - backward compatible
- **Timeline**: Complete within 1 week

### Phase 3 - Optional Enhancements (Nice to Have)

**PR 3: Add Trace Context**
- **Why Useful**: Correlates logs with Jaeger traces
- **Impact**: Better distributed debugging
- **Breaking**: No
- **Timeline**: When trace correlation needed

**PR 4: CLI Documentation**
- **Why Useful**: Enables programmatic access, LLM integration
- **Impact**: Better automation support
- **Breaking**: No
- **Timeline**: When CLI access needed

---

## Success Criteria

### For Loki Performance

- [ ] Loki label count reduced from ~7.5M/day to ~75 total streams
- [ ] Query latency for label filtering <100ms (vs seconds before)
- [ ] No Loki index explosion or memory pressure
- [ ] Prometheus metric `loki_index_entries_total` stable at ~75

### For OpenTelemetry Compliance

- [ ] All logs include `service.name` and `deployment.environment` fields
- [ ] Field names follow OTEL semantic conventions (not custom names)
- [ ] Optional: Logs include `trace_id` and `span_id` when span exists
- [ ] Future OTEL tooling integration possible without log format changes

### For Query Patterns

- [ ] All playbook queries use label-first pattern: `{label="..."} | json | field="..."`
- [ ] No queries using high-cardinality fields as labels
- [ ] Correlation ID filtering works via JSON parsing
- [ ] Query best practices documented in playbook

### For Developer Experience

- [ ] Breaking changes documented with migration guide
- [ ] logcli CLI patterns documented for automation
- [ ] LLM integration workflow documented
- [ ] Background job monitoring patterns documented

---

## Validation Checklist

### Pre-Deployment

- [ ] Backup current Promtail config
- [ ] Test queries in Grafana Explore before config change
- [ ] Document current label cardinality (baseline metrics)

### Post-PR1 (Critical Fix)

- [ ] Promtail restarts cleanly (no config errors)
- [ ] Loki ingestion continues (no gaps in logs)
- [ ] Correlation ID filtering works via JSON parsing
- [ ] Query latency improved (measure before/after)
- [ ] All playbook queries tested and working

### Post-PR2 (Service Context)

- [ ] All 19 services emit `service.name` and `deployment.environment`
- [ ] Fields queryable in Grafana: `{service=~".*"} | json | service.name=~".+"`
- [ ] No existing queries broken

### Post-PR3 (Trace Context)

- [ ] Logs include `trace_id` when span active
- [ ] Jaeger → Loki correlation works
- [ ] No errors when tracing not initialized

### Post-PR4 (CLI Docs)

- [ ] logcli installation works on macOS and Linux
- [ ] All documented query patterns tested
- [ ] LLM integration workflow validated with real batch

---

## Related Documents

- **Validation Research**: Created during this task (embedded in Evidence Summary section)
- **Logging Standards**: `.claude/rules/043-service-configuration-and-logging.md`
- **Loki Patterns**: `.claude/rules/071.4-grafana-loki-patterns.md`
- **Grafana Playbook**: `docs/operations/01-grafana-playbook.md`
- **Previous Logging Work**: `.claude/work/tasks/TASK-LOGGING-FILE-PERSISTENCE-AND-DOCKER-CONFIG.md`
- **Observability Index**: `.claude/rules/071-observability-index.md`
