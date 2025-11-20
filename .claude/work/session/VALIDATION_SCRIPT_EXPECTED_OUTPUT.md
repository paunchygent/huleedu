# Expected Validation Script Output

This document shows what the validation script output will look like when services are running with correct OTEL trace context.

---

## Successful Validation Output

```bash
$ ./scripts/validate_otel_trace_context.sh

OTEL Trace Context Validation
==============================

=== Validating cj_assessment_service ===
✓ Format valid: trace_id (32-char hex), span_id (16-char hex)
Sample log with trace context:
  {
    "timestamp": "2025-11-20T17:23:45.123456Z",
    "event": "Processing comparison judgment",
    "trace_id": "a1b2c3d4e5f67890a1b2c3d4e5f67890",
    "span_id": "1234567890abcdef"
  }
  {
    "timestamp": "2025-11-20T17:23:45.234567Z",
    "event": "LLM request completed",
    "trace_id": "a1b2c3d4e5f67890a1b2c3d4e5f67890",
    "span_id": "2345678901bcdef0"
  }

✓ Service validation passed (125/500 logs have trace context)

=== Validating api_gateway_service ===
✓ Format valid: trace_id (32-char hex), span_id (16-char hex)
Sample log with trace context:
  {
    "timestamp": "2025-11-20T17:23:40.000000Z",
    "event": "Received POST /api/v1/assessments/batch",
    "trace_id": "a1b2c3d4e5f67890a1b2c3d4e5f67890",
    "span_id": "0000000000000001"
  }

✓ Service validation passed (45/500 logs have trace context)

=== Validating batch_orchestrator_service ===
✓ Format valid: trace_id (32-char hex), span_id (16-char hex)
Sample log with trace context:
  {
    "timestamp": "2025-11-20T17:23:42.500000Z",
    "event": "Creating batch for assessment",
    "trace_id": "a1b2c3d4e5f67890a1b2c3d4e5f67890",
    "span_id": "abcdef0123456789"
  }

✓ Service validation passed (67/500 logs have trace context)

=== Validating spellchecker_service ===
✓ Format valid: trace_id (32-char hex), span_id (16-char hex)
Sample log with trace context:
  {
    "timestamp": "2025-11-20T17:23:44.000000Z",
    "event": "Processing spellcheck request",
    "trace_id": "f9e8d7c6b5a4f9e8d7c6b5a4f9e8d7c6",
    "span_id": "fedcba9876543210"
  }

✓ Service validation passed (32/500 logs have trace context)

=== Cross-Service Trace Validation ===
Using trace_id from cj_assessment_service: a1b2c3d4e5f67890a1b2c3d4e5f67890

✓ Found in cj_assessment_service:
  {"service": "cj_assessment_service", "event": "Processing comparison judgment", "timestamp": "2025-11-20T17:23:45.123456Z"}

✓ Found in api_gateway_service:
  {"service": "api_gateway_service", "event": "Received POST /api/v1/assessments/batch", "timestamp": "2025-11-20T17:23:40.000000Z"}

✓ Found in batch_orchestrator_service:
  {"service": "batch_orchestrator_service", "event": "Creating batch for assessment", "timestamp": "2025-11-20T17:23:42.500000Z"}

✓ Cross-service tracing validated (trace_id found in 3 services)

=== Jaeger Correlation Validation ===
✓ Jaeger is accessible
Checking trace_id in Jaeger: a1b2c3d4e5f67890a1b2c3d4e5f67890
✓ Trace exists in Jaeger: a1b2c3d4e5f67890a1b2c3d4e5f67890

=== Validation Matrix ===

| Service                    | Container Running | Logs Have trace_id | Logs Have span_id | Format Valid | % With Context | Status |
|----------------------------|-------------------------------------------------------------------------------------|
| cj_assessment_service      | YES               | YES                | YES               | YES          | 25%            | PASS   |
| api_gateway_service        | YES               | YES                | YES               | YES          | 9%             | PASS   |
| batch_orchestrator_service | YES               | YES                | YES               | YES          | 13%            | PASS   |
| spellchecker_service       | YES               | YES                | YES               | YES          | 6%             | PASS   |

=== Recommendations ===

✓ All validated services have correct OTEL trace context in logs
  - trace_id format: 32-character hexadecimal
  - span_id format: 16-character hexadecimal
  - Fields appear in logs when spans are active
```

---

## Warning Case Output (Services Idle)

```bash
$ ./scripts/validate_otel_trace_context.sh

OTEL Trace Context Validation
==============================

=== Validating cj_assessment_service ===
⚠ No logs with trace_id found

=== Validating api_gateway_service ===
⚠ No logs with trace_id found

=== Validating batch_orchestrator_service ===
⚠ No logs with trace_id found

=== Validating spellchecker_service ===
⚠ No logs with trace_id found

=== Cross-Service Trace Validation ===
⚠ No trace_id found to validate cross-service tracing

=== Jaeger Correlation Validation ===
✓ Jaeger is accessible
⚠ No trace_id available to check in Jaeger

=== Validation Matrix ===

| Service                    | Container Running | Logs Have trace_id | Logs Have span_id | Format Valid | % With Context | Status |
|----------------------------|-------------------------------------------------------------------------------------|
| cj_assessment_service      | YES               | NO                 | NO                | N/A          | 0%             | WARN   |
| api_gateway_service        | YES               | NO                 | NO                | N/A          | 0%             | WARN   |
| batch_orchestrator_service | YES               | NO                 | NO                | N/A          | 0%             | WARN   |
| spellchecker_service       | YES               | NO                 | NO                | N/A          | 0%             | WARN   |

=== Recommendations ===

⚠ All services running but no trace context found in logs

This is EXPECTED BEHAVIOR if:
  - Services are idle (no requests processed)
  - No spans have been created yet
  - Services just started (haven't received traced requests)

To generate trace context, trigger operations:
  curl -X POST http://localhost:8000/api/v1/assessments/batch \
    -H "Content-Type: application/json" \
    -d '{"batch_size": 10}'

Then run validation again.
```

