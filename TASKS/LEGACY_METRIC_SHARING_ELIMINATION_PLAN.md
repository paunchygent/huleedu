# Legacy Metric Sharing Elimination Plan

## 🎯 OBJECTIVE  
Eliminate ALL legacy metric sharing anti-patterns and implement proper Dependency Injection (DI) patterns across all HuleEdu services to achieve 100% compliance with Rule 042: Async Patterns and DI.

## 🚨 CRITICAL FINDINGS

### Anti-Pattern Classification
- **SEVERE VIOLATION**: Essay Lifecycle Service (global metric sharing)
- **MODERATE VIOLATION**: Batch Conductor Service (post-injection mutation)  
- **COMPLIANT SERVICES**: 5 services already following proper patterns
- **MODERN STANDARD**: File Service (DI injection pattern to replicate)

### Architectural Violations
- **Rule 042**: Violates DI patterns - metrics should be injected via Dishka
- **Rule 020.5**: ELS architecture mandates proper DI integration
- **Anti-pattern**: Global state sharing instead of dependency injection

## 📋 COMPLETE SCOPE ANALYSIS

### SEVERE ANTI-PATTERN: Essay Lifecycle Service

#### Global Metric Sharing Anti-Pattern Identified

**File**: `services/essay_lifecycle_service/api/essay_routes.py`
**Lines**: 25, 28-31
```python
# ANTI-PATTERN: Global metric variable
ESSAY_OPERATIONS: Counter | None = None

# ANTI-PATTERN: Global state mutation function  
def set_essay_operations_metric(metric: Counter) -> None:
    global ESSAY_OPERATIONS
    ESSAY_OPERATIONS = metric

# ANTI-PATTERN: Usage with null checks
if ESSAY_OPERATIONS:
    ESSAY_OPERATIONS.labels(...).inc()
```

**File**: `services/essay_lifecycle_service/api/batch_routes.py`
**Lines**: 23, 26-29
```python
# IDENTICAL ANTI-PATTERN: Global metric variable
ESSAY_OPERATIONS: Counter | None = None

# IDENTICAL ANTI-PATTERN: Global state mutation function
def set_essay_operations_metric(metric: Counter) -> None:
    global ESSAY_OPERATIONS  
    ESSAY_OPERATIONS = metric
```

**File**: `services/essay_lifecycle_service/startup_setup.py`
**Lines**: 66-67
```python
# ANTI-PATTERN: Startup injection via global setters
set_essay_essay_operations(metrics["essay_operations"])
set_batch_essay_operations(metrics["essay_operations"])
```

#### Critical Issues Identified
1. **Global State Mutation**: Two identical global variables across route files
2. **Coupling Violation**: Routes coupled to startup initialization order
3. **Testing Issues**: Global state makes unit testing difficult
4. **Concurrency Risk**: Global variables create potential race conditions
5. **DI Bypass**: Completely bypasses established Dishka DI container

### MODERATE ANTI-PATTERN: Batch Conductor Service

#### Post-Injection Metric Sharing Anti-Pattern

**File**: `services/batch_conductor_service/api/pipeline_routes.py`
**Lines**: 42-44
```python
# ANTI-PATTERN: Post-injection metric sharing
metrics_ext = current_app.extensions.get("metrics")
if metrics_ext and hasattr(pipeline_service, "set_metrics"):
    pipeline_service.set_metrics(metrics_ext)
```

#### Issues Identified  
1. **Service Mutation**: Violates immutability by setting state after injection
2. **Implicit Dependencies**: Metrics dependency not visible in DI graph
3. **Fragile Pattern**: Relies on hasattr() checks and runtime mutation

### COMPLIANT SERVICES (No Changes Required)

#### Modern Standard: File Service ✅
**File**: `services/file_service/di.py` 
**Lines**: 55-57
```python
@provide(scope=Scope.APP)
def provide_metrics(self) -> dict[str, Any]:
    """Provide shared Prometheus metrics."""
    return get_metrics()
```

**File**: `services/file_service/api/file_routes.py`
**Line**: 37  
```python
@inject
async def upload_file(
    metrics: FromDishka[dict[str, Any]],  # ← PROPER DI INJECTION
    # other dependencies...
):
```

