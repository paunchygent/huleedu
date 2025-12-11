---
id: "073-health-endpoint-implementation"
type: "implementation"
created: 2025-07-07
last_updated: 2025-11-17
scope: "backend"
---

# 073: Health Endpoint Implementation

## Requirements by Service Type

**ALL services MUST implement:**
- `/healthz` - Basic service health check
- `/metrics` - Prometheus metrics endpoint

**PostgreSQL services MUST ALSO implement:**
- `/healthz/database` - Detailed database connection health
- `/healthz/database/summary` - Database operation summary metrics

## Quart Services with PostgreSQL

```python
from huleedu_service_libs.database import DatabaseHealthChecker
from huleedu_service_libs.logging_utils import create_service_logger
from quart import Blueprint, Response, current_app, jsonify

logger = create_service_logger("service_name.api.health")
health_bp = Blueprint("health", __name__)

@health_bp.route("/healthz")
async def health_check() -> Response | tuple[Response, int]:
    """Basic service health check."""
    try:
        checks = {"service_responsive": True, "dependencies_available": True}
        dependencies = {}

        # Check database if available
        if hasattr(current_app, "database_engine"):
            health_checker = DatabaseHealthChecker(current_app.database_engine, settings.SERVICE_NAME)
            db_health = await health_checker.check_basic_connectivity()
            dependencies["database"] = db_health
            if not db_health["healthy"]:
                checks["dependencies_available"] = False

        response_data = {
            "service": settings.SERVICE_NAME,
            "environment": settings.ENVIRONMENT.value,
            "status": "healthy" if all(checks.values()) else "unhealthy",
            "checks": checks,
            "dependencies": dependencies,
        }

        status_code = 200 if all(checks.values()) else 503
        return jsonify(response_data), status_code

    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return jsonify({"status": "unhealthy", "error": str(e)}), 503

@health_bp.route("/healthz/database")
async def database_health() -> Response | tuple[Response, int]:
    """Detailed database health check."""
    if not hasattr(current_app, "database_engine"):
        return jsonify({"error": "No database configured"}), 404

    try:
        health_checker = DatabaseHealthChecker(current_app.database_engine, settings.SERVICE_NAME)
        health_data = await health_checker.check_detailed_health()
        status_code = 200 if health_data["healthy"] else 503
        return jsonify(health_data), status_code
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return jsonify({"healthy": False, "error": str(e)}), 503

@health_bp.route("/healthz/database/summary")
async def database_summary() -> Response | tuple[Response, int]:
    """Database summary metrics."""
    if not hasattr(current_app, "database_engine"):
        return jsonify({"error": "No database configured"}), 404

    try:
        health_checker = DatabaseHealthChecker(current_app.database_engine, settings.SERVICE_NAME)
        summary_data = await health_checker.get_summary_metrics()
        return jsonify(summary_data), 200
    except Exception as e:
        logger.error(f"Database summary failed: {e}")
        return jsonify({"error": str(e)}), 503
```

## FastAPI Services

```python
from fastapi import APIRouter
from huleedu_service_libs.database import DatabaseHealthChecker

health_router = APIRouter(prefix="/healthz", tags=["health"])

@health_router.get("/")
async def health_check():
    """Basic health check."""
    return {
        "service": settings.SERVICE_NAME,
        "status": "healthy",
        "environment": settings.ENVIRONMENT.value,
    }

@health_router.get("/database")
async def database_health():
    """Database health check."""
    # Similar pattern to Quart implementation
```

## Non-Database Services

```python
@health_bp.route("/healthz")
async def health_check() -> Response:
    """Health check for stateless services."""
    return jsonify({
        "service": settings.SERVICE_NAME,
        "environment": settings.ENVIRONMENT.value,
        "status": "healthy",
        "checks": {"service_responsive": True},
    })
```

## Metrics Endpoint

```python
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

@health_bp.route("/metrics")
async def metrics() -> Response:
    """Prometheus metrics endpoint."""
    metrics_data = generate_latest()
    return Response(metrics_data, mimetype=CONTENT_TYPE_LATEST)
```

## App Setup Requirements

```python
# app.py - Store engine for health checks
app.database_engine = engine
app.health_checker = DatabaseHealthChecker(engine, settings.SERVICE_NAME)

# Register health blueprint
app.register_blueprint(health_bp)
```

## Critical Implementation Notes

1. **Database Engine Storage**: MUST store `engine` on `app.database_engine` for health checks
2. **Error Handling**: Health checks must never crash the service
3. **Status Codes**: 200 for healthy, 503 for unhealthy
4. **Response Format**: Consistent JSON structure across all services
5. **Logging**: Log health check failures for debugging