---

## Current Output (Services Not Running)

```bash
$ ./scripts/validate_otel_trace_context.sh

OTEL Trace Context Validation
==============================

=== Validating cj_assessment_service ===
⚠ Container huleedu_cj_assessment_service not running

=== Validating api_gateway_service ===
⚠ Container huleedu_api_gateway_service not running

=== Validating batch_orchestrator_service ===
⚠ Container huleedu_batch_orchestrator_service not running

=== Validating spellchecker_service ===
⚠ Container huleedu_spellchecker_service not running

=== Cross-Service Trace Validation ===
⚠ No trace_id found to validate cross-service tracing

=== Jaeger Correlation Validation ===
✓ Jaeger is accessible
⚠ No trace_id available to check in Jaeger

=== Validation Matrix ===

| Service                    | Container Running | Logs Have trace_id | Logs Have span_id | Format Valid | % With Context | Status |
|----------------------------|-------------------------------------------------------------------------------------|
| cj_assessment_service      | NO                | N/A                | N/A               | N/A          | N/A            | SKIP   |
| api_gateway_service        | NO                | N/A                | N/A               | N/A          | N/A            | SKIP   |
| batch_orchestrator_service | NO                | N/A                | N/A               | N/A          | N/A            | SKIP   |
| spellchecker_service       | NO                | N/A                | N/A               | N/A          | N/A            | SKIP   |

=== Recommendations ===

⚠ Some services not running - start services to validate:
  pdm run dev-start cj_assessment_service
  pdm run dev-start api_gateway_service
  pdm run dev-start batch_orchestrator_service
  pdm run dev-start spellchecker_service
```

---

## Failure Case Output (Implementation Error)

```bash
$ ./scripts/validate_otel_trace_context.sh

OTEL Trace Context Validation
==============================

=== Validating cj_assessment_service ===
✗ Invalid trace_id format: 1234567890abcdef (length: 16)
✗ Invalid span_id format: 1234567890abcdef1234567890abcdef (length: 32)
Sample log with trace context:
  {
    "timestamp": "2025-11-20T17:23:45.123456Z",
    "event": "Processing comparison judgment",
    "trace_id": "1234567890abcdef",
    "span_id": "1234567890abcdef1234567890abcdef"
  }

✗ Service validation failed

=== Validation Matrix ===

| Service                    | Container Running | Logs Have trace_id | Logs Have span_id | Format Valid | % With Context | Status |
|----------------------------|-------------------------------------------------------------------------------------|
| cj_assessment_service      | YES               | YES                | YES               | NO           | 25%            | FAIL   |
| api_gateway_service        | NO                | N/A                | N/A               | N/A          | N/A            | SKIP   |
| batch_orchestrator_service | NO                | N/A                | N/A               | N/A          | N/A            | SKIP   |
| spellchecker_service       | NO                | N/A                | N/A               | N/A          | N/A            | SKIP   |

=== Recommendations ===

✗ Issues found:
  - cj_assessment_service: FAIL
    Action: Verify add_trace_context processor is in structlog chain
    Action: Check format strings in add_trace_context (should be 032x for trace_id, 016x for span_id)
```

---

## Single Service Validation Output

```bash
$ ./scripts/validate_otel_trace_context.sh cj_assessment_service

OTEL Trace Context Validation
==============================

=== Validating cj_assessment_service ===
✓ Format valid: trace_id (32-char hex), span_id (16-char hex)
Sample log with trace context:
  {
    "timestamp": "2025-11-20T17:23:45.123456Z",
    "event": "Processing comparison judgment",
    "trace_id": "a1b2c3d4e5f67890a1b2c3d4e5f67890",
    "span_id": "1234567890abcdef"
  }
  {
    "timestamp": "2025-11-20T17:23:45.234567Z",
    "event": "LLM request completed",
    "trace_id": "a1b2c3d4e5f67890a1b2c3d4e5f67890",
    "span_id": "2345678901bcdef0"
  }

✓ Service validation passed (125/500 logs have trace context)
```

---

## Notes

### Expected Behavior
- **PASS**: trace_id and span_id present with correct format when spans are active
- **WARN**: No trace context found (services idle, no traced operations)
- **SKIP**: Services not running (containers not started)
- **FAIL**: trace_id/span_id present but wrong format (implementation bug)

### Percentage Thresholds
- 0%: Services idle (WARN)
- 1-20%: Normal (many logs without spans like startup, health checks)
- 20-50%: Good (active tracing on main operations)
- 50%+: Excellent (comprehensive tracing coverage)

### Jaeger Correlation
- Trace found in Jaeger: Perfect (end-to-end validation)
- Trace not found: Not necessarily an error (may be too recent, already exported, or sampling disabled)

### Cross-Service Validation
- Same trace_id in multiple services: Perfect (distributed tracing working)
- Trace only in single service: OK (operation may be isolated to one service)
- No matching trace_id: Services processing different requests (expected)
