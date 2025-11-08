# Import Resolution Patterns in HuleEdu Monorepo

## Context
In a monorepo with multiple microservices, import conflicts can arise when services have modules with identical names (e.g., `metrics.py`, `di.py`, `protocols.py`). This rule documents the correct import patterns to avoid these conflicts.

## The Problem
When all service directories are in PYTHONPATH (as they are in Docker containers and test environments), simple imports like `from metrics import MetricsClass` can resolve to the wrong service's module, causing import errors and type mismatches.

## The Solution: Full Module Path Imports (Mandatory)

### Relative Import Policy

**Cross-Service/Cross-Package Imports (FORBIDDEN):**
```python
# ❌ NEVER use relative imports across services or major boundaries
from ..common_core.events import EventEnvelope
from ..other_service.module import SomeClass
```

**Always use full module paths for cross-boundary imports:**
```python
# ✅ CORRECT - Full paths for cross-service/library imports
from libs.common_core.src.common_core.events import EventEnvelope
from services.other_service.module import SomeClass
```

**Intra-Package Imports (ACCEPTABLE):**
Within a single service or library package, relative imports are acceptable and encouraged for internal organization:

```python
# ✅ ACCEPTABLE in __init__.py for package exports
from .module import SomeClass
from .subpackage import helper

# ✅ ACCEPTABLE in domain packages for internal organization
from .validators import validate_input
from ..shared import common_utility
```

**Examples of acceptable relative import contexts:**
- Service `__init__.py` files: `services/cj_assessment_service/__init__.py`
- Feature packages: `services/nlp_service/features/student_matching/__init__.py`
- Test fixtures: `tests/unit/__init__.py` or `tests/conftest.py`

### Standard Pattern: Full Module Path Imports
**All services MUST use full module paths for cross-service imports:**

```python
# ✅ CORRECT - Full path prevents ambiguity
from services.result_aggregator_service.metrics import ResultAggregatorMetrics
from services.result_aggregator_service.protocols import BatchRepositoryProtocol
from services.result_aggregator_service.di import ServiceProvider
from libs.common_core.src.common_core.events import EventEnvelope

# ❌ INCORRECT - Can resolve to wrong service's module
from metrics import ResultAggregatorMetrics
from protocols import BatchRepositoryProtocol
from di import ServiceProvider
```

**Guideline:**
- **Cross-boundary** (services ↔ services, services ↔ libs): Always use full paths
- **Intra-package** (within single service/library): Relative imports acceptable for internal organization
- **When in doubt**: Use full paths for clarity

### Test Import Consistency
**Critical Rule**: Test imports must match the service's import pattern.

```python
# Service code
from services.batch_orchestrator_service.protocols import BatchRepositoryProtocol

# Test code - MUST match
from services.batch_orchestrator_service.protocols import BatchRepositoryProtocol
```

## Service-Specific Patterns

### All Services Use Full Module Paths:
- Batch Orchestrator Service (BOS)
- Result Aggregator Service (RAS)
- Essay Lifecycle Service (ELS)  
- Content Service
- File Service
- CJ Assessment Service
- Class Management Service
- API Gateway Service
- Spell Checker Service

## Implementation Guidelines

1. **New Services**: Always use full module paths
2. **Existing Services**: Check the pattern by looking at the service's `app.py` or `worker_main.py`
3. **Adding Imports**: Match the existing pattern in the file
4. **Tests**: Always match the service's import pattern

## Debugging Import Issues

If you encounter import errors like:
- `ImportError: cannot import name 'X' from 'module'`
- `AttributeError: module 'X' has no attribute 'Y'`

Check:
1. Are you using the correct import pattern for this service?
2. Do your test imports match your service imports?
3. Is Python finding the wrong module? (Check the error's file path)

## Docker vs Local Execution

The import patterns work the same in both environments because:
- Docker: `ENV PYTHONPATH=/app` includes all services
- Local: `pdm run` sets up paths to include all services

## Examples of Correct Patterns

### Result Aggregator Service
```python
# In services/result_aggregator_service/app.py
from services.result_aggregator_service.api.health_routes import health_bp
from services.result_aggregator_service.api.query_routes import query_bp
from services.result_aggregator_service.di import (
    CoreInfrastructureProvider,
    DatabaseProvider,
    ServiceProvider,
)
```

### Batch Orchestrator Service
```python
# In services/batch_orchestrator_service/app.py
from services.batch_orchestrator_service.api.batch_routes import batch_command_bp
from services.batch_orchestrator_service.api.health_routes import health_bp
from services.batch_orchestrator_service.di import (
    CoreInfrastructureProvider,
    RepositoryAndPublishingProvider,
)
```

## Rule Priority
This rule is marked as `055` because it's a critical pattern that affects all services but comes after core architectural patterns (010-050).
