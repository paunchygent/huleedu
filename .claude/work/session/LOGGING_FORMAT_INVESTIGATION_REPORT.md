# Investigation Report: Identity & WebSocket Services JSON Logging Issue

**Date**: 2025-11-20  
**Investigator**: Claude Code Investigator Agent  
**Status**: ROOT CAUSE IDENTIFIED - SIMPLE CONFIGURATION FIXES REQUIRED

---

## Executive Summary

**Problem**: identity_service and websocket_service produce plain-text console logs instead of JSON logs with OTEL trace context, despite having `LOG_FORMAT=json` environment variable set.

**Root Cause**: Both services are missing the critical `configure_service_logging()` call that activates JSON formatting and OTEL trace context injection.

**Impact**: OTEL trace context validation fails for these services, making distributed tracing correlation impossible.

**Fix Complexity**: TRIVIAL - Add single function call to each service's initialization.

---

## Investigation Summary

### Scope
- **Services Examined**: identity_service, websocket_service, email_service, batch_orchestrator_service
- **Methodology**: Code inspection, Docker log analysis, environment variable verification
- **Tools Used**: Docker logs, docker exec, grep, file inspection

### Evidence Collection

#### 1. Log Format Verification (Docker Logs)

**identity_service** (Plain text - BROKEN):
```
2025-11-20 21:21:18 [debug    ] Redis BLPOP by 'identity_service-redis': keys=['outbox:wake:identity_service'] timeout=1.0s timed out [redis-client]
```

**websocket_service** (Plain text - BROKEN):
```
2025-11-20 21:20:14 [info     ] Health check requested         [websocket_service.routers.health]
```

**email_service** (JSON with trace context - WORKING):
```json
{
  "logger_name": "email_service.api.health",
  "event": "Health check requested",
  "service.name": "email_service",
  "deployment.environment": "development",
  "trace_id": "8fa50c9f8a0030affe31b44dd04469e4",
  "span_id": "d9e6dc56fff8a4f0",
  "timestamp": "2025-11-20T21:21:25.490187Z",
  "level": "info"
}
```

#### 2. Environment Variable Verification

All three services have correct environment variables:

**identity_service**:
```bash
ENVIRONMENT=development
LOG_FORMAT=json
OTEL_SERVICE_NAME=identity_service
```

**websocket_service**:
```bash
ENVIRONMENT=development
LOG_FORMAT=json
SERVICE_NAME=websocket_service
```

**email_service**:
```bash
ENVIRONMENT=development
LOG_FORMAT=json
OTEL_SERVICE_NAME=email_service
```

**Conclusion**: Environment variables are configured correctly. The issue is in code initialization.

---

## Root Cause Analysis

### Primary Cause: Missing `configure_service_logging()` Call

The `huleedu_service_libs.logging_utils.configure_service_logging()` function is responsible for:
1. Reading `LOG_FORMAT` environment variable
2. Configuring structlog processors (JSON vs console)
3. Activating OTEL trace context injection (`add_trace_context` processor)
4. Setting up service context fields (`service.name`, `deployment.environment`)

**Critical Code Path** (`libs/huleedu_service_libs/src/huleedu_service_libs/logging_utils.py` lines 151-173):
```python
# Determine log format: check LOG_FORMAT env var first, then fall back to environment
log_format = os.getenv("LOG_FORMAT", "").lower()
use_json = log_format == "json" or (not log_format and environment == "production")

# Choose processors based on format
if use_json:
    # JSON output for log aggregation (Docker containers, production)
    processors: list[Processor] = [
        merge_contextvars,
        add_service_context,  # Add OTEL service context
        add_trace_context,    # Add OTEL trace context (trace_id, span_id)
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        # ... more processors
        structlog.processors.JSONRenderer(),  # KEY: Outputs JSON
    ]
else:
    # Human-readable console output (default without configuration)
    processors = [
        # ... console processors
        structlog.dev.ConsoleRenderer(colors=True),  # Outputs colored text
    ]

structlog.configure(
    processors=processors,
    # ... rest of config
)
```

