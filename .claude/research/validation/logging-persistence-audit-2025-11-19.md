# Logging Persistence and Service Alignment Audit
**Date:** 2025-11-19
**Status:** Audit Required
**Priority:** Medium
**Scope:** All HuleEdu services, observability stack integration

## Context

During serial_bundle validation testing, we discovered that background ENG5 validation tasks have no log persistence mechanism. Investigation revealed broader issues with logging configuration across the HuleEdu platform.

## Current State Assessment

### Logging Stack Components

**Centralized Configuration:**
- Location: `libs/huleedu_service_libs/src/huleedu_service_libs/logging_utils.py`
- Functions: `configure_service_logging()`, `create_service_logger()`
- Framework: structlog + standard library logging
- Output: stdout only (no file handlers)

**Observability Stack:**
- Prometheus: Metrics collection (operational)
- Grafana: Metrics visualization (operational)
- Jaeger: Distributed tracing (operational)
- Loki: Log aggregation (status unknown)

**Docker Configuration:**
- No logging driver specified in `docker-compose.*.yml`
- Default: json-file driver (unbounded)
- Logs stored in Docker VM (macOS) - not directly accessible

### Service Logging Status

| Service | Logging Config | Status | File Location | Issues |
|---------|---------------|--------|---------------|--------|
| CJ Assessment | ✓ Calls `configure_service_logging()` | Partial | app.py:61 | stdout only, no files |
| LLM Provider | ✗ Missing `configure_service_logging()` | Broken | startup_setup.py:20 | Only create_service_logger, inconsistent format |
| API Gateway | ✗ Missing `configure_service_logging()` | Broken | app/startup_setup.py:18 | Only create_service_logger, FastAPI service |
| Result Aggregator | ✗ Missing `configure_service_logging()` | Broken | app.py:31 | Only create_service_logger |
| Batch Orchestrator | ✓ Calls `configure_service_logging()` | Partial | app.py:22 | stdout only, no files |
| Batch Conductor | ✓ Calls `configure_service_logging()` | Partial | app.py:32 | stdout only, no files |
| Essay Lifecycle | ✓ Calls `configure_service_logging()` | Partial | app.py:29-32 | stdout only, no files |
| Class Management | ✓ Calls `configure_service_logging()` | Partial | app.py:36 | stdout only, no files |
| Content Service | ✓ Calls `configure_service_logging()` | Partial | app.py:19 | stdout only, no files |
| File Service | ✓ Calls `configure_service_logging()` | Partial | app.py:20 | stdout only, no files |
| Spellchecker | ✓ Calls `configure_service_logging()` | Partial | app.py:50 | stdout only, no files |
| Entitlements | ✓ Calls `configure_service_logging()` | Partial | app/main.py:62 | stdout only, no files |

**Summary:**
- ✓ Correct: 9 services (75%)
- ✗ Broken: 3 services (25%) - API Gateway, LLM Provider, Result Aggregator
- All services log to stdout only (no file handlers)
- 3 services missing centralized logging configuration entirely

### Key Issues Identified

1. **No file-based logging** - All services log to stdout/stderr only
2. **Inconsistent configuration** - LLM Provider Service doesn't call centralized config
3. **No persistence strategy** - Logs only available via `docker logs` (volatile)
4. **Background tasks** - Local Python processes have no log capture
5. **Loki integration** - Unknown if configured, unused if present
6. **Docker logging** - No driver config, no rotation limits, no compression

## Investigation Findings (2025-11-19)

### File Locations

**Centralized Logging:**
- `libs/huleedu_service_libs/src/huleedu_service_libs/logging_utils.py` (lines 28-100)
  - `configure_service_logging()` sets up structlog + stdlib logging
  - Line 89: `stream=sys.stdout` - only stdout, no files
  - No `FileHandler` or `RotatingFileHandler`

**Service-Specific:**
- `services/cj_assessment_service/app.py` (line 61): ✓ Calls `configure_service_logging()`
- `services/llm_provider_service/startup_setup.py` (line 20): ✗ Only calls `create_service_logger()`
- `services/llm_provider_service/app.py` (lines 34-41): Uses Quart dev server (not Hypercorn in some configs)

**Docker Configuration:**
- `docker-compose.services.yml`: No logging section
- `docker-compose.dev.yml`: No logging section
- `services/*/Dockerfile`: ✓ All set `PYTHONUNBUFFERED=1` (correct)

### Observability Stack Integration

**Prometheus + Grafana:** ✓ Operational
- Metrics instrumented in all services
- Dashboards available
- No issues found

**Jaeger:** ✓ Operational
- Distributed tracing configured
- W3C trace propagation
- OpenTelemetry integration

