---
id: bff-teacher-service-internal-clients
title: BFF Teacher Service Internal Clients
type: task
status: done
priority: high
domain: programs
service: bff_teacher_service
owner_team: agents
owner: ''
program: teacher_dashboard_integration
created: '2025-12-09'
last_updated: '2026-02-01'
related:
- TASKS/programs/teacher_dashboard_integration/HUB.md
- cms-batch-class-info-internal-endpoint
labels:
- bff
- http-clients
- dishka
---
# BFF Teacher Service Internal Clients

## Objective

Implement RAS and CMS HTTP clients for the BFF Teacher Service with Dishka DI integration.

**Blocked by**: `cms-batch-class-info-internal-endpoint` ✅ (completed)

## Implementation Summary

### Files Created/Modified

| File | Action | Description |
|------|--------|-------------|
| `config.py` | UPDATED | Added RAS_URL, CMS_URL, timeout settings |
| `protocols.py` | CREATED | RASClientProtocol, CMSClientProtocol |
| `clients/_utils.py` | CREATED | build_internal_auth_headers() |
| `clients/ras_client.py` | CREATED | RASClientImpl with get_batches_for_user() |
| `clients/cms_client.py` | CREATED | CMSClientImpl with get_class_info_for_batches() |
| `clients/__init__.py` | UPDATED | Exports for clients |
| `dto/teacher_v1.py` | UPDATED | Added BatchSummaryV1, ClassInfoV1, PaginationV1 |
| `di.py` | CREATED | BFFTeacherProvider, RequestContextProvider |
| `middleware.py` | CREATED | Extracted CorrelationIDMiddleware |
| `app.py` | UPDATED | Dishka integration via setup_dishka() |
| `api/v1/teacher_routes.py` | UPDATED | Real implementation with DI injection |
| `api/health_routes.py` | CREATED | Health check and favicon routes |
| `api/spa_routes.py` | CREATED | SPA fallback route |
| `tests/test_provider.py` | CREATED | AuthTestProvider, InfrastructureTestProvider |
| `tests/unit/test_ras_client.py` | CREATED | 7 unit tests |
| `tests/unit/test_cms_client.py` | CREATED | 6 unit tests |
| `tests/unit/test_teacher_routes.py` | CREATED | 7 unit tests (incl. missing auth header) |

### Key Implementation Details

**Protocols**: Type-safe interfaces for dependency injection
```python
class RASClientProtocol(Protocol):
    async def get_batches_for_user(self, user_id: str, correlation_id: UUID, *, limit: int = 20, offset: int = 0, status: str | None = None) -> tuple[list[BatchSummaryV1], dict]: ...

class CMSClientProtocol(Protocol):
    async def get_class_info_for_batches(self, batch_ids: list[UUID], correlation_id: UUID) -> dict[str, ClassInfoV1 | None]: ...
```

**Internal Auth Headers**: Consistent with API Gateway pattern
```python
{
    "X-Internal-API-Key": settings.get_internal_api_key(),
    "X-Service-ID": settings.SERVICE_NAME,
    "X-Correlation-ID": str(correlation_id),
}
```

**Dishka DI**: APP scope for clients, REQUEST scope for context
- `BFFTeacherProvider`: Config, HTTP client, RAS/CMS clients
- `RequestContextProvider`: Correlation ID from request.state, user_id from header

**Error Handling**:
- Missing `X-User-ID` header → 401 `AUTHENTICATION_ERROR`
- External service errors → 502 Bad Gateway via `raise_external_service_error()`

## Test Summary

### Unit Tests ✅ VALIDATED

```bash
pdm run pytest-root services/bff_teacher_service/tests/ -v  # 19 passed
```

| Test File | Tests | Status |
|-----------|-------|--------|
| `test_ras_client.py` | 7 | ✅ Passed |
| `test_cms_client.py` | 6 | ✅ Passed |
| `test_teacher_routes.py` | 6 | ✅ Passed |

### Functional Tests ✅ VALIDATED (2025-12-10)

**Location**: `tests/functional/test_bff_teacher_dashboard_functional.py`

**Status**: All 4 tests passing against docker-compose stack.

**Validation command**:
```bash
ALLOW_REAL_LLM_FUNCTIONAL=1 pdm run pytest-root tests/functional/test_bff_teacher_dashboard_functional.py -v
```

**Test results (4/4 passed)**:
- `test_dashboard_requires_authentication` ✅ - 401 without X-User-ID
- `test_dashboard_with_valid_user_id` ✅ - 200 with valid response structure
- `test_dashboard_returns_correlation_id` ✅ - Correlation ID propagation
- `test_health_endpoint` ✅ - Health check response

## Success Criteria

- [x] RAS client sends internal auth headers
- [x] CMS client calls batch-class-info endpoint correctly
- [x] DI container provides clients to routes
- [x] Dashboard endpoint aggregates RAS + CMS data
- [x] Missing X-User-ID returns 401 AUTHENTICATION_ERROR
- [x] Unit tests pass with respx mocking (19/19)
- [x] `pdm run typecheck-all` passes
- [x] **Functional tests validated against docker-compose stack** (4/4 passed)

## Validation Commands

```bash
# Unit tests (validated)
pdm run typecheck-all  # Success: no issues found in 1433 source files
pdm run pytest-root services/bff_teacher_service/tests/ -v  # 19 passed

# Functional tests (requires docker-compose)
pdm run dev-start
pdm run pytest-root tests/functional/test_bff_teacher_dashboard_functional.py -v -m functional
```

## Related

- Programme Hub: `TASKS/programs/teacher_dashboard_integration/HUB.md`
- Blocked by: `cms-batch-class-info-internal-endpoint` ✅
- Blocks: `bff-teacher-dashboard-endpoint`
