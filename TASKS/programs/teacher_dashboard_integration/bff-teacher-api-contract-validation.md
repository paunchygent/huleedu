---
id: 'bff-teacher-api-contract-validation'
title: 'BFF Teacher API Contract Validation'
type: 'task'
status: 'in_progress'
priority: 'medium'
domain: 'programs'
service: 'bff_teacher_service'
owner_team: 'agents'
owner: ''
program: 'teacher_dashboard_integration'
created: '2025-12-09'
last_updated: '2025-12-10'
related: ["TASKS/programs/teacher_dashboard_integration/HUB.md", "bff-teacher-dashboard-endpoint"]
labels: ["openapi", "contract-testing", "typescript"]
---
# BFF Teacher API Contract Validation

## Objective

Validate and export API contracts for the BFF Teacher Service to ensure frontend integration readiness.

**Blocked by**: `bff-teacher-dashboard-endpoint` ✅ (basic implementation complete)

## Context

Before frontend development begins, we need:
- Validated OpenAPI schema
- TypeScript types for frontend
- Contract tests to prevent breaking changes
- Documentation for API consumers

## Implementation Steps

### Step 1: OpenAPI Schema Export

**Deliverable**: `docs/reference/apis/bff-teacher-openapi.json`

```bash
# Ensure BFF service is running
pdm run dev-start bff_teacher_service

# Export OpenAPI schema
curl -s http://localhost:4101/openapi.json | python3 -m json.tool > docs/reference/apis/bff-teacher-openapi.json

# Validate JSON is well-formed
python3 -c "import json; json.load(open('docs/reference/apis/bff-teacher-openapi.json'))"
```

### Step 2: TypeScript Types Generation

**Tool**: `openapi-typescript` (npm package)
**Deliverable**: `frontend/src/types/api/bff-teacher.d.ts`

```bash
# Install openapi-typescript (if not already)
cd frontend && pnpm add -D openapi-typescript

# Generate TypeScript types from OpenAPI spec
npx openapi-typescript ../docs/reference/apis/bff-teacher-openapi.json \
  -o src/types/api/bff-teacher.d.ts

# Verify types compile
pnpm run type-check
```

**Add to `frontend/package.json` scripts:**
```json
{
  "scripts": {
    "generate:types": "openapi-typescript ../docs/reference/apis/bff-teacher-openapi.json -o src/types/api/bff-teacher.d.ts"
  }
}
```

**Expected output structure:**
```typescript
// frontend/src/types/api/bff-teacher.d.ts
export interface paths {
  "/bff/v1/teacher/dashboard": {
    get: operations["get_teacher_dashboard"];
  };
}

export interface components {
  schemas: {
    TeacherDashboardResponseV1: {
      batches: components["schemas"]["TeacherBatchItemV1"][];
      total_count: number;
    };
    TeacherBatchItemV1: {
      batch_id: string;
      title: string;
      class_name: string | null;
      status: "pending_content" | "ready" | "processing" | "completed_successfully" | "completed_with_failures" | "failed" | "cancelled";
      total_essays: number;
      completed_essays: number;
      created_at: string;
    };
  };
}
```

### Step 3: Contract Tests

**File**: `services/bff_teacher_service/tests/contract/test_dto_contracts.py` (CREATE)