#### Other Compliant Services ✅
- **Batch Orchestrator Service**: Uses Quart extensions pattern properly
- **Content Service**: Uses Quart extensions pattern properly  
- **CJ Assessment Service**: Uses Quart extensions pattern properly
- **Spellchecker Service**: Uses Quart extensions pattern properly

## 🔧 REFACTORING IMPLEMENTATION

### Phase 1: Essay Lifecycle Service - CRITICAL REFACTORING

#### Step 1: Update DI Provider
**File**: `services/essay_lifecycle_service/di.py`
**Action**: Add metrics provider following File Service pattern

**Add to CoreInfrastructureProvider class**:
```python
@provide(scope=Scope.APP)
def provide_metrics(self) -> dict[str, Any]:
    """Provide shared Prometheus metrics for route injection."""
    from services.essay_lifecycle_service.metrics import get_metrics
    return get_metrics()
```

#### Step 2: Refactor Essay Routes
**File**: `services/essay_lifecycle_service/api/essay_routes.py`

**REMOVE (Lines 25, 28-31)**:
```python
# DELETE THESE LINES
ESSAY_OPERATIONS: Counter | None = None

def set_essay_operations_metric(metric: Counter) -> None:
    global ESSAY_OPERATIONS
    ESSAY_OPERATIONS = metric
```

**UPDATE Route Handler Pattern**:
```python
# BEFORE (anti-pattern)
@essay_bp.route("/<essay_id>/status", methods=["GET"])
@inject
async def get_essay_status(
    essay_id: str,
    state_store: FromDishka[EssayRepositoryProtocol],
) -> Response:
    if ESSAY_OPERATIONS:
        ESSAY_OPERATIONS.labels(operation="get_status").inc()

# AFTER (proper DI)  
@essay_bp.route("/<essay_id>/status", methods=["GET"])
@inject
async def get_essay_status(
    essay_id: str,
    state_store: FromDishka[EssayRepositoryProtocol],
    metrics: FromDishka[dict[str, Any]],
) -> Response:
    essay_operations = metrics.get("essay_operations")
    if essay_operations:
        essay_operations.labels(operation="get_status").inc()
```

**UPDATE Import Section**:
```python
# ADD to imports
from dishka import FromDishka
from typing import Any

# REMOVE from imports  
# Remove any references to set_essay_operations_metric
```

#### Step 3: Refactor Batch Routes
**File**: `services/essay_lifecycle_service/api/batch_routes.py`

**REMOVE (Lines 23, 26-29)**:
```python
# DELETE THESE LINES
ESSAY_OPERATIONS: Counter | None = None

def set_essay_operations_metric(metric: Counter) -> None:
    global ESSAY_OPERATIONS
    ESSAY_OPERATIONS = metric
```

**UPDATE All Route Handlers**:
Apply the same pattern as essay routes - add `metrics: FromDishka[dict[str, Any]]` parameter and use proper metric access.

#### Step 4: Update Startup Setup
**File**: `services/essay_lifecycle_service/startup_setup.py`

**REMOVE (Lines 66-67)**:
```python
# DELETE THESE LINES
set_essay_essay_operations(metrics["essay_operations"])
set_batch_essay_operations(metrics["essay_operations"])
```

**REMOVE Imports**:
```python
# DELETE THESE IMPORTS
from services.essay_lifecycle_service.api.batch_routes import (
    set_essay_operations_metric as set_batch_essay_operations,
)  
from services.essay_lifecycle_service.api.essay_routes import (
    set_essay_operations_metric as set_essay_essay_operations,
)
```

### Phase 2: Batch Conductor Service - MODERATE REFACTORING

#### Step 1: Update DI Provider  
**File**: `services/batch_conductor_service/di.py`

**Add Metrics Provider**:
```python
@provide(scope=Scope.APP)
def provide_metrics(self) -> dict[str, Any]:
    """Provide metrics for pipeline service integration."""
    from services.batch_conductor_service.metrics import get_metrics
    return get_metrics()
```

#### Step 2: Refactor Pipeline Service
**File**: Pipeline service implementation (exact file TBD)

**REMOVE**: `set_metrics()` method from pipeline service class
**ADD**: Metrics injection via constructor in DI provider
**ENSURE**: Service is immutable after construction

#### Step 3: Update Route Handler
**File**: `services/batch_conductor_service/api/pipeline_routes.py`

