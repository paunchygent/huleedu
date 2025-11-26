# Port Documentation Audit and Update Report

**Completed**: 2025-11-26
**Task**: Audit and update port documentation to reflect recent service port configuration changes

## Summary of Changes

All service port configurations have been updated across the codebase. The following documentation changes were made:

### 1. CJ Assessment Service

**Files Updated**:
- `/services/cj_assessment_service/README.md`
- `/.claude/rules/020.7-cj-assessment-service.md`

**Changes**:
- **Line 371 in README.md**: Changed `METRICS_PORT=9090` → `HTTP_PORT=9090`
- **Line 552 in README.md**: Updated observability description from `METRICS_PORT` to `HTTP_PORT`
- **Line 16 in 020.7-cj-assessment-service.md**: Confirmed port mapping: 9090 (internal) → 9095 (host via docker-compose)
- **Line 130 in 020.7-cj-assessment-service.md**: Updated config section from `METRICS_PORT` to `HTTP_PORT`

**Rationale**: The service was renamed from METRICS_PORT to HTTP_PORT for consistency across the platform, as the port serves both health checks and metrics endpoints.

### 2. Content Service

**Files Updated**:
- `/services/content_service/README.md`

**Changes**:
- **Line 61**: Updated configuration description to clarify port env var as `PORT` or `HTTP_PORT` (Default: 8000)

**Note**: Docker container mapping: 8001:8000 (host:internal)

### 3. API Gateway Service

**Files Updated**:
- `/services/api_gateway_service/README.md`

**Changes**:
- **Line 262**: Updated `API_GATEWAY_FILE_SERVICE_URL` default from `http://file_service:8000` → `http://file_service:7001`
- **Line 263**: Updated `API_GATEWAY_CMS_API_URL` default from `http://class_management_service:8000` → `http://class_management_service:5002`

**Note**: These URLs refer to internal service-to-service communication (Docker network), not externally mapped ports.

### 4. File Service

**Files Updated**:
- `/services/file_service/README.md`

**Changes**:
- **Line 125**: Updated Docker example port mapping from `9094:9094` → `9099:9099`

**Rationale**: Prometheus port changed from 9094 to 9099 to avoid port conflict with Kafka.

### 5. Observability/Debugging Documentation

**Files Updated**:
- `/docs/how-to/debugging-with-observability.md`

**Changes**:
- **Line 419**: Updated example curl command from `http://localhost:8000/api/v1/healthz` → `http://localhost:8080/healthz`
  - Added clarification: "API Gateway on port 8080 in Docker, 4001 locally"

## Port Configuration Summary (from docker-compose.services.yml)

### Service Port Mappings

| Service | Internal Port | Host Port (Docker) | Purpose |
|---------|---------------|--------------------|---------|
| Content Service | 8000 | 8001 | HTTP API |
| CJ Assessment Service | 9090 | 9095 | HTTP API + Metrics |
| Entitlements Service | 8083 | 8083 | HTTP API |
| Language Tool Service | 8085 | 8085 | HTTP API |
| File Service | 7001 | 7001 | HTTP API |
| File Service Prometheus | 9099 | (internal) | Metrics |
| API Gateway Service | 8080 | 8080 | HTTP API (docker) / 4001 (local) |
| Result Aggregator | 4003 | 4003 | HTTP API + Metrics |
| Class Management | 5002 | 5002 | HTTP API |
| Essay Lifecycle | 6000 | 6001 | HTTP API |
| Batch Orchestrator | 5000 | 5001 | HTTP API |
| LLM Provider Service | 8080 | 8090 | HTTP API |
| Websocket Service | 8080 | 8081 | WebSocket |
| Identity Service | 7005 | 7005 | HTTP API |
| Identity Service Prometheus | 9097 | 9097 | Metrics |
| Email Service | 8080 | 8082 | HTTP API |
| Email Service Prometheus | 9098 | 9098 | Metrics |

### Service-to-Service Communication URLs (Internal Docker Network)

- **CJ Assessment Service**: `http://content_service:8000/v1/content` (Content Service reference)
- **API Gateway**:
  - File Service: `http://file_service:7001`
  - Class Management: `http://class_management_service:5002`
  - Result Aggregator: `http://result_aggregator_service:4003`
  - Batch Orchestrator: `http://batch_orchestrator_service:5000`

### Configuration Files Verified

**No changes needed** - Already have correct defaults:
- `services/cj_assessment_service/config.py`: `HTTP_PORT: int = 9090` ✓
- `services/content_service/config.py`: `HTTP_PORT: int = 8000` ✓
- `services/file_service/config.py`: `PROMETHEUS_PORT: int = 9099` ✓
- `services/entitlements_service/config.py`: `HTTP_PORT: int = 8083` ✓
- `services/language_tool_service/config.py`: `HTTP_PORT: int = 8085` ✓
- `services/api_gateway_service/config.py`: Correct URL defaults ✓

## Files NOT Updated (No Port References Found)

- `services/entitlements_service/README.md` - No port references needing update
- `services/language_tool_service/README.md` - No port references needing update (already mentions correct port 8085)

## Documentation Files Cross-Checked

✓ `docs/reference/apis/API_REFERENCE.md` - References API Gateway (4001 localhost / 8080 docker)
✓ `docs/how-to/grafana-dashboard-import-guide.md` - References correct ports
✓ `docs/how-to/SHARED_CODE_PATTERNS.md` - References API Gateway (4001)
✓ `docs/how-to/SVELTE_INTEGRATION_GUIDE.md` - References API Gateway (4001)
✓ `docs/how-to/FRONTEND_INTEGRATION_INDEX.md` - References API Gateway (4001)

## Validation

All changes have been made to documentation files only. No source code modifications were performed.

**Total files updated**: 5
**Total changes made**: 8

All port mappings are now consistent with the current `docker-compose.services.yml` configuration.

## Files Updated with Line Numbers

### `/services/cj_assessment_service/README.md`
- Line 371: Environment variable documentation
- Line 552: Observability features section

### `/.claude/rules/020.7-cj-assessment-service.md`
- Line 16: Service Identity section
- Line 130: Configuration section

### `/services/content_service/README.md`
- Line 61: Configuration settings

### `/services/api_gateway_service/README.md`
- Line 262: FILE_SERVICE_URL configuration
- Line 263: CMS_API_URL configuration

### `/services/file_service/README.md`
- Line 125: Docker example command

### `/docs/how-to/debugging-with-observability.md`
- Line 419: Curl example command with explanatory comment
