---
id: ARCH-001
title: "Health Check Dependency Injection Refactoring"
author: "Claude Code Assistant"
status: "Completed"
created_date: "2025-07-21"
updated_date: "2025-07-21"
---

# ARCH-001: Health Check Dependency Injection Refactoring

## Executive Summary

Refactor health check endpoints across 4 services to use dependency injection (DI) for Settings instead of singleton imports or hardcoded values. This aligns with the architectural pattern used by the majority of services (6 out of 10) and improves testability.

## Background

### Current State Analysis
- **6 services use DI**: Batch Orchestrator, LLM Provider, File Service, Essay Lifecycle, Class Management, Result Aggregator
- **4 services need refactoring**: Content Service (singleton), Spellchecker (hardcoded), CJ Assessment (hardcoded), API Gateway (hardcoded)
- **WebSocket Service**: Already fixed in previous session

### Architecture Validation
- `DatabaseHealthChecker` and `HuleEduApp` are fully compatible with DI patterns
- No circular dependencies or breaking changes expected
- Pattern already proven in production services

## Implementation Plan

### Phase 1: Content Service Refactoring

#### 1.1 Add Settings to DI Provider
**File**: `services/content_service/di.py`

```python
from services.content_service.config import Settings, settings

class ContentServiceProvider(Provider):
    # ... existing code ...
    
    @provide(scope=Scope.APP)
    def provide_settings(self) -> Settings:
        """Provide service settings."""
        return settings
```

#### 1.2 Update Health Routes
**File**: `services/content_service/api/health_routes.py`

```python
# Change import
from services.content_service.config import Settings  # Remove singleton import

# Update health check function
@health_bp.route("/healthz")
@inject
async def health_check(settings: FromDishka[Settings]) -> Response | tuple[Response, int]:
    """Standardized health check endpoint with storage validation."""
    try:
        # ... existing code ...
        store_path = settings.CONTENT_STORE_ROOT_PATH  # Now uses injected settings
        # ... rest of implementation
```

#### 1.3 Create Health Check Tests
**File**: `services/content_service/tests/test_health_routes.py` (new)

```python
"""Tests for Content Service health check endpoints."""

import pytest
from dishka import make_container
from quart import Quart
from quart.testing import QuartClient

from services.content_service.config import Settings
from services.content_service.di import ContentServiceProvider

class TestHealthRoutes:
    """Test suite for health check endpoints."""
    
    @pytest.fixture
    def test_settings(self) -> Settings:
        """Create test settings."""
        return Settings(
            SERVICE_NAME="content_service",
            CONTENT_STORE_ROOT_PATH="/tmp/test_content",
        )
    
    @pytest.fixture
    def test_app(self, test_settings: Settings) -> Quart:
        """Create test application with DI container."""
        app = Quart(__name__)
        
        # Override settings provider
        provider = ContentServiceProvider()
        provider.provide_settings = lambda: test_settings
        
        container = make_container(provider)
        # ... setup app with container
        
        return app
    
    async def test_health_check_returns_correct_service_name(
        self, test_app: Quart
    ) -> None:
        """Test that health check returns correct service name from settings."""
        client = test_app.test_client()
        
        response = await client.get("/healthz")
        
        assert response.status_code == 200
        data = await response.get_json()
        assert data["service"] == "content_service"
```

#### 1.4 Rebuild and Test
```bash
# Rebuild service
docker compose build --no-cache content_service && docker compose up -d content_service

# Run tests
pdm run -p services/content_service test

# Verify health endpoint
curl http://localhost:8001/healthz | jq .service
```

### Phase 2: Spellchecker Service Refactoring

#### 2.1 Update Health Routes
**File**: `services/spellchecker_service/api/health_routes.py`

```python
# Add imports
from dishka import FromDishka
from services.spellchecker_service.config import Settings

# Update health check function
@health_bp.route("/healthz")
@inject
async def health_check(settings: FromDishka[Settings]) -> tuple[Response, int]:
    """Standardized health check endpoint for Spell Checker Service."""
    try:
        # ... existing database check code ...
        
        # Replace hardcoded values
        health_checker = DatabaseHealthChecker(engine, settings.SERVICE_NAME)
        
        # ... existing health check logic ...
        
        health_response = {
            "service": settings.SERVICE_NAME,  # Was: "spellchecker_service"
            "status": overall_status,
            "message": f"{settings.SERVICE_NAME} is {overall_status}",
            "version": settings.VERSION,  # Add VERSION to settings if not present
            "checks": checks,
            "dependencies": dependencies,
            "environment": settings.ENVIRONMENT.value,  # Was: "development"
        }
```

#### 2.2 Create Health Check Tests
**File**: `services/spellchecker_service/tests/test_health_routes.py` (new)

```python
"""Tests for Spellchecker Service health check endpoints."""

import pytest
from dishka import make_container
from huleedu_service_libs.quart_app import HuleEduApp
from quart.testing import QuartClient

from services.spellchecker_service.config import Settings
from services.spellchecker_service.di import SpellCheckerServiceProvider

class TestHealthRoutes:
    """Test suite for health check endpoints."""
    
    async def test_health_check_uses_injected_settings(
        self, test_app: HuleEduApp
    ) -> None:
        """Test that health check uses DI settings not singleton."""
        client = test_app.test_client()
        
        response = await client.get("/healthz")
        
        assert response.status_code == 200
        data = await response.get_json()
        assert data["service"] == "spellchecker_service"
        assert data["environment"] == "test"  # From test settings
```

#### 2.3 Rebuild and Test
```bash
# Rebuild service
docker compose build --no-cache spellchecker_service && docker compose up -d spellchecker_service

# Run tests  
pdm run -p services/spellchecker_service test

# Verify health endpoint
curl http://localhost:8002/healthz | jq .service
```

