# Database Metrics Library

Comprehensive PostgreSQL database observability library for HuleEdu services.

## Overview

This library provides standardized database metrics collection, connection monitoring, query performance tracking, and health checks that integrate seamlessly with existing HuleEdu service patterns.

## Key Features

- **Protocol-First Design**: Uses `DatabaseMetricsProtocol` for flexible implementations
- **Zero Performance Impact**: Async-safe event listeners and context managers
- **Prometheus Integration**: Follows established HuleEdu metrics patterns
- **Connection Pool Monitoring**: Real-time tracking of SQLAlchemy pool status
- **Query Performance Tracking**: Decorators and context managers for operation timing
- **Health Checks**: Comprehensive database health verification
- **Repository Integration**: Seamless integration with existing repository patterns

## Architecture

```
huleedu_service_libs/database/
├── __init__.py                    # Public API exports
├── metrics.py                     # Core database metrics classes  
├── connection_monitoring.py       # SQLAlchemy event listeners for connection pool
├── query_monitoring.py            # Query performance tracking decorators/context managers
├── health_checks.py              # Database health check utilities
└── middleware.py                 # Integration middleware for repository pattern
```

## Usage Examples

### Basic Setup

```python
from huleedu_service_libs.database import setup_database_monitoring
from sqlalchemy.ext.asyncio import create_async_engine

# Setup database monitoring for a service
engine = create_async_engine(settings.DATABASE_URL)
db_metrics = setup_database_monitoring(engine, service_name="content_service")

# Get metrics dictionary for service integration
metrics_dict = db_metrics.get_metrics()
```

### Repository Integration

```python
from huleedu_service_libs.database import query_performance_tracker

class ContentRepositoryImpl:
    def __init__(self, db_infrastructure, metrics):
        self.db_infrastructure = db_infrastructure
        self.metrics = metrics
    
    @query_performance_tracker(metrics, "select", "content", "get_content_by_id")
    async def get_content_by_id(self, content_id: str) -> dict | None:
        async with self.db_infrastructure.session() as session:
            result = await session.execute(
                select(Content).where(Content.id == content_id)
            )
            return result.scalar_one_or_none()
```

### Context Manager Usage

```python
from huleedu_service_libs.database import QueryPerformanceTracker

# In your repository implementation
tracker = QueryPerformanceTracker(metrics, "content_service")

async def create_content(self, content_data: dict) -> dict:
    async with tracker.track_transaction("create_content"):
        async with self.db_infrastructure.session() as session:
            async with tracker.track_query("insert", "content", "create new content"):
                content = Content(**content_data)
                session.add(content)
                await session.commit()
                return content_data
```

### Health Checks Integration

```python
from huleedu_service_libs.database import DatabaseHealthChecker

# In your health route
health_checker = DatabaseHealthChecker(engine, "content_service")

@content_bp.get("/healthz")
async def health_check():
    db_health = await health_checker.get_health_summary()
    
    if db_health["status"] == "healthy":
        return {"status": "healthy", "database": db_health}
    else:
        return {"status": "unhealthy", "database": db_health}, 503
```

### Service Provider Integration (Dishka)

```python
# di.py
from dishka import Provider, Scope, provide
from huleedu_service_libs.database import setup_database_monitoring

class ContentServiceProvider(Provider):
    @provide(scope=Scope.APP)
    def provide_database_metrics(
        self, 
        engine: AsyncEngine,
        settings: Settings
    ) -> DatabaseMetrics:
        return setup_database_monitoring(engine, settings.SERVICE_NAME)
    
    @provide(scope=Scope.APP) 
    def provide_repository(
        self,
        db_infrastructure: DatabaseInfrastructure,
        metrics: DatabaseMetrics
    ) -> ContentRepositoryProtocol:
        return ContentRepositoryImpl(db_infrastructure, metrics)
```

## Metrics Collected

### Connection Pool Metrics
- `{service}_database_connections_active`: Active connections
- `{service}_database_connections_idle`: Idle connections  
- `{service}_database_connections_total`: Total pool size
- `{service}_database_connections_overflow`: Overflow connections
- `{service}_database_connections_acquired_total`: Connection acquisitions
- `{service}_database_connections_released_total`: Connection releases

### Query Performance Metrics
- `{service}_database_query_duration_seconds`: Query execution time histogram
- `{service}_database_transaction_duration_seconds`: Transaction time histogram
- `{service}_database_transactions_total`: Transaction counter

### Error Tracking
- `{service}_database_errors_total`: Database error counter

## Integration Patterns

### Existing Repository Pattern Enhancement

For services with existing repository implementations, use the middleware:

```python
from huleedu_service_libs.database import create_repository_middleware

# Enhance existing repository with metrics
middleware = create_repository_middleware(engine, db_metrics)

@middleware.repository_method_tracker("select", "batches", "get_batch_by_id")
async def get_batch_by_id(self, batch_id: str):
    # Your existing implementation
    pass
```

### Database Infrastructure Enhancement

```python
from huleedu_service_libs.database import create_infrastructure_enhancer

# Enhance existing database infrastructure
enhancer = create_infrastructure_enhancer(db_metrics)
enhanced_session = enhancer.enhance_session_factory(
    self.async_session_maker,
    "batch_operations"
)
```

## Health Check Endpoints

### Quick Health Summary
```python
# GET /healthz
{
  "service": "content_service",
  "status": "healthy",
  "connectivity": true,
  "response_time_seconds": 0.002,
  "pool_utilization_percent": 25.0,
  "active_connections": 2,
  "timestamp": 1701234567.89
}
```

### Comprehensive Health Check
```python
# GET /health/detailed
{
  "service": "content_service", 
  "overall_status": "healthy",
  "checks": {
    "connectivity": {
      "status": "healthy",
      "connectivity": true,
      "response_time_seconds": 0.002
    },
    "connection_pool": {
      "status": "healthy",
      "pool_size": 10,
      "active_connections": 2,
      "utilization_percent": 20.0
    },
    "query_performance": {
      "status": "healthy", 
      "simple_query_time_seconds": 0.001,
      "complex_query_time_seconds": 0.015
    },
    "database_resources": {
      "status": "healthy",
      "active_connections": 5,
      "database_size": "45 MB"
    }
  }
}
```

## Testing

The library includes comprehensive test coverage demonstrating proper usage patterns:

```bash
pdm run pytest libs/huleedu_service_libs/src/huleedu_service_libs/database/tests/ -v
```

## Design Principles

1. **Protocol-First**: All dependencies use `DatabaseMetricsProtocol`
2. **Zero Disruption**: Backward-compatible with existing implementations
3. **Async-Safe**: All operations designed for async SQLAlchemy
4. **Error Resilient**: Graceful handling of metrics collection failures
5. **Performance Conscious**: Minimal overhead on database operations
6. **HuleEdu Compliant**: Follows established service patterns and conventions