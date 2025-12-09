---
id: 'cms-batch-class-info-internal-endpoint'
title: 'CMS Batch Class Info Internal Endpoint'
type: 'task'
status: 'completed'
priority: 'critical'
domain: 'programs'
service: 'class_management_service'
owner_team: 'agents'
owner: ''
program: 'teacher_dashboard_integration'
created: '2025-12-09'
last_updated: '2025-12-09'
related: ["TASKS/programs/teacher_dashboard_integration/HUB.md"]
labels: ["blocking", "cms", "internal-api"]
---
# CMS Batch Class Info Internal Endpoint

## Objective

Add `GET /internal/v1/batches/class-info` endpoint to CMS that returns batch→class mapping by querying the `EssayStudentAssociation` table.

**COMPLETED**: Endpoint implemented and tested (2025-12-09).

## Context

The BFF Teacher Dashboard needs to display class names alongside batches. The batch→class relationship exists in CMS via `EssayStudentAssociation` (not via RAS `assignment_id`, which links to assessment instructions).

**Domain Model**:
- RAS `BatchResult.batch_id` → unique batch identifier
- CMS `EssayStudentAssociation.batch_id` → FK to RAS batch
- CMS `EssayStudentAssociation.class_id` → FK to class
- CMS `UserClass.id` → class with name

**Note**: Batches can legitimately exist without class associations (valid state, return `null`).

## Plan

### 1. Update Protocol
**File**: `services/class_management_service/protocols.py`

Add to `ClassManagementServiceProtocol`:
```python
async def get_class_info_for_batches(
    self, batch_ids: list[UUID]
) -> dict[str, dict[str, str] | None]:
    """Get class info for multiple batches via EssayStudentAssociation."""
    ...
```

### 2. Implement Service Method
**File**: `services/class_management_service/implementations/class_management_service_impl.py`

```python
async def get_class_info_for_batches(
    self, batch_ids: list[uuid.UUID]
) -> dict[str, dict[str, str] | None]:
    result: dict[str, dict[str, str] | None] = {}
    for batch_id in batch_ids:
        associations = await self.repo.get_batch_student_associations(batch_id)
        if not associations:
            result[str(batch_id)] = None
            continue
        class_id = associations[0].class_id
        user_class = await self.get_class_by_id(class_id)
        if user_class:
            result[str(batch_id)] = {
                "class_id": str(class_id),
                "class_name": user_class.name,
            }
        else:
            result[str(batch_id)] = None
    return result
```

### 3. Add Internal Route
**File**: `services/class_management_service/api/internal_routes.py`

```python
@bp.route("/batches/class-info", methods=["GET"])
@inject
async def get_batch_class_info(
    service: FromDishka[ClassManagementServiceProtocol],
) -> Response | tuple[Response, int]:
    """Get class info for multiple batches.

    Query params:
        batch_ids: Comma-separated list of batch UUIDs

    Returns:
        {batch_id: {class_id: str, class_name: str} | null}
    """
    api_key = request.headers.get("X-Internal-API-Key")
    if not api_key or api_key != settings.INTERNAL_API_KEY:
        return jsonify({"error": "Unauthorized"}), 401

    batch_ids_param = request.args.get("batch_ids", "")
    if not batch_ids_param:
        return jsonify({}), 200

    batch_ids = [UUID(bid.strip()) for bid in batch_ids_param.split(",") if bid.strip()]
    result = await service.get_class_info_for_batches(batch_ids)
    return jsonify(result), 200
```

### 4. Unit Tests
**File**: `services/class_management_service/tests/unit/test_batch_class_info.py` (CREATE)

Test cases:
- Returns class info for batches with associations
- Returns `null` for batches without class associations
- Handles empty batch_ids list
- Validates internal API key
- Handles invalid UUIDs gracefully

## Success Criteria

- [x] Endpoint returns correct class info for batches with associations
- [x] Returns `null` for batches without class associations (not error)
- [x] Internal API key validation works (`before_request` hook with `X-Internal-API-Key` + `X-Service-ID`)
- [x] Unit tests pass (9/9 tests in `test_batch_class_info.py`)
- [x] `pdm run typecheck-all` passes
- [x] `pdm run lint-fix --unsafe-fixes` passes

## Implementation Files

- `services/class_management_service/protocols.py` - Added `get_class_info_for_batches()` to both protocols
- `services/class_management_service/implementations/class_repository_postgres_impl.py` - Repository method with metrics
- `services/class_management_service/implementations/class_repository_mock_impl.py` - Mock implementation
- `services/class_management_service/implementations/class_management_service_impl.py` - Service method
- `services/class_management_service/api/internal_routes.py` - `before_request` auth + route handler
- `services/class_management_service/tests/unit/test_batch_class_info.py` - 9 unit tests

## Related

- Programme Hub: `TASKS/programs/teacher-dashboard-integration/HUB.md`
- Research Report: `.claude/work/reports/2025-12-09-teacher-dashboard-endpoint-implementation-plan.md`
- Downstream: `bff-teacher-service-internal-clients` (blocked by this)
