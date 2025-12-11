---
type: decision
id: ADR-0007
status: proposed
created: 2025-11-27
last_updated: 2025-11-27
---

# ADR-0007: BFF vs API Gateway Pattern

## Status
Proposed

## Context
The HuleEdu platform is transitioning from a backend-only system to supporting client-facing dashboards for teachers and administrators. This requires a strategy for exposing backend services to frontend clients while maintaining clean architectural boundaries.

### Current Architecture
- **Event-driven microservices**: RAS, CMS, Content, File, Identity, WebSocket services
- **API Gateway**: Handles authentication, rate limiting, and CORS for external clients
- **Backend contracts**: Internal services use service-to-service authentication and fine-grained APIs
- **Frontend needs**: Screen-specific DTOs tailored to Vue 3 components with minimal round-trips

### Key Requirements
1. **Role-specific views**: Teacher and admin dashboards require different data aggregations
2. **Screen-optimized responses**: Avoid multiple client-side API calls per screen
3. **Security boundaries**: Clear separation between teacher and admin capabilities
4. **Type safety**: Support OpenAPI → TypeScript generation for frontend developers
5. **Real-time updates**: Integration with WebSocket service for batch progress notifications
6. **Independent evolution**: Frontend and backend services must evolve at different paces

### Architectural Patterns Considered
The platform must choose between:
- **API Gateway pattern**: Gateway aggregates multiple services and exposes unified API
- **BFF (Backend-for-Frontend) pattern**: Dedicated backend services per frontend type
- **Hybrid approach**: BFF services behind an API Gateway

## Decision
Implement **per-role BFF services behind API Gateway** with the following architecture:

### 1. Service Topology
Create dedicated BFF services for each role:
- `bff_teacher_service`: Teacher-facing endpoints and DTOs
- `bff_admin_service`: Admin-facing endpoints and DTOs (future)

**Rationale**: Separate services provide clear security boundaries, independent scaling, and avoid monolithic multi-role complexity.

### 2. API Gateway Responsibilities
API Gateway handles cross-cutting concerns:
- JWT authentication and token validation
- Rate limiting per user/organization
- CORS configuration for production origins
- Request routing to appropriate BFF service
- Transparent request/response forwarding for `/bff/v1/...` routes

**Implementation**:
```python
# API Gateway routing
@gateway.route("/bff/v1/teacher/<path:subpath>", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy_to_teacher_bff(subpath: str):
    """Forward authenticated requests to teacher BFF."""
    # Gateway validates JWT and adds user context headers
    # BFF trusts Gateway-validated requests
    return await forward_to_service(
        service="bff_teacher",
        path=f"/bff/v1/teacher/{subpath}",
        headers=inject_user_context(request.headers)
    )
```

### 3. BFF Service Responsibilities
Each BFF service provides:
- **Screen-specific DTOs**: `TeacherClassDashboardV1`, `TeacherBatchDetailV1`, etc.
- **Backend aggregation**: Compose data from RAS, CMS, Content, File services
- **Authorization enforcement**: Ensure teachers only access their own batches/classes
- **Real-time integration**: Publish view-model events to Redis for WebSocket service

**BFF Service Structure**:
```
services/bff_teacher_service/
  app.py                    # FastAPI app (CORS, tracing, error handling, DI)
  config.py                 # Pydantic settings (downstream URLs, Redis)
  di.py                     # Dishka providers for HTTP clients, Redis
  api/v1/
    teacher_routes.py       # /bff/v1/teacher/dashboard, etc.
  dto/
    teacher_v1.py           # TeacherClassDashboardV1, TeacherBatchDetailV1
  clients/
    ras_client.py           # HTTP client for RAS internal endpoints
    cms_client.py           # HTTP client for CMS
    content_client.py       # HTTP client for Content Service
  streaming/
    view_events.py          # Optional view-model event publishing
  tests/
    test_dashboard.py       # Screen-specific tests
```

### 4. Request Flow
**Production Flow**:
```
Vue SPA
  ↓ GET /bff/v1/teacher/dashboard + JWT
API Gateway
  ↓ Validate JWT, extract user_id, add X-User-ID header
BFF Teacher Service
  ↓ Call RAS: GET /internal/v1/batches/user/{user_id}
  ↓ Call CMS: GET /v1/classes?owner_id={user_id}
  ↓ Compose TeacherClassDashboardV1 DTO
  ↓ Return JSON
API Gateway
  ↓ Forward response
Vue SPA
  ↓ Render dashboard
```

**Development Flow** (optional):
- Vue SPA may call BFF directly (bypass Gateway)
- BFF validates JWT using shared libraries
- BFF configures CORS for dev origins

### 5. Backend Composition Pattern
BFFs aggregate data from multiple services:

**Prefer RAS for read-optimized queries**:
- Dashboard: `GET /internal/v1/batches/user/{user_id}` (RAS)
- Batch detail: `GET /internal/v1/batches/{batch_id}/status` (RAS)
- Enrich with CMS when needed (class names, student associations)

