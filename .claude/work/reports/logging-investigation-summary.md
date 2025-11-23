# Logging Configuration Investigation - Executive Summary

**Date**: 2025-11-20  
**Status**: ROOT CAUSE CONFIRMED  

---

## Problem Statement

identity_service and websocket_service produce plain-text console logs instead of JSON logs with OTEL trace context, despite having `LOG_FORMAT=json` environment variable configured in Docker Compose.

---

## Root Causes (Different for Each Service)

### websocket_service: Missing Configuration (SIMPLE FIX)

**Issue**: Service NEVER calls `configure_service_logging()`

**Evidence**:
```bash
$ grep -rn "configure_service_logging" services/websocket_service/
# NO OUTPUT - Function never called anywhere
```

**Result**: Structlog uses default console renderer, ignoring `LOG_FORMAT=json` entirely.

**Fix**: Add one line to `services/websocket_service/main.py` before line 23:
```python
from huleedu_service_libs.logging_utils import configure_service_logging
configure_service_logging("websocket_service", log_level=settings.LOG_LEVEL)
```

### identity_service: Timing Issue (COMPLEX FIX)

**Issue**: Service calls `configure_service_logging()` TWICE in wrong order

**Evidence**:
1. `app.py` line 26: Module-level call with hardcoded "identity-service" 
2. `startup_setup.py` line 29: Inside `@app.before_serving` with settings.SERVICE_NAME

**Execution Order**:
1. Module load → `app.py` line 26 runs → Logging configured ✅
2. Container starts → `@app.before_serving` runs → `startup_setup.py` line 29 runs
3. SECOND call reconfigures logging (uses `force=True` in logging.basicConfig)
4. Something in the reconfiguration breaks JSON formatting ❌

**The Mystery**: Why does the second call break JSON formatting?

**Hypothesis**: The Settings class value `settings.SERVICE_NAME = "identity_service"` (from config.py line 16) is correct, and the second call SHOULD work. The issue is likely that:
- The second call happens INSIDE an async context
- Logger instances created BEFORE reconfiguration keep old renderer
- The module-level logger at line 27 uses the OLD (console) configuration

**Fix**: Remove duplicate configuration - keep only ONE call in the correct location.

---

## Key Insight: The `configure_service_logging()` Function

From `libs/huleedu_service_libs/src/huleedu_service_libs/logging_utils.py`:

```python
def configure_service_logging(
    service_name: str,
    environment: str | None = None,
    log_level: str = "INFO",
    # ...
) -> None:
    # Line 152: Read LOG_FORMAT environment variable
    log_format = os.getenv("LOG_FORMAT", "").lower()
    use_json = log_format == "json" or (not log_format and environment == "production")
    
    if use_json:
        processors = [
            # ... JSON processors
            structlog.processors.JSONRenderer(),  # Outputs JSON
        ]
    else:
        processors = [
            # ... Console processors
            structlog.dev.ConsoleRenderer(colors=True),  # Outputs colored text
        ]
    
    # Line 228: Configure structlog with chosen processors
    structlog.configure(
        processors=processors,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,  # CRITICAL: Caches configuration
    )
```

**The Critical Parameter**: `cache_logger_on_first_use=True`

This means that once a logger is created with `create_service_logger()`, it caches the configuration. If you call `configure_service_logging()` AFTER creating loggers, those loggers keep the OLD configuration.

**This explains identity_service**:
1. `app.py` line 27 creates logger AFTER first configuration ✅
2. `startup_setup.py` line 29 reconfigures logging ❌
3. `startup_setup.py` line 30 creates NEW logger with new config ✅
4. But module-level logger from line 27 still uses OLD config ❌

---

## Correct Pattern (from email_service)

**File**: `services/email_service/app.py`

```python
# Line 58: Configure logging FIRST (module level, before app creation)
configure_service_logging("email_service", log_level=settings.LOG_LEVEL)

# Line 42: Create logger AFTER configuration (module level)
logger = create_service_logger("email_service.app")

# Lines 110-134: Use logger in lifecycle hooks
@app.before_serving
async def startup() -> None:
    # NO reconfiguration here - just use existing logger
    logger.info("Email Service started successfully")
```

**Key Points**:
1. Call `configure_service_logging()` ONCE at module level
2. Create ALL loggers AFTER configuration
3. Do NOT reconfigure in lifecycle hooks

---

## Recommended Fixes

### websocket_service (SIMPLE - 2 lines)

**File**: `services/websocket_service/main.py`

**Add after imports, before line 23**:
```python
from huleedu_service_libs.logging_utils import configure_service_logging

# Configure logging at module level (reads LOG_FORMAT env var)
configure_service_logging("websocket_service", log_level=settings.LOG_LEVEL)

logger = create_service_logger("websocket.main")
```

### identity_service (COMPLEX - Requires careful refactoring)

**Option A: Follow email_service pattern (Recommended)**

**File**: `services/identity_service/app.py` - Keep as-is (lines 26-27 are correct)

**File**: `services/identity_service/startup_setup.py` - REMOVE duplicate configuration:

```python
async def initialize_services(app: Quart, settings: Settings) -> None:
    # REMOVE THIS LINE:
    # configure_service_logging(settings.SERVICE_NAME, log_level=settings.LOG_LEVEL)
    
    # Keep logger creation (will use app.py's configuration)
    logger = create_service_logger("identity_service.startup")
    logger.info("Identity Service initializing")
    # ... rest of function
```

**Option B: Consolidate in startup_setup.py (Alternative)**

**File**: `services/identity_service/app.py` - REMOVE lines 26-27

**File**: `services/identity_service/startup_setup.py` - Keep as-is

**File**: `services/identity_service/app.py` - Move logger creation:
```python
app = HuleEduApp(__name__)

@app.before_serving
async def startup() -> None:
    await initialize_services(app, settings)
    # Create logger AFTER initialize_services() configures logging
    logger = create_service_logger("identity_service.app")
    logger.info("Identity Service startup completed successfully")
```

**Recommendation**: Use Option A (keep app.py config) because:
- Matches email_service pattern
- Module-level configuration is clearer
- Avoids async context issues

---

## Validation Commands

```bash
# Fix websocket_service
# (Apply code change)
pdm run dev-recreate websocket_service
docker logs huleedu_websocket_service --tail 5
# Expected: JSON logs with trace_id/span_id

# Fix identity_service
# (Apply code change)
pdm run dev-recreate identity_service
docker logs huleedu_identity_service --tail 5
# Expected: JSON logs with trace_id/span_id

# Run validation script
bash scripts/validate_otel_trace_context.sh
# Expected: Both services show PASS
```

---

## Files Requiring Changes

### websocket_service
- `/Users/olofs_mba/Documents/Repos/huledu-reboot/services/websocket_service/main.py`
  - Add import and configure_service_logging() call before line 23

### identity_service (Option A - Recommended)
- `/Users/olofs_mba/Documents/Repos/huledu-reboot/services/identity_service/startup_setup.py`
  - Remove line 29: `configure_service_logging(settings.SERVICE_NAME, log_level=settings.LOG_LEVEL)`

---

## Conclusion

**Root Cause**: websocket_service never configures logging; identity_service configures twice causing cache conflicts.

**Fix Complexity**: TRIVIAL for websocket_service (add 1 line), SIMPLE for identity_service (remove 1 line).

**Risk**: MINIMAL - Following established patterns from working services.

**Priority**: P0 - Blocks OTEL trace context validation and distributed tracing observability.

---
