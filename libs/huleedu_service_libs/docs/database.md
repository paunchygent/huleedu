# Database Utilities

PostgreSQL monitoring, health checks, and metrics collection for HuleEdu microservices.

## Overview

The database utilities provide comprehensive monitoring and health checking capabilities for PostgreSQL databases. Features include connection pool monitoring, query performance tracking, and Prometheus metrics integration.

## Components

### DatabaseHealthChecker

Comprehensive health monitoring for PostgreSQL databases.

```python
class DatabaseHealthChecker:
    def __init__(self, engine: AsyncEngine, service_name: str)
    
    async def check_basic_connectivity(self, timeout: float = 5.0) -> Dict[str, Any]
    async def check_connection_pool_health(self) -> Dict[str, Any]
    async def check_query_performance(self, timeout: float = 10.0) -> Dict[str, Any]
    async def check_database_resources(self) -> Dict[str, Any]
    async def comprehensive_health_check(self) -> Dict[str, Any]
    async def get_health_summary(self) -> Dict[str, Any]
```

### Health Check Response Example

```json
{
  "service": "content_service",
  "overall_status": "healthy",
  "checks": {
    "connectivity": {
      "status": "healthy",
      "response_time_seconds": 0.012
    },
    "connection_pool": {
      "status": "healthy",
      "pool_size": 10,
      "active_connections": 3,
      "utilization_percent": 30.0
    },
    "query_performance": {
      "status": "healthy",
      "simple_query_time_seconds": 0.001,
      "complex_query_time_seconds": 0.045
    },
    "database_resources": {
      "status": "healthy",
      "active_connections": 15,
      "database_size": "125 MB"
    }
  }
}
```

### Database Metrics

Prometheus metrics for database observability.

```python
# Setup database monitoring
from huleedu_service_libs.database import setup_database_monitoring

db_metrics = setup_database_monitoring(
    engine=engine,
    service_name="content_service",
    metrics_dict=existing_metrics  # Optional
)
```

### Collected Metrics

- `{service}_database_query_duration_seconds`: Query execution time histogram
- `{service}_database_connections_active`: Active connection gauge
- `{service}_database_connections_idle`: Idle connection gauge
- `{service}_database_connections_total`: Total pool size gauge
- `{service}_database_connections_overflow`: Overflow connections gauge
- `{service}_database_connections_acquired_total`: Connection acquisition counter
- `{service}_database_connections_released_total`: Connection release counter
- `{service}_database_transactions_total`: Transaction counter
- `{service}_database_transaction_duration_seconds`: Transaction duration histogram
- `{service}_database_errors_total`: Error counter by type and operation

### Query Performance Tracking

Decorator for tracking query performance.

```python
from huleedu_service_libs.database import query_performance_tracker

class ContentRepository:
    @query_performance_tracker(metrics, operation="create", table="content")
    async def create_content(self, content_data: dict) -> Content:
        # Database operation
        pass
```

## Integration Example

```python
# In startup_setup.py
async def setup_database(app: Quart, settings: Settings) -> AsyncEngine:
    engine = create_async_engine(settings.DATABASE_URL)
    
    # Setup monitoring
    db_metrics = setup_database_monitoring(engine, "content_service")
    app.extensions["db_metrics"] = db_metrics
    
    # Store health checker
    app.health_checker = DatabaseHealthChecker(engine, "content_service")
    
    return engine

# In health routes
@health_bp.route("/healthz")
async def health_check():
    health_checker = current_app.health_checker
    summary = await health_checker.get_health_summary()
    return jsonify(summary), 200 if summary["status"] == "healthy" else 503
```

## Usage Examples

### Basic Health Check Setup

```python
from huleedu_service_libs.database import DatabaseHealthChecker
from sqlalchemy.ext.asyncio import create_async_engine

# Create engine
engine = create_async_engine("postgresql+asyncpg://user:pass@localhost/db")

# Setup health checker
health_checker = DatabaseHealthChecker(engine, "my_service")

# Use in health endpoint
@app.route("/health")
async def health():
    result = await health_checker.get_health_summary()
    status_code = 200 if result["overall_status"] == "healthy" else 503
    return jsonify(result), status_code
```

### Comprehensive Monitoring Setup

```python
from huleedu_service_libs.database import setup_database_monitoring

# Setup complete monitoring
async def setup_database_monitoring_complete(engine, service_name):
    # Get metrics collection
    db_metrics = setup_database_monitoring(
        engine=engine,
        service_name=service_name
    )
    
    # Setup health checker
    health_checker = DatabaseHealthChecker(engine, service_name)
    
    return db_metrics, health_checker
```

### Repository Performance Tracking

