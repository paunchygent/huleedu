---
id: "041-http-service-blueprint"
type: "implementation"
created: 2025-06-05
last_updated: 2025-11-17
scope: "backend"
child_rules: ["041.1-fastapi-integration-patterns"]
---
# 041: HTTP Service Blueprint

## HuleEduApp Requirements

**app.py** (<150 LOC):
- HuleEduApp initialization with guaranteed contracts
- Dishka container setup
- Blueprint registration
- Startup/shutdown hooks
- NO route definitions

## Directory Structure
```
services/<service_name>/
├── app.py                # HuleEduApp setup
├── api/                  # REQUIRED
│   ├── health_routes.py  # REQUIRED
│   └── <domain>_routes.py
├── config.py            # Pydantic settings
├── protocols.py         # typing.Protocol contracts
└── di.py               # Dishka providers
```

## Health Routes Pattern

```python
# health_routes.py (REQUIRED)
from typing import TYPE_CHECKING
from quart import Blueprint, current_app

if TYPE_CHECKING:
    from huleedu_service_libs.quart_app import HuleEduApp

health_bp = Blueprint('health', __name__)

@health_bp.route("/healthz")
async def health_check():
    if TYPE_CHECKING:
        assert isinstance(current_app, HuleEduApp)
    
    # Guaranteed attributes (non-optional)
    engine = current_app.database_engine
    container = current_app.container
    
    # Health check logic
    return jsonify({"status": "healthy"}), 200
```

## App Initialization Pattern

```python
# app.py
from huleedu_service_libs.quart_app import HuleEduApp

def create_app() -> HuleEduApp:
    app = HuleEduApp(__name__)
    
    # Guaranteed initialization (REQUIRED)
    app.container = create_container()
    app.database_engine = create_async_engine(settings.DATABASE_URL)
    
    # Register blueprints
    app.register_blueprint(health_bp)
    app.register_blueprint(domain_bp)
    
    return app
```

## Test Fixture Pattern

```python
# tests/test_api_integration.py
@pytest.fixture
async def app_client():
    container = make_async_container(TestProvider())
    
    # REQUIRED for HuleEduApp contract
    app.container = container
    app.database_engine = AsyncMock(spec=AsyncEngine)
    
    QuartDishka(app=app, container=container)
    
    async with app.test_client() as client:
        yield client
```
