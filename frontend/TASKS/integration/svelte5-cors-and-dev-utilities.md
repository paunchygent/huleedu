---
id: svelte5-cors-and-dev-utilities
title: Svelte 5 + Vite CORS Configuration and Development Utilities
type: task
status: proposed
priority: medium
domain: integration
service: ''
owner_team: agents
owner: ''
program: ''
created: '2025-11-08'
last_updated: '2026-02-01'
related: []
labels: []
---
## Overview

This task implements Priority 3.1 (Development Configuration) from the Frontend Readiness Checklist, specifically focusing on enhancing CORS configuration and adding development utilities optimized for Svelte 5 + Vite frontend stack.

## Background

The current backend services are configured with React-centric CORS origins and lack development-specific utilities for frontend integration. With the frontend stack being Svelte 5 + Vite, we need to:

1. Update CORS configuration to prioritize Vite development ports
2. Create environment-specific CORS patterns
3. Add mock data endpoints for frontend development
4. Implement test user token generation
5. Enhance development environment detection

## Current State Analysis

### CORS Configuration

- **API Gateway**: `CORS_ORIGINS` defaults to `["http://localhost:3000", "http://localhost:3001"]` (React ports)
- **WebSocket Service**: `CORS_ORIGINS` defaults to `["http://localhost:3000"]` only
- **Comments**: Still reference "React frontend" instead of "Vue 3 + Vite"
- **Environment Detection**: Basic `ENV_TYPE` field exists but underutilized

### Development Infrastructure

- **Mock Data**: Extensive mock implementations exist for testing but no frontend-specific mock endpoints
- **Authentication**: JWT infrastructure exists but no test token generation for development
- **Environment Detection**: Limited development-specific features

## Implementation Plan

### Phase 1: Enhanced CORS Configuration (45 minutes)

#### 1.1 Update Default CORS Origins

**Files to Modify:**

- `services/api_gateway_service/config.py`
- `services/websocket_service/config.py`

**Changes:**

```python
# API Gateway Service
CORS_ORIGINS: list[str] = Field(
    default=[
        "http://localhost:5173",  # Vite dev server (primary)
        "http://localhost:4173",  # Vite preview server
        "http://localhost:3000",  # Legacy/backup port
    ],
    description="Allowed CORS origins for Svelte 5 + Vite development",
)

# WebSocket Service  
CORS_ORIGINS: list[str] = Field(
    default=[
        "http://localhost:5173",  # Vite dev server (primary)
        "http://localhost:4173",  # Vite preview server
        "http://localhost:3000",  # Legacy/backup port
    ],
    description="Allowed origins for Svelte 5 WebSocket connections",
)
```

#### 1.2 Environment-Specific CORS Patterns

**New File:** `services/api_gateway_service/utils/cors_utils.py`

**Implementation:**

```python
def get_cors_origins_for_environment(env_type: str, custom_origins: list[str] | None = None) -> list[str]:
    """Get CORS origins based on environment type - optimized for Svelte 5 + Vite."""
    base_origins = {
        "development": [
            "http://localhost:5173",   # Vite dev server (primary)
            "http://localhost:4173",   # Vite preview server
            "http://localhost:3000",   # Backup/alternative port
            "http://localhost:8080",   # Custom dev port
        ],
        "staging": [
            "https://staging.huledu.com",
            "https://staging-app.huledu.com",
        ],
        "production": [
            "https://app.huledu.com",
            "https://huledu.com",
        ]
    }
    
    origins = base_origins.get(env_type, base_origins["development"])
    if custom_origins:
        origins.extend(custom_origins)
    
    return list(set(origins))  # Remove duplicates
```

#### 1.3 Update Configuration Comments

Update all references from "React frontend" to "Svelte 5 + Vite frontend" in:

- Configuration classes
- Documentation strings
- Code comments

### Phase 2: Development Utilities (90 minutes)

#### 2.1 Mock Data Endpoints

**New File:** `services/api_gateway_service/routers/dev_routes.py`

**Endpoints to Implement:**

```python
@router.get("/dev/mock/classes")
async def get_mock_classes() -> list[dict]:
    """Return mock class data optimized for Svelte 5 $state() runes."""

@router.get("/dev/mock/students/{class_id}")
async def get_mock_students(class_id: str) -> list[dict]:
    """Return mock student data for a specific class."""

@router.get("/dev/mock/essays/{status}")
async def get_mock_essays_by_status(status: str) -> list[dict]:
    """Return mock essays filtered by processing status."""

@router.get("/dev/mock/batches")
async def get_mock_batches() -> list[dict]:
    """Return mock batch processing data with various states."""

@router.get("/dev/mock/reactive-state")
async def get_mock_reactive_state() -> dict:
    """Return mock state data structured for Svelte 5 reactive patterns."""

@router.post("/dev/mock/websocket/trigger")
async def trigger_mock_notification(
    notification_type: str,
    payload: dict = None
) -> dict:
    """Trigger WebSocket notifications optimized for Svelte 5 reactive updates."""
```

**Mock Data Structure:**

- Align with existing Pydantic models
- Optimize for Svelte 5 runes (`$state()`, `$derived()`, `$effect()`)
- Include realistic data variations for different UI states
- Support batch processing states and transitions

