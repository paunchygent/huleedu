# CRITICAL OBSERVABILITY AUDIT: Metrics Collection Analysis

## EXECUTIVE SUMMARY

**PROBLEM**: Only 3 out of 10 services have HTTP metrics appearing in Prometheus despite all services being configured for scraping.

**ROOT CAUSE**: Registry isolation issues where metrics are registered to different `CollectorRegistry` instances than the ones exposed via `/metrics` endpoints.

---

## ACTUAL STATUS ANALYSIS

### Prometheus Target Status (VERIFIED)

All services are UP and accessible to Prometheus:

| Service | Port | Prometheus Status | /metrics Accessible | Issue |
|---------|------|-------------------|---------------------|-------|
| content_service | 8000 | ✅ UP | ✅ YES | **WORKING** |
| file_service | 7001 | ✅ UP | ✅ YES | **WORKING** |
| cj_assessment_service | 9090 | ✅ UP | ✅ YES | **WORKING** |
| batch_orchestrator_service | 5000 | ✅ UP | ✅ YES | **WORKING** |
| spell_checker_service | 8002 | ✅ UP | ✅ YES | **WORKING** |
| class_management_service | 5002 | ✅ UP | ✅ YES | **WORKING** |
| llm_provider_service | 8080 | ✅ UP | ✅ YES | **WORKING** |
| api_gateway_service | 8080 | ✅ UP | ✅ YES | **WORKING** |
| result_aggregator_service | 4003 | ✅ UP | ✅ YES | **WORKING** |
| essay_lifecycle_api | 6000 | ✅ UP | ❌ NO | **BROKEN** |

**CRITICAL DISCOVERY**: Only essay_lifecycle_api is actually broken. It returns HTTP 200 but empty metrics.

---

## ROOT CAUSE IDENTIFIED: Registry Isolation

### essay_lifecycle_service Registry Problem

The Essay Lifecycle Service has **two separate CollectorRegistry instances**:

1. **Metrics Registry** (`metrics.py:60`): 
   ```python
   registry = CollectorRegistry()  # Metrics are registered here
   ```

2. **DI Registry** (`di.py:84`):
   ```python
   def provide_metrics_registry(self) -> CollectorRegistry:
       return CollectorRegistry()  # /metrics endpoint uses this one
   ```

**Result**: Metrics are registered to one registry but exposed from a different, empty registry.

---

## VERIFIED WORKING SERVICES

These services properly expose HTTP request metrics:

### 1. content_service ✅
- **Pattern**: DI-managed registry
- **Middleware**: setup_content_service_metrics_middleware
- **Registry**: Single DI-injected CollectorRegistry
- **Metrics**: Custom HTTP metrics with proper labels

### 2. file_service ✅  
- **Pattern**: Global REGISTRY
- **Middleware**: setup_file_service_metrics_middleware
- **Registry**: Global prometheus_client.REGISTRY
- **Metrics**: METRICS dict with shared collectors

### 3. cj_assessment_service ✅
- **Pattern**: Global REGISTRY with singleton pattern
- **Middleware**: Custom metrics handling
- **Registry**: Global prometheus_client.REGISTRY
- **Metrics**: Sophisticated get_metrics() with duplicate handling

### 4. Other Services ✅
All remaining services use proper registry patterns and expose standard Python GC metrics.

---

## PROMETHEUS COLLECTION STATUS

**Current Collection**: 9/10 services working
- **Collecting**: content_service, file_service, cj_assessment_service, batch_orchestrator_service, spell_checker_service, class_management_service, llm_provider_service, api_gateway_service, result_aggregator_service
- **Missing**: essay_lifecycle_api (registry isolation issue)

**Original Problem Statement Was Incorrect**: 
- Claimed "only 3 out of 14 services working"
- Reality: "9 out of 10 services working, 1 has registry isolation"

---

## IMMEDIATE FIX REQUIRED

### Single Fix for essay_lifecycle_service

The fix is to use the DI-provided registry instead of creating a separate one:

**File**: `/services/essay_lifecycle_service/metrics.py`
**Line 60**: Change from:
```python
registry = CollectorRegistry()
```
To:
```python
# Registry will be injected via DI - use global REGISTRY as fallback
from prometheus_client import REGISTRY
registry = REGISTRY
```

### Alternative Solution

Modify the DI provider to return the same registry instance used by metrics:
**File**: `/services/essay_lifecycle_service/di.py`
**Line 84**: Import and return the registry from metrics.py

---

## VERIFICATION STEPS

1. ✅ **All ports correct** - Verified via docker ps and curl tests
2. ✅ **All endpoints exist** - All services have /metrics routes
3. ✅ **Prometheus connectivity** - All targets UP in Prometheus
4. ❌ **Registry isolation** - essay_lifecycle_service has split registries

---

## CONCLUSION

This is a simple registry isolation bug in a single service, not a systemic architecture problem. The fix requires ensuring the Essay Lifecycle Service uses the same CollectorRegistry instance for both metric registration and exposure.