### Phase 3: CJ Assessment Service Refactoring

#### 3.1 Update Health Routes
**File**: `services/cj_assessment_service/api/health_routes.py`

```python
# Add imports
from dishka import FromDishka
from services.cj_assessment_service.config import Settings

# Update health check function
@health_bp.route("/healthz")
@inject
async def health_check(settings: FromDishka[Settings]) -> tuple[Response, int]:
    """Standardized health check endpoint for CJ Assessment Service."""
    try:
        # ... existing checks ...
        
        # Use injected settings
        health_checker = DatabaseHealthChecker(engine, settings.SERVICE_NAME)
        
        # ... existing health check logic ...
        
        health_response = {
            "service": settings.SERVICE_NAME,  # Was: "cj_assessment_service"
            "status": overall_status,
            "message": f"{settings.SERVICE_NAME} is {overall_status}",
            "version": settings.VERSION,  # Add if not present
            "checks": checks,
            "dependencies": dependencies,
            "environment": settings.ENVIRONMENT.value,  # Was: "development"
        }
```

#### 3.2 Verify Existing Tests
**File**: `services/cj_assessment_service/tests/test_health_api.py`

Ensure existing tests still pass after DI changes. Update test fixtures if needed to provide Settings through DI.

#### 3.3 Rebuild and Test
```bash
# Rebuild service
docker compose build --no-cache cj_assessment_service && docker compose up -d cj_assessment_service

# Run tests
pdm run -p services/cj_assessment_service test

# Verify health endpoint
curl http://localhost:8003/healthz | jq .service
```

### Phase 4: API Gateway Service Refactoring

#### 4.1 Update Health Routes
**File**: `services/api_gateway_service/routers/health_routes.py`

```python
# Add imports
from services.api_gateway_service.config import Settings

# Update health check function
@router.get("/healthz")
@inject
async def health_check(settings: FromDishka[Settings]) -> dict[str, str | dict]:
    """Health check endpoint following Rule 072 format."""
    try:
        # ... existing checks ...
        
        return {
            "service": settings.SERVICE_NAME,  # Was: "api_gateway_service"
            "status": overall_status,
            "message": f"{settings.SERVICE_NAME} is {overall_status}",
            "version": settings.VERSION,  # Add if not present
            "checks": checks,
            "dependencies": dependencies,
            "environment": settings.ENVIRONMENT.value,  # Was: "development"
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "service": settings.SERVICE_NAME,
            "status": "unhealthy",
            "message": "Health check failed",
            "version": settings.VERSION,
            "error": str(e),
        }
```

#### 4.2 Verify Existing Tests
**File**: `services/api_gateway_service/tests/test_health_routes.py`

Update test fixtures to ensure Settings are properly injected through DI.

#### 4.3 Rebuild and Test
```bash
# Rebuild service
docker compose build --no-cache api_gateway_service && docker compose up -d api_gateway_service

# Run tests
pdm run -p services/api_gateway_service test

# Verify health endpoint
curl http://localhost:8000/healthz | jq .service
```

### Phase 5: Integration Verification

#### 5.1 Full System Test
```bash
# Rebuild all affected services
docker compose build --no-cache content_service spellchecker_service cj_assessment_service api_gateway_service

# Start all services
docker compose up -d

# Wait for services to be ready
sleep 10

# Verify all health endpoints
for port in 8000 8001 8002 8003; do
    echo "Testing service on port $port:"
    curl -s http://localhost:$port/healthz | jq '{service: .service, status: .status}'
done
```

#### 5.2 Environment Variable Isolation Test
```bash
# Set conflicting environment variable
export SERVICE_NAME="wrong_service_name"

# Run tests - should still use DI settings
pdm run test-all

# Health checks should still return correct service names
```

## Success Criteria

1. ✅ All 4 services use DI for Settings in health endpoints
2. ✅ No singleton imports in health route files
3. ✅ All health tests pass
4. ✅ Services report correct names regardless of environment variables
5. ✅ Docker builds succeed without errors
6. ✅ Integration tests confirm proper isolation

## Rollback Plan

If issues arise:
1. Revert health route changes
2. Keep DI provider changes (they're additive and safe)
3. Debug specific service issues individually

## Notes

- This refactoring improves consistency across the codebase
- Makes services more testable and less prone to environment conflicts
- Follows established patterns from majority of services
- No breaking changes to external APIs or contracts

## Completion Report (2025-07-21)

### Summary
Task completed successfully with the following results:

1. **Services Refactored**: 3 out of 4 target services
   - ✅ Content Service: Successfully refactored to use DI for Settings in health endpoint
   - ✅ Spellchecker Service: Successfully refactored to use DI for Settings in health endpoint
   - ✅ CJ Assessment Service: Successfully refactored to use DI for Settings in health endpoint
   - ℹ️  API Gateway Service: Analysis revealed it already uses DI patterns correctly (no changes needed)

2. **All Success Criteria Met**:
   - ✅ 3 services now use DI for Settings in health endpoints (4th already compliant)
   - ✅ No singleton imports remain in health route files
   - ✅ All health tests pass
   - ✅ Services report correct names regardless of environment variables
   - ✅ Docker builds succeed without errors
   - ✅ Integration tests confirm proper isolation

3. **Verification Results**:
   - All services running and healthy
   - Health endpoints return correct service names from injected settings
   - Environment variable isolation test passed (tests run successfully with wrong SERVICE_NAME)
   - No breaking changes to external APIs

### No Issues Encountered
The refactoring was completed smoothly with no unexpected issues or complications.