#### 2.2 Test User Token Generation

**Endpoint:** `/dev/auth/test-token`

**Implementation:**

```python
@router.post("/dev/auth/test-token")
async def generate_test_token(
    user_type: Literal["teacher", "student", "admin"] = "teacher",
    class_id: str | None = None,
    expires_minutes: int = 60,
    custom_claims: dict | None = None
) -> dict:
    """Generate a test JWT token for development with configurable claims."""
```

**Features:**

- Support different user types (teacher, student, admin)
- Configurable expiration times
- Optional class association
- Custom claims for testing specific scenarios
- Integration with existing JWT validation middleware

#### 2.3 Development Environment Detection

**Enhancements:**

```python
def is_development_environment() -> bool:
    """Check if running in development environment."""
    return settings.ENV_TYPE.lower() in ["development", "dev", "local"]

@app.middleware("http")
async def development_middleware(request: Request, call_next):
    """Add development-specific headers and features."""
    if is_development_environment():
        response = await call_next(request)
        response.headers["X-HuleEdu-Environment"] = "development"
        response.headers["X-HuleEdu-Dev-Mode"] = "enabled"
        response.headers["X-HuleEdu-CORS-Origins"] = ",".join(settings.CORS_ORIGINS)
        return response
    return await call_next(request)
```

**Development-Only Features:**

- Debug headers for troubleshooting
- Enhanced error responses with stack traces
- Development route registration conditional on environment
- CORS origin information in response headers

### Phase 3: Integration and Testing (30 minutes)

#### 3.1 Route Registration

Update `services/api_gateway_service/app/main.py`:

```python
# Development routes (only in development environment)
if is_development_environment():
    from .routers import dev_routes
    app.include_router(dev_routes.router, prefix="/dev", tags=["Development"])
```

#### 3.2 Testing Strategy

1. **CORS Testing**: Verify Vite dev server (5173) can connect without CORS errors
2. **Mock Endpoints**: Test all mock endpoints return valid data matching API schemas
3. **Token Generation**: Verify generated tokens work with existing authentication middleware
4. **Environment Detection**: Test development features are only available in dev mode
5. **WebSocket Mocks**: Test mock WebSocket notifications trigger properly

#### 3.3 Documentation Updates

Update the following files:

- `Documentation/guides/FRONTEND_INTEGRATION_INDEX.md` - Add new CORS ports and development utilities
- `Documentation/apis/API_REFERENCE.md` - Document new development endpoints
- `Documentation/guides/SVELTE_INTEGRATION_GUIDE.md` - Add examples using new mock endpoints
- Service READMEs - Update CORS configuration examples

## Acceptance Criteria

### CORS Configuration

- [ ] API Gateway defaults to Vite ports (5173, 4173) with React port (3000) as backup
- [ ] WebSocket Service matches API Gateway CORS configuration
- [ ] Environment-specific CORS patterns implemented and tested
- [ ] All "React" references updated to "Svelte 5 + Vite"
- [ ] CORS works with Vite dev server without manual configuration

### Development Utilities

- [ ] Mock data endpoints return realistic data matching existing API schemas
- [ ] Mock data optimized for Svelte 5 reactive patterns
- [ ] Test token generation works with different user types and claims
- [ ] Generated tokens validate correctly with existing auth middleware
- [ ] Development environment detection working correctly
- [ ] Development-only features are properly gated

### Integration

- [ ] All development routes only available in development environment
- [ ] Mock WebSocket notifications trigger correctly
- [ ] No breaking changes to existing production functionality
- [ ] All tests pass after implementation
- [ ] Documentation updated and accurate

## Success Metrics

1. **Developer Experience**: Frontend developers can start development without manual CORS configuration
2. **Mock Data Quality**: Mock endpoints provide realistic data for all major UI states
3. **Authentication Testing**: Developers can easily generate test tokens for different scenarios
4. **Environment Safety**: Development utilities are completely isolated from production
5. **Documentation Accuracy**: All references correctly reflect Svelte 5 + Vite stack

## Dependencies

- Existing JWT authentication infrastructure
- Current Pydantic model definitions
- FastAPI routing and middleware system
- Environment configuration system

## Risks and Mitigations

### Risk: Breaking Production CORS

**Mitigation**: Keep existing React port (3000) as backup, test thoroughly in staging

### Risk: Security Exposure of Development Endpoints

**Mitigation**: Strict environment detection, comprehensive testing of environment gating

### Risk: Mock Data Drift from Real API

**Mitigation**: Use existing Pydantic models, regular validation against real API schemas

## Timeline

- **Phase 1 (CORS Configuration)**: 45 minutes
- **Phase 2 (Development Utilities)**: 90 minutes  
- **Phase 3 (Integration & Testing)**: 30 minutes
- **Total Estimated Time**: 2 hours 45 minutes

## Implementation Order

1. Update CORS configuration and test with Vite
2. Create environment-specific CORS utilities
3. Implement mock data endpoints
4. Add test token generation
5. Enhance development environment detection
6. Integrate development routes with environment gating
7. Update documentation
8. Comprehensive testing

This task directly supports Priority 3.1 of the Frontend Readiness Checklist and provides the foundation for enhanced developer experience with the Svelte 5 + Vite frontend stack.