**Parallel HTTP calls**:
```python
async def get_teacher_dashboard(user_id: str) -> TeacherClassDashboardV1:
    """Compose dashboard from RAS + CMS."""
    # Parallel fetch
    batches, classes = await asyncio.gather(
        self.ras_client.get_user_batches(user_id),
        self.cms_client.get_user_classes(user_id)
    )

    # Enrich batches with class names
    class_map = {c.class_id: c.name for c in classes}
    for batch in batches:
        batch.class_name = class_map.get(batch.class_id, "Unknown")

    return TeacherClassDashboardV1(batches=batches, total_count=len(batches))
```

### 5a. BFF Feature Scope

| Feature Area             | BFF Role                 | Backend Service   |
|--------------------------|--------------------------|-------------------|
| Dashboard (batch list)   | Aggregates RAS + CMS     | RAS, CMS          |
| Batch Detail             | Aggregates RAS + Content | RAS, Content      |
| Class/Student Management | Proxy to CMS             | CMS               |
| Batch CRUD               | Proxy to BOS             | BOS               |
| Essay Management         | Proxy to ELS/File        | ELS, File Service |
| Statistics               | Aggregates RAS           | RAS               |
| AI Feedback              | Aggregates RAS + Content | RAS, Content      |

### 5b. Write Path Decision

**Decision**: BFF proxies writes to backend services via Gateway patterns.

- **Reads**: BFF aggregates from multiple services (primary responsibility)
- **Writes**: BFF forwards to appropriate backend, Gateway handles command publishing
- **Rationale**: Keeps BFF focused on read optimization; avoids duplicating write logic

**Write Flow**:
1. Vue → Gateway → BOS/ELS (writes)
2. Vue → Gateway → BFF → RAS/CMS (reads)

### 6. Versioning Strategy
- **URL path versioning**: `/bff/v1/teacher/...`
- **DTO version suffixes**: `TeacherClassDashboardV1`, `V2`, etc.
- **Non-breaking additions**: Stay within `v1`
- **Breaking changes**: Introduce `/bff/v2/...` with new DTOs

### 7. Real-Time Updates
**WebSocket Backplane**:
- BFF may publish view-model events to Redis on state changes
- WebSocket service broadcasts to connected clients
- Vue app updates query caches or invalidates queries

**Example**:
```python
# BFF publishes batch update event
await self.redis_pubsub.publish_user_notification(
    user_id=batch.user_id,
    event_type="BATCH_UPDATED",
    payload={"batch_id": batch_id, "new_status": "COMPLETED"}
)
```

## Consequences

### Positive
- **Clean separation of concerns**: Gateway handles auth/rate-limiting, BFF handles aggregation
- **Role-based security**: Per-role BFFs prevent cross-role data leakage
- **Independent scaling**: Scale teacher and admin BFFs independently based on traffic
- **Type-safe contracts**: OpenAPI → TypeScript generation per BFF service
- **Frontend velocity**: Screen-specific DTOs eliminate client-side composition complexity
- **Backend protection**: Gateway shields backend services from direct client access
- **Flexible composition**: BFFs can aggregate from multiple services without frontend awareness
- **Clear ownership**: Each BFF owns its DTOs and frontend contract

### Negative
- **Additional services**: More operational overhead (2+ BFF services vs 1 Gateway)
- **HTTP hop overhead**: One extra network hop (Client → Gateway → BFF → Backend)
- **Data duplication risk**: BFFs may cache or duplicate data from RAS
- **Coordination complexity**: Changes requiring BFF + backend alignment need careful sequencing
- **Testing surface**: Contract tests needed for BFF ↔ Backend interactions

## Alternatives Considered

1. **API Gateway Only**: Gateway aggregates services directly without BFFs
   - Rejected: Gateway becomes monolithic, mixing auth/rate-limiting with business logic
   - Violates single responsibility principle
   - Difficult to maintain role-specific views in single codebase

2. **Direct Backend Access**: Frontend calls RAS, CMS, etc. directly
   - Rejected: Chatty client-side API calls, no aggregation layer
   - Frontend must understand backend service boundaries
   - Difficult to optimize queries or provide screen-specific responses

3. **Monolithic BFF**: Single BFF service for all roles
   - Rejected: Complex authorization logic, unclear ownership
   - Single point of failure for all frontend traffic
   - Difficult to scale independently per role

4. **GraphQL Gateway**: Use GraphQL for flexible client queries
   - Deferred: Adds complexity, team lacks GraphQL expertise
   - REST + BFF pattern proven and well-understood
   - Can reconsider for future iterations if query flexibility becomes critical

5. **Server-Side Rendering**: Vue SSR with server-side aggregation
   - Rejected: Scope is SPA dashboards, not marketing pages
   - SSR adds deployment complexity without clear benefit
   - Real-time updates favor client-side rendering

## Related ADRs
- ADR-0003: Multi-Tenancy Data Isolation Strategy (tenant_id propagation through BFF)

## References
- docs/architecture/bff-frontend-integration.md (normative BFF architecture)
- docs/research/bff-vue-3-frontend-integration-design.md (design research)
- TASKS/frontend/bff-service-implementation-plan.md (implementation plan)
- .agent/rules/020.10-api-gateway-service.md (Gateway patterns)
- .agent/rules/020.12-result-aggregator-service-architecture.md (RAS integration)