**Loki:** ✓ Fully Operational (Status: VERIFIED)
- **Location**: `observability/docker-compose.observability.yml`
- **Loki**: grafana/loki:3.1.0 on port 3100
- **Promtail**: grafana/promtail:3.1.0 configured for Docker log scraping
- **Configuration**: `observability/promtail/promtail-config.yml`
- **Scope**: Scrapes all containers on `huleedu_internal_network`
- **Features**:
  - JSON log parsing
  - Correlation ID extraction
  - Service label promotion
  - Timestamp normalization
- **Grafana**: Pre-configured as datasource on port 3000
- **Status**: Deployed and ready to use

### Architectural Requirements

From `.claude/rules/046-docker-container-debugging.md`:
- Structured logging required for all services
- Correlation IDs must be propagated
- Log levels configurable per service
- Development vs production logging separation

From observability patterns:
- Logs should integrate with Loki for long-term storage
- JSON format for machine-readable logs
- Human-readable format for development
- Retention policies per environment

## Required Audit Tasks

### Task 1: Complete Service Logging Survey

**Objective:** Audit all 12 services for logging configuration compliance

**Steps:**
1. For each service, check:
   - Does `app.py` call `configure_service_logging()`?
   - Are there custom loggers that bypass centralized config?
   - Is log level configurable via env var?
   - Does service use structlog consistently?
2. Document findings in table format
3. Identify services needing fixes

**Services to audit:**
- api_gateway_service
- batch_orchestrator_service
- batch_conductor_service
- essay_lifecycle_service
- class_management_service
- content_service
- file_service
- spellchecker_service
- cj_assessment_service (✓ already audited)
- llm_provider_service (✓ already audited, needs fix)
- result_aggregator_service
- entitlements_service

### Task 2: Design File-Based Logging Strategy

**Objective:** Add file persistence without breaking existing stdout logging

**Requirements:**
1. Maintain stdout logging for Docker capture
2. Add file handlers with rotation
3. Support both JSON and human-readable formats
4. Configure per-environment (dev vs prod)
5. Integrate with Loki if available

**Design decisions needed:**
- File location: `/app/logs/` in container?
- Volume mount: `./logs/<service>:/app/logs`?
- Rotation: `RotatingFileHandler` with what limits?
- Formats: JSON + text, or JSON only?
- Retention: How long before deletion/archive?

**Implementation approach:**
- Modify `configure_service_logging()` to add `FileHandler`
- Make file logging optional via env var
- Ensure backward compatibility
- Test with one service first (CJ Assessment)

### Task 3: Docker Logging Configuration

**Objective:** Configure Docker Compose with proper logging driver and limits

**Requirements:**
1. Specify json-file driver explicitly
2. Set max-size and max-file limits
3. Enable compression
4. Document retention policy

**Proposed configuration:**
```yaml
x-logging: &default-logging
  driver: json-file
  options:
    max-size: "100m"      # 100MB per file
    max-file: "10"        # Keep 10 files = 1GB total per container
    compress: "true"      # Compress rotated logs
    labels: "service,environment"
```

**Implementation:**
- Add to both `docker-compose.services.yml` and `docker-compose.dev.yml`
- Apply to all services
- Test with `docker inspect <container>` to verify

### Task 4: Loki Integration Assessment

**Objective:** Determine if Loki is configured and create integration plan if not

**Investigation:**
1. Check if Loki container exists in Docker Compose
2. Check if promtail is configured to scrape logs
3. Review Grafana for Loki data sources
4. Document current state

**If Loki exists:**
- Verify configuration
- Ensure all services are scraped
- Test query performance
- Document access patterns

**If Loki doesn't exist:**
- Design Loki + Promtail setup
- Create Docker Compose configuration
- Plan data retention policies
- Document deployment steps

### Task 5: Background Task Logging

**Objective:** Ensure ENG5 validation runs and other background tasks have persistent logs

**Requirements:**
1. ENG5 runner should log to files by default
2. Support both verbose console output and file logging
3. Include structured metadata (batch ID, mode, etc.)
4. Rotate logs to prevent disk fill

**Design options:**

**Option A: Built-in file logging**
```python
# In cli.py, add FileHandler automatically
log_file = f"logs/eng5-{batch_id}-{timestamp}.log"
file_handler = logging.FileHandler(log_file)
logger.addHandler(file_handler)
```

**Option B: Shell redirection (current workaround)**
```bash
pdm run eng5-np-run ... > logs/run-$(date +%Y%m%d-%H%M%S).log 2>&1
```

**Option C: Dedicated logging service**
- Background tasks send logs to syslog/Loki
- Centralized collection
- More complex setup

**Recommendation:** Start with Option A (built-in), document Option B as fallback

### Task 6: Alignment with HuleEdu Architecture

**Objective:** Ensure logging strategy aligns with architectural principles

**Principles to verify:**
1. **DDD/Clean Architecture:** Logging at boundary layers (API, Kafka handlers)
2. **Service isolation:** Each service manages own logs
3. **Observability triad:** Logs + Metrics + Traces all configured
4. **12-factor app:** Logs to stdout, config via env vars
5. **Security:** No secrets in logs, PII handling