```python
"""Contract tests for BFF Teacher Service DTOs.

These tests validate that DTOs match the documented API contract.
Breaking changes should fail these tests.
"""

import pytest
from pydantic import ValidationError

from services.bff_teacher_service.dto.teacher_v1 import (
    TeacherBatchItemV1,
    TeacherDashboardResponseV1,
)


class TestTeacherBatchItemV1Contract:
    """Contract tests for TeacherBatchItemV1."""

    def test_required_fields(self) -> None:
        """All required fields must be present."""
        # Minimum valid payload
        item = TeacherBatchItemV1(
            batch_id="test-batch-123",
            title="Test Batch",
            class_name=None,
            status="processing",
            total_essays=10,
            completed_essays=5,
            created_at="2025-12-10T12:00:00Z",
        )
        assert item.batch_id == "test-batch-123"

    def test_status_enum_values(self) -> None:
        """Status must be valid BatchClientStatus value."""
        valid_statuses = [
            "pending_content", "ready", "processing",
            "completed_successfully", "completed_with_failures",
            "failed", "cancelled"
        ]
        for status in valid_statuses:
            item = TeacherBatchItemV1(
                batch_id="test",
                title="Test",
                class_name=None,
                status=status,
                total_essays=0,
                completed_essays=0,
                created_at="2025-12-10T12:00:00Z",
            )
            assert item.status.value == status

    def test_class_name_nullable(self) -> None:
        """class_name can be null (batch without class association)."""
        item = TeacherBatchItemV1(
            batch_id="test",
            title="Test",
            class_name=None,
            status="ready",
            total_essays=0,
            completed_essays=0,
            created_at="2025-12-10T12:00:00Z",
        )
        assert item.class_name is None


class TestTeacherDashboardResponseV1Contract:
    """Contract tests for TeacherDashboardResponseV1."""

    def test_empty_batches_valid(self) -> None:
        """Empty batches list is valid (new user)."""
        response = TeacherDashboardResponseV1(batches=[], total_count=0)
        assert response.batches == []
        assert response.total_count == 0

    def test_batches_list_type(self) -> None:
        """batches must be a list of TeacherBatchItemV1."""
        response = TeacherDashboardResponseV1(
            batches=[
                TeacherBatchItemV1(
                    batch_id="test",
                    title="Test",
                    class_name="Class A",
                    status="ready",
                    total_essays=5,
                    completed_essays=0,
                    created_at="2025-12-10T12:00:00Z",
                )
            ],
            total_count=1,
        )
        assert len(response.batches) == 1
        assert isinstance(response.batches[0], TeacherBatchItemV1)
```

### Step 4: Service README Update

**File**: `services/bff_teacher_service/README.md` (CREATE/UPDATE)

```markdown
# BFF Teacher Service

Backend-for-Frontend service for the Teacher Dashboard.

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/healthz` | Health check |
| GET | `/bff/v1/teacher/dashboard` | Teacher dashboard data |

## Authentication

All `/bff/v1/*` endpoints require `X-User-ID` header (injected by API Gateway from JWT).

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `BFF_TEACHER_SERVICE_PORT` | 4101 | HTTP server port |
| `BFF_TEACHER_SERVICE_RAS_URL` | `http://result_aggregator_service:4003` | RAS base URL |
| `BFF_TEACHER_SERVICE_CMS_URL` | `http://class_management_service:5002` | CMS base URL |
| `HULEEDU_INTERNAL_API_KEY` | - | Internal service auth key |

## Running Locally

```bash
pdm run dev-start bff_teacher_service
curl http://localhost:4101/healthz
```

## Tests

```bash
pdm run pytest-root services/bff_teacher_service/tests/ -v
```

## TypeScript Types

Generated types available at `frontend/src/types/api/bff-teacher.d.ts`.

Regenerate after API changes:
```bash
cd frontend && pnpm run generate:types
```
```

### Step 5: Correlation ID Validation

Already validated in functional tests (`test_dashboard_returns_correlation_id`). Document in README.

## PDM Script for Type Generation

Add to root `pyproject.toml`:

```toml
[tool.pdm.scripts]
bff-openapi = "bash -c 'curl -s http://localhost:4101/openapi.json > docs/reference/apis/bff-teacher-openapi.json'"
bff-types = "bash -c 'cd frontend && pnpm exec openapi-typescript ../docs/reference/apis/bff-teacher-openapi.json -o src/types/api/bff-teacher.d.ts'"
```

## Success Criteria

- [ ] OpenAPI schema exported to `docs/reference/apis/bff-teacher-openapi.json`
- [ ] TypeScript types generated to `frontend/src/types/api/bff-teacher.d.ts`
- [ ] Contract tests validate all DTOs (5+ tests)
- [ ] README documents all endpoints and env vars
- [x] Correlation ID propagates correctly (validated in functional tests)
- [ ] Frontend team can consume types (verify with `pnpm run type-check`)

## Related

- Programme Hub: `TASKS/programs/teacher_dashboard_integration/HUB.md`
- Blocked by: `bff-teacher-dashboard-endpoint` ✅
- Frontend plan: `frontend/TASKS/integration/bff-service-implementation-plan.md`
