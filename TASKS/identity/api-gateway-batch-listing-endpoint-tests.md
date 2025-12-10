---
id: 'api-gateway-batch-listing-endpoint-tests'
title: 'API Gateway batch listing endpoint tests'
type: 'task'
status: 'completed'
priority: 'medium'
domain: 'identity'
service: 'api_gateway_service'
owner_team: 'agents'
owner: ''
program: ''
created: '2025-12-10'
last_updated: '2025-12-10'
related: ["TASKS/architecture/bff-pattern-adoption-and-rollout-plan.md"]
labels: ['api-gateway', 'testing']
---
# API Gateway batch listing endpoint tests

## Objective

Create comprehensive test coverage for the `GET /v1/batches` endpoint in API Gateway.

## Context

The `GET /v1/batches` endpoint was implemented on 2025-12-08 as part of the batch routes refactor (see handoff.md). The endpoint:
- Lists paginated batches owned by authenticated user
- Supports pagination (`limit`, `offset`) and status filtering
- Maps internal RAS statuses to client-facing statuses
- Proxies to RAS `/internal/v1/batches/user/{user_id}` with internal auth headers

Implementation exists in `services/api_gateway_service/routers/batch_queries.py` (168 LoC) but had zero test coverage.

## Implementation

**Test file created**: `services/api_gateway_service/tests/test_batch_queries.py` (393 LoC, 28 tests)

**Pattern**: Follows `test_status_routes.py` (Dishka DI, respx mock, AsyncClient)

**Test coverage**:

| Category | Tests | Description |
|----------|-------|-------------|
| Success path | 2 | Empty list, multiple batches |
| Pagination | 2 | Params forwarding, metadata response |
| Status filtering | 8 | 7 valid client→internal mappings, 1 invalid filter |
| Status mapping | 12 | All internal→client status transformations |
| Response cleanup | 1 | `user_id` removal from batch objects |
| Auth headers | 1 | `X-Internal-API-Key`, `X-Service-ID`, `X-Correlation-ID` |
| Error handling | 2 | RAS 500/503 → gateway 502 |

**Validation**:
- `pdm run typecheck-all`: Pass
- `pdm run pytest-root services/api_gateway_service/tests/test_batch_queries.py -v`: 28/28 pass
- No `@patch` usage (DI compliant per Rule 075)
- `pdm run format-all` + `pdm run lint-fix --unsafe-fixes`: Applied

## Success Criteria

- [x] Test file created following `test_status_routes.py` pattern
- [x] All test categories covered (success, pagination, filtering, mapping, auth, errors)
- [x] File <500 LoC (393 LoC)
- [x] typecheck-all passes
- [x] All tests pass (28/28)
- [x] No @patch usage (DI compliant)

## Key Files

- `services/api_gateway_service/routers/batch_queries.py` - Implementation (168 LoC)
- `services/api_gateway_service/routers/_batch_utils.py` - Status mapping, models
- `services/api_gateway_service/tests/test_batch_queries.py` - Tests (393 LoC)
- `services/api_gateway_service/tests/test_status_routes.py` - Pattern reference