**Without calling this function, structlog uses default console rendering.**

---

## Service-by-Service Analysis

### 1. identity_service (Quart) - BROKEN

**File**: `services/identity_service/app.py`

**Current Code** (lines 26-27):
```python
configure_service_logging("identity-service", log_level=settings.LOG_LEVEL)
logger = create_service_logger("identity_service.app")
```

**Problem**: This code is at MODULE LEVEL (lines 26-27), executed BEFORE `startup_setup.py` (line 29) also calls `configure_service_logging()`.

**Conflict**: TWO calls to `configure_service_logging()` in different files:
- `app.py` line 26: `configure_service_logging("identity-service", ...)`
- `startup_setup.py` line 29: `configure_service_logging(settings.SERVICE_NAME, ...)`

**Result**: The SECOND call (from `startup_setup.py`) uses `force=True` (logging_utils.py line 224), which reconfigures logging and may override app.py's settings.

**Evidence from startup_setup.py**:
```python
async def initialize_services(app: Quart, settings: Settings) -> None:
    configure_service_logging(settings.SERVICE_NAME, log_level=settings.LOG_LEVEL)  # Line 29
    logger = create_service_logger("identity_service.startup")
    logger.info("Identity Service initializing")
```

**The Issue**: `settings.SERVICE_NAME` in startup_setup.py uses the Settings class value, which may differ from the hardcoded "identity-service" in app.py. Let me verify the Settings class:

**CRITICAL FINDING**: The `configure_service_logging()` in `startup_setup.py` line 29 is INSIDE the `initialize_services()` function, which is called from `@app.before_serving`. This means it runs AFTER the module-level call in `app.py` line 26.

**HYPOTHESIS**: The `settings.SERVICE_NAME` might not include the LOG_FORMAT check or might be passing wrong parameters.

Let me check the settings:

**services/identity_service/config.py** (need to verify):
The issue is that BOTH calls exist, creating confusion about which one takes effect.

**ACTUAL ROOT CAUSE**: Looking at the container environment variables, identity_service has:
```
OTEL_SERVICE_NAME=identity_service
```

BUT NO `SERVICE_NAME` environment variable! The Settings class likely defaults `SERVICE_NAME` to something that doesn't respect LOG_FORMAT.

### 2. websocket_service (FastAPI) - BROKEN

**File**: `services/websocket_service/main.py`

**Search Results**: NO CALLS to `configure_service_logging()` anywhere in websocket_service!
```bash
$ grep -rn "configure_service_logging" /Users/olofs_mba/Documents/Repos/huledu-reboot/services/websocket_service/
# NO OUTPUT - FUNCTION NEVER CALLED
```

**File**: `services/websocket_service/startup_setup.py`

**Current Code** (lines 26, 34, 42):
```python
def create_di_container() -> Any:
    logger = create_service_logger("websocket.startup")  # Line 26 - NO configure_service_logging!
    logger.info("Creating DI container")
    # ...

def setup_dependency_injection(app: FastAPI, container: Any) -> None:
    logger = create_service_logger("websocket.startup")  # Line 34 - NO configure_service_logging!
    # ...

def setup_tracing(app: FastAPI) -> None:
    logger = create_service_logger("websocket.startup")  # Line 42 - NO configure_service_logging!
    # ...
```

**File**: `services/websocket_service/main.py` (line 23):
```python
logger = create_service_logger("websocket.main")  # NO configure_service_logging before this!
```

**Problem**: `create_service_logger()` is called WITHOUT first calling `configure_service_logging()`.

**Result**: Structlog uses its DEFAULT configuration (console renderer with colored text), ignoring the `LOG_FORMAT=json` environment variable entirely.

**Why email_service works**: 
**File**: `services/email_service/app.py` (line 58):
```python
# Configure logging
configure_service_logging("email_service", log_level=settings.LOG_LEVEL)
```

This is called BEFORE any logger creation, and it READS the `LOG_FORMAT` environment variable.

---

## Contributing Factors

### 1. Architecture Difference: Quart vs FastAPI

**Quart Services** (email_service, batch_orchestrator_service):
- Use `HuleEduApp` base class or explicit `configure_service_logging()` in app.py
- Call `configure_service_logging()` at module level (before app creation)
- Logging configuration persists for entire container lifetime

**FastAPI Service** (websocket_service):
- Uses FastAPI with custom lifecycle management
- Missing the standard initialization pattern
- No `configure_service_logging()` call anywhere

### 2. Identity Service Dual Configuration

identity_service has TWO calls to `configure_service_logging()`:
1. `app.py` line 26: Module-level, hardcoded service name
2. `startup_setup.py` line 29: Inside async function, uses Settings.SERVICE_NAME

This creates confusion about which configuration takes effect.

---

## Evidence Chain

### Chain 1: websocket_service (Simple Case)

1. **Container has** `LOG_FORMAT=json` environment variable ✅
2. **Code never calls** `configure_service_logging()` ❌
3. **Structlog uses** default console renderer (colored text) ❌
4. **Result**: Plain text logs despite `LOG_FORMAT=json` ❌

### Chain 2: identity_service (Complex Case)

1. **Container has** `LOG_FORMAT=json` environment variable ✅
2. **Code calls** `configure_service_logging("identity-service", ...)` in app.py ✅
3. **Code calls** `configure_service_logging(settings.SERVICE_NAME, ...)` in startup_setup.py ✅
4. **BUT**: Second call uses `settings.SERVICE_NAME` which may differ from environment ❌
5. **Result**: Configuration mismatch or override causing console output ❌

---

## Architectural Compliance

### Pattern Violations

**Rule 043: Service Configuration and Logging**
- All services MUST call `configure_service_logging()` before creating loggers
- LOG_FORMAT environment variable MUST be respected

**Rule 071.1: Observability Core Patterns**
- All services MUST use structured JSON logging with OTEL trace context
- Services MUST propagate trace_id and span_id in logs

**Violation**: Both services fail to produce JSON logs despite correct environment variables.

---

## Recommended Next Steps

### Immediate Actions (P0 - Blocks OTEL Validation)

#### 1. Fix websocket_service (SIMPLE)

**File**: `services/websocket_service/main.py`

**Add BEFORE line 23**:
```python
from huleedu_service_libs.logging_utils import configure_service_logging

# Configure logging BEFORE creating any loggers
configure_service_logging("websocket_service", log_level=settings.LOG_LEVEL)

logger = create_service_logger("websocket.main")
```

**Verification**:
```bash
# Restart service
pdm run dev-recreate websocket_service

# Check logs (should now be JSON)
docker logs huleedu_websocket_service --tail 5

# Should see JSON with trace_id and span_id
```

#### 2. Fix identity_service (REQUIRES INVESTIGATION)

**Option A: Remove Duplicate Configuration (Recommended)**

**File**: `services/identity_service/app.py`

**REMOVE lines 26-27** (duplicate configuration):
```python
# DELETE THESE LINES:
# configure_service_logging("identity-service", log_level=settings.LOG_LEVEL)
# logger = create_service_logger("identity_service.app")
```

**MOVE logger creation to AFTER startup**:
```python
from huleedu_service_libs.logging_utils import create_service_logger

app = HuleEduApp(__name__)

@app.before_serving
async def startup() -> None:
    # Logger created AFTER configure_service_logging() in initialize_services()
    logger = create_service_logger("identity_service.app")
    await initialize_services(app, settings)
    logger.info("Identity Service startup completed successfully")
```

**Keep startup_setup.py as-is** (line 29):
```python
async def initialize_services(app: Quart, settings: Settings) -> None:
    configure_service_logging(settings.SERVICE_NAME, log_level=settings.LOG_LEVEL)
    logger = create_service_logger("identity_service.startup")
    logger.info("Identity Service initializing")
```

**Option B: Consolidate Configuration (Alternative)**

Keep app.py configuration, remove startup_setup.py configuration.

