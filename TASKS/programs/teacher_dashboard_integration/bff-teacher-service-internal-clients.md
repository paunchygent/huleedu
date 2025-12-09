---
id: 'bff-teacher-service-internal-clients'
title: 'BFF Teacher Service Internal Clients'
type: 'task'
status: 'blocked'
priority: 'high'
domain: 'programs'
service: 'bff_teacher_service'
owner_team: 'agents'
owner: ''
program: 'teacher_dashboard_integration'
created: '2025-12-09'
last_updated: '2025-12-09'
related: ["TASKS/programs/teacher_dashboard_integration/HUB.md", "cms-batch-class-info-internal-endpoint"]
labels: ["bff", "http-clients", "dishka"]
---
# BFF Teacher Service Internal Clients

## Objective

Implement RAS and CMS HTTP clients for the BFF Teacher Service with Dishka DI integration.

**Blocked by**: `cms-batch-class-info-internal-endpoint`

## Context

The BFF Teacher Service needs to call backend services (RAS, CMS) to aggregate data for the dashboard. Following HuleEdu patterns:
- Protocols define client interfaces
- Implementations use `httpx.AsyncClient`
- Dishka provides DI with APP scope for clients

## Plan

### 1. Create Protocols
**File**: `services/bff_teacher_service/protocols.py` (CREATE)

```python
"""Protocol definitions for BFF Teacher Service DI."""
from typing import Protocol, Any

class RASClientProtocol(Protocol):
    async def get_batches_for_user(
        self, user_id: str, *, limit: int = 20, offset: int = 0, status: str | None = None
    ) -> list[dict[str, Any]]: ...

    async def get_batch_status(self, batch_id: str) -> dict[str, Any] | None: ...

class CMSClientProtocol(Protocol):
    async def get_batch_class_info(
        self, batch_ids: list[str]
    ) -> dict[str, dict[str, str | None]]:
        """Get class info for multiple batches."""
        ...
```

### 2. Implement RAS Client
**File**: `services/bff_teacher_service/clients/ras_client.py` (CREATE)

- Internal headers: `X-Internal-API-Key`, `X-Service-ID`
- Endpoints: `/internal/v1/batches/user/{user_id}`, `/internal/v1/batches/{batch_id}/status`

### 3. Implement CMS Client
**File**: `services/bff_teacher_service/clients/cms_client.py` (CREATE)

- Internal headers: `X-Internal-API-Key`, `X-Service-ID`
- Endpoint: `/internal/v1/batches/class-info?batch_ids=...`

### 4. Update Config
**File**: `services/bff_teacher_service/config.py` (UPDATE)

Add: `RAS_BASE_URL`, `CMS_BASE_URL`, `HTTP_CLIENT_TIMEOUT_SECONDS`

### 5. Create DI Provider
**File**: `services/bff_teacher_service/di.py` (CREATE)

Dishka provider with APP scope for HTTP client and service clients.

### 6. Unit Tests
**Files**: `tests/unit/test_ras_client.py`, `tests/unit/test_cms_client.py`

## Success Criteria

- [ ] RAS client sends internal auth headers
- [ ] CMS client calls batch-class-info endpoint correctly
- [ ] DI container provides clients to routes
- [ ] Unit tests pass with mocked HTTP
- [ ] `pdm run typecheck-all` passes

## Related

- Programme Hub: `TASKS/programs/teacher-dashboard-integration/HUB.md`
- Blocked by: `cms-batch-class-info-internal-endpoint`
- Blocks: `bff-teacher-dashboard-endpoint`