**REMOVE (Lines 42-44)**:
```python
# DELETE THESE LINES
metrics_ext = current_app.extensions.get("metrics")
if metrics_ext and hasattr(pipeline_service, "set_metrics"):
    pipeline_service.set_metrics(metrics_ext)
```

**UPDATE Route Handler**:
```python
# BEFORE (anti-pattern)
@pipeline_bp.route("/internal/v1/pipelines/define", methods=["POST"])
@inject
async def define_pipeline(
    pipeline_service: FromDishka[PipelineResolutionServiceProtocol],
) -> tuple[Response, int]:
    metrics_ext = current_app.extensions.get("metrics") 
    if metrics_ext and hasattr(pipeline_service, "set_metrics"):
        pipeline_service.set_metrics(metrics_ext)

# AFTER (proper DI)
@pipeline_bp.route("/internal/v1/pipelines/define", methods=["POST"])
@inject
async def define_pipeline(
    pipeline_service: FromDishka[PipelineResolutionServiceProtocol],
    # No metric injection needed - service already has metrics via DI
) -> tuple[Response, int]:
```

## 📅 IMPLEMENTATION TIMELINE

### Day 1: Essay Lifecycle Service Critical Refactoring

**Morning (4 hours)**:
1. Update DI provider with metrics provider
2. Refactor essay_routes.py to use DI injection
3. Remove global variables and setter functions

**Afternoon (4 hours)**:
4. Refactor batch_routes.py with same pattern
5. Update startup_setup.py to remove metric sharing
6. Run unit tests and fix any issues

### Day 2: Batch Conductor Service Moderate Refactoring

**Morning (3 hours)**:
1. Update DI provider for metrics injection
2. Refactor pipeline service to remove mutation methods
3. Update route handler to remove post-injection pattern

**Afternoon (2 hours)**:
4. Run comprehensive testing
5. Validate all metrics continue working
6. Final validation and cleanup

### Day 3: Validation and Documentation

**Morning (2 hours)**:
1. Run full test suite across all services
2. Validate metric collection works correctly
3. Performance testing of DI patterns

**Afternoon (1 hour)**:
4. Update documentation
5. Create summary report
6. Mark task as complete

## ✅ VALIDATION CRITERIA

### Pre-Refactoring Validation
- [ ] Document current metric behavior with integration tests
- [ ] Capture baseline metric values for comparison
- [ ] Identify all route handlers using anti-patterns

### Post-Refactoring Validation
- [ ] All metrics continue to work identically
- [ ] No metric registry conflicts
- [ ] Proper DI container behavior validated
- [ ] Service startup/shutdown cycles work correctly
- [ ] No global variables remain in any service

### Compliance Verification
- [ ] ✅ Rule 042: All services use proper DI patterns
- [ ] ✅ Rule 020.5: ELS follows proper DI integration
- [ ] ✅ No global state or setter functions remain
- [ ] ✅ All metrics injected via Dishka DI container

## 🚀 SUCCESS METRICS

**Immediate Benefits**:
- 100% elimination of global metric sharing anti-patterns
- Proper dependency injection for all metric usage
- Improved testability (no global state)
- Better concurrency safety

**Architectural Benefits**:
- Full compliance with established DI patterns
- Metrics dependencies visible in DI graph
- Immutable service instances after construction
- Consistent patterns across all services

## 🔄 ROLLBACKPLAN

**If Issues Discovered**:
1. Revert code changes via git feature branch
2. Restore original metric sharing patterns temporarily
3. Investigate and fix DI configuration issues
4. Re-attempt refactoring with corrections

**Safety Measures**:
- Feature branch for all changes
- Comprehensive testing before merge
- Backup of current metric configurations
- Gradual rollout service by service

## 📊 EFFORT ESTIMATION

**Total Effort**: 2-3 days
- **Essay Lifecycle Service**: 8 hours (critical complexity)
- **Batch Conductor Service**: 5 hours (moderate complexity)  
- **Testing & Validation**: 3 hours
- **Documentation**: 1 hour

**Risk Level**: MODERATE
- Multiple services affected
- DI container changes required
- Metric functionality must be preserved
- Requires careful testing to avoid regressions

**Dependencies**:
- Understanding of Dishka DI patterns
- Access to File Service as reference implementation
- Ability to run full test suite for validation

This refactoring plan ensures complete elimination of metric sharing anti-patterns while implementing proper dependency injection patterns consistent with established architectural standards.