**Review checklist:**
- [ ] Structured logging used everywhere (JSON format)
- [ ] Correlation IDs propagated across all services
- [ ] Log levels follow standards (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- [ ] Error handling logs include full context
- [ ] Business events logged separately from technical logs
- [ ] Secrets/credentials never logged
- [ ] PII handling complies with data protection requirements

## Proposed Solution Architecture

### Layered Logging Strategy

**Layer 1: Application Logs (stdout)**
- Current: structlog → stdout
- Keep for Docker capture
- Format: JSON in production, human-readable in dev
- Retention: Docker driver limits (100MB × 10 = 1GB per service)

**Layer 2: Persistent File Logs**
- New: Add RotatingFileHandler
- Location: `/app/logs/<service>.log`
- Format: JSON for machine parsing
- Rotation: 100MB per file, 10 files = 1GB per service
- Retention: 7 days in dev, 30 days in prod

**Layer 3: Centralized Log Aggregation (Loki)**
- New or existing: Loki + Promtail
- Collection: Scrape Docker logs + file logs
- Retention: 90 days (configurable per environment)
- Query: Via Grafana dashboards

### Configuration Hierarchy

```
Environment Variables
├── LOG_LEVEL (DEBUG/INFO/WARNING/ERROR)
├── LOG_FORMAT (json/text)
├── LOG_TO_FILE (true/false)
├── LOG_FILE_PATH (/app/logs/<service>.log)
├── LOG_MAX_BYTES (104857600 = 100MB)
└── LOG_BACKUP_COUNT (10)
```

### Service-Level Implementation

```python
# libs/huleedu_service_libs/src/huleedu_service_libs/logging_utils.py

def configure_service_logging(
    service_name: str,
    *,
    log_level: str = "INFO",
    log_format: str = "json",
    log_to_file: bool = False,
    log_file_path: str | None = None,
) -> None:
    """
    Configure centralized logging for a service.

    Args:
        service_name: Service identifier for log correlation
        log_level: Logging level (DEBUG/INFO/WARNING/ERROR)
        log_format: Output format (json/text)
        log_to_file: Enable file-based logging
        log_file_path: Path to log file (default: /app/logs/{service_name}.log)
    """
    handlers = [logging.StreamHandler(sys.stdout)]  # Always log to stdout

    if log_to_file:
        log_file = log_file_path or f"/app/logs/{service_name}.log"
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=int(os.getenv("LOG_MAX_BYTES", "104857600")),  # 100MB
            backupCount=int(os.getenv("LOG_BACKUP_COUNT", "10")),
        )
        handlers.append(file_handler)

    # Configure stdlib logging with all handlers
    logging.basicConfig(
        format="%(message)s",
        handlers=handlers,
        level=getattr(logging, log_level.upper()),
    )

    # Configure structlog (unchanged)
    structlog.configure(...)
```

## Success Criteria

- [ ] All 12 services audited for logging configuration
- [ ] All services call `configure_service_logging()` consistently
- [ ] File-based logging implemented and tested
- [ ] Docker Compose logging driver configured with limits
- [ ] Loki integration assessed and documented (or implemented if missing)
- [ ] Background task logging strategy implemented
- [ ] Architecture alignment verified
- [ ] Documentation updated (service READMEs, operations runbooks)
- [ ] Migration plan created for existing deployments

## Files to Review

**Logging Infrastructure:**
- `libs/huleedu_service_libs/src/huleedu_service_libs/logging_utils.py`
- `.claude/rules/046-docker-container-debugging.md`
- `.claude/rules/071.2-prometheus-metrics-patterns.md` (observability context)

**Service Startup:**
- `services/*/app.py` (all 12 services)
- `services/*/startup_setup.py` (if exists)

**Docker Configuration:**
- `docker-compose.yml`
- `docker-compose.services.yml`
- `docker-compose.dev.yml`
- `services/*/Dockerfile`

**Background Tasks:**
- `scripts/cj_experiments_runners/eng5_np/cli.py`
- `scripts/cj_experiments_runners/eng5_np/kafka_flow.py`

**Documentation:**
- `services/cj_assessment_service/README.md`
- `services/llm_provider_service/README.md`
- `docs/operations/` (any logging runbooks)

## Related Work

- **Batch State Fixes:** `.claude/work/tasks/TASK-CJ-BATCH-STATE-AND-COMPLETION-FIXES.md` (7 PRs)
- **Serial Bundle Validation:** Background tasks that triggered this investigation
- **Observability Stack:** Prometheus, Grafana, Jaeger already operational

## Next Steps

1. Review this audit document
2. Execute Task 1 (service survey) to get complete picture
3. Make design decisions for Tasks 2-4
4. Create implementation PRs
5. Test with one service before rolling out to all

---

**Note:** This audit was triggered by serial_bundle validation testing but addresses platform-wide logging gaps. The logging strategy should support both operational debugging and long-term observability requirements.