```python
from huleedu_service_libs.database import query_performance_tracker

class UserRepository:
    def __init__(self, engine: AsyncEngine, metrics: dict):
        self.engine = engine
        self.metrics = metrics
    
    @query_performance_tracker(operation="get_user", table="users")
    async def get_user(self, user_id: str) -> User:
        async with self.engine.begin() as conn:
            result = await conn.execute(
                select(User).where(User.id == user_id)
            )
            return result.scalar_one_or_none()
    
    @query_performance_tracker(operation="create_user", table="users")
    async def create_user(self, user_data: dict) -> User:
        async with self.engine.begin() as conn:
            user = User(**user_data)
            conn.add(user)
            await conn.commit()
            return user
```

### Advanced Health Monitoring

```python
# Custom health check with business logic
class CustomHealthChecker(DatabaseHealthChecker):
    async def check_business_critical_data(self) -> Dict[str, Any]:
        """Check business-critical data integrity."""
        async with self.engine.begin() as conn:
            # Check for orphaned records
            orphaned_count = await conn.execute(
                select(func.count()).select_from(
                    select(Content).outerjoin(User, Content.user_id == User.id)
                    .where(User.id.is_(None))
                )
            )
            
            is_healthy = orphaned_count.scalar() == 0
            
            return {
                "status": "healthy" if is_healthy else "unhealthy",
                "orphaned_records": orphaned_count.scalar(),
                "description": "Business data integrity check"
            }
    
    async def comprehensive_health_check(self) -> Dict[str, Any]:
        """Override to include business checks."""
        base_checks = await super().comprehensive_health_check()
        business_check = await self.check_business_critical_data()
        
        base_checks["checks"]["business_integrity"] = business_check
        
        # Recalculate overall status
        all_healthy = all(
            check["status"] == "healthy" 
            for check in base_checks["checks"].values()
        )
        base_checks["overall_status"] = "healthy" if all_healthy else "unhealthy"
        
        return base_checks
```

## Configuration

### Engine Configuration

```python
from sqlalchemy.ext.asyncio import create_async_engine

# Recommended engine configuration
engine = create_async_engine(
    settings.DATABASE_URL,
    # Connection pool settings
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    pool_recycle=3600,
    # Query logging in development
    echo=settings.ENVIRONMENT == "development",
    # Async driver
    future=True
)
```

### Environment Variables

- `DATABASE_URL`: PostgreSQL connection string
- `DB_POOL_SIZE`: Connection pool size (default: 10)
- `DB_MAX_OVERFLOW`: Max overflow connections (default: 20)
- `DB_POOL_RECYCLE`: Pool recycle time in seconds (default: 3600)

## Testing

### Health Check Testing

```python
import pytest
from unittest.mock import AsyncMock
from huleedu_service_libs.database import DatabaseHealthChecker

@pytest.fixture
def mock_engine():
    engine = AsyncMock()
    engine.pool = AsyncMock()
    engine.pool.size.return_value = 10
    engine.pool.checked_in.return_value = 7
    engine.pool.checked_out.return_value = 3
    return engine

async def test_health_check_healthy(mock_engine):
    health_checker = DatabaseHealthChecker(mock_engine, "test_service")
    
    # Mock successful connection
    mock_engine.begin.return_value.__aenter__.return_value.execute.return_value = AsyncMock()
    
    result = await health_checker.get_health_summary()
    
    assert result["overall_status"] == "healthy"
    assert result["service"] == "test_service"
    assert "checks" in result
```

### Metrics Testing

```python
from prometheus_client import REGISTRY
from huleedu_service_libs.database import setup_database_monitoring

async def test_database_metrics_collection(mock_engine):
    # Clear existing metrics
    collectors = list(REGISTRY._collector_to_names.keys())
    for collector in collectors:
        REGISTRY.unregister(collector)
    
    # Setup monitoring
    metrics = setup_database_monitoring(mock_engine, "test_service")
    
    # Verify metrics exist
    assert "test_service_database_connections_active" in metrics
    assert "test_service_database_query_duration_seconds" in metrics
```

## Best Practices

1. **Always setup health checks**: Include database health in service health endpoints
2. **Monitor connection pools**: Track pool utilization and overflow
3. **Use performance tracking**: Instrument repository methods with decorators
4. **Set appropriate timeouts**: Configure reasonable query timeouts
5. **Monitor business metrics**: Add custom health checks for data integrity
6. **Pool configuration**: Size pools appropriately for service load
7. **Connection lifecycle**: Use async context managers for connections
8. **Error handling**: Gracefully handle database unavailability

## Anti-Patterns to Avoid

1. **Ignoring pool metrics**: Monitor connection pool health
2. **Missing health checks**: Always include database health endpoints
3. **Synchronous operations**: Use async SQLAlchemy throughout
4. **Connection leaks**: Always use context managers
5. **Hardcoded timeouts**: Make timeouts configurable
6. **Missing error handling**: Handle database connection failures
7. **Unmonitored queries**: Track performance of critical queries
8. **Pool exhaustion**: Configure pools to prevent connection starvation