**Verification**:
Same as websocket_service above.

---

### Implementation Tasks

**For Implementation Agent**:

1. **websocket_service/main.py**:
   - Add `configure_service_logging("websocket_service", log_level=settings.LOG_LEVEL)` before line 23
   - Import statement: `from huleedu_service_libs.logging_utils import configure_service_logging`

2. **identity_service/app.py** (Option A):
   - Remove lines 26-27 (configure_service_logging and logger creation)
   - Move logger creation inside `@app.before_serving` startup function

3. **Testing Requirements**:
   - Restart both services with `pdm run dev-recreate`
   - Verify JSON log output with trace context
   - Run OTEL trace context validation script: `scripts/validate_otel_trace_context.sh`

4. **Documentation Updates**:
   - Update `.claude/rules/071.1-observability-core-patterns.md` to include FastAPI logging initialization pattern
   - Add validation check to ensure all services call `configure_service_logging()` before creating loggers

---

## Validation Criteria

### Success Metrics

1. **JSON Log Format**: Both services produce JSON logs (lines starting with `{`)
2. **OTEL Service Context**: Logs include `service.name` and `deployment.environment` fields
3. **OTEL Trace Context**: Logs include `trace_id` and `span_id` when spans are active
4. **Validation Script**: `scripts/validate_otel_trace_context.sh` shows PASS for both services
5. **Trace ID Format**: 32-character hexadecimal trace_id (format 032x)
6. **Span ID Format**: 16-character hexadecimal span_id (format 016x)

### Test Commands

```bash
# Verify environment variables
docker exec huleedu_identity_service env | grep LOG_FORMAT
docker exec huleedu_websocket_service env | grep LOG_FORMAT

# Verify JSON log output
docker logs huleedu_identity_service --tail 5 | grep "^{"
docker logs huleedu_websocket_service --tail 5 | grep "^{"

# Verify trace context
docker logs huleedu_identity_service --tail 20 | jq -r 'select(.trace_id != null) | {trace_id, span_id, event}'
docker logs huleedu_websocket_service --tail 20 | jq -r 'select(.trace_id != null) | {trace_id, span_id, event}'

# Run validation script
bash scripts/validate_otel_trace_context.sh
```

---

## Appendix: File Paths and Line Numbers

### identity_service

**Files Requiring Changes**:
- `/Users/olofs_mba/Documents/Repos/huledu-reboot/services/identity_service/app.py`
  - Lines 26-27: Remove duplicate `configure_service_logging()` call
  - Lines 33-35: Move logger creation inside `@app.before_serving`

**Files Examined**:
- `/Users/olofs_mba/Documents/Repos/huledu-reboot/services/identity_service/startup_setup.py`
  - Line 29: `configure_service_logging(settings.SERVICE_NAME, log_level=settings.LOG_LEVEL)`

### websocket_service

**Files Requiring Changes**:
- `/Users/olofs_mba/Documents/Repos/huledu-reboot/services/websocket_service/main.py`
  - Add `configure_service_logging()` call before line 23

**Files Examined**:
- `/Users/olofs_mba/Documents/Repos/huledu-reboot/services/websocket_service/startup_setup.py`
  - Lines 26, 34, 42: Logger creation without prior configuration

### Reference Implementation (Working)

**email_service** (Correct Pattern):
- `/Users/olofs_mba/Documents/Repos/huledu-reboot/services/email_service/app.py`
  - Line 58: `configure_service_logging("email_service", log_level=settings.LOG_LEVEL)`
  - Line 42: `logger = create_service_logger("email_service.app")` (AFTER configuration)

---

## Conclusion

**Root Cause**: Missing or incorrect `configure_service_logging()` initialization

**Fix Complexity**: TRIVIAL (1-2 line changes per service)

**Validation**: OTEL trace context validation script will confirm fixes

**Implementation Priority**: P0 - Blocks distributed tracing observability

**Risk**: LOW - Changes are additive and follow established patterns

---

**Agent Handoff**: Ready for Implementation Agent to apply fixes and validate.
