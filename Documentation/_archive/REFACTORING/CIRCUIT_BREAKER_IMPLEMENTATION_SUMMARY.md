# CircuitBreaker OpenTelemetry Refactoring - Implementation Summary

## Quick Reference

### Problem
- CircuitBreaker eagerly initializes OpenTelemetry tracer causing RecursionError in tests
- 5 services have preemptive test hacks manipulating `trace._TRACER_PROVIDER_SET_ONCE._done`

### Solution
Implement lazy tracer initialization using Python property pattern.

### Code Changes

#### In `services/libs/huleedu_service_libs/resilience/circuit_breaker.py`:

**Replace (line 77):**
```python
self.tracer = tracer or trace.get_tracer(__name__)
```

**With:**
```python
self._explicit_tracer = tracer
self._lazy_tracer: Optional[trace.Tracer] = None
```

**Add property after `__init__`:**
```python
@property
def tracer(self) -> trace.Tracer:
    """Get tracer, initializing lazily if needed."""
    if self._explicit_tracer:
        return self._explicit_tracer
    
    if self._lazy_tracer is None:
        self._lazy_tracer = trace.get_tracer(__name__)
    
    return self._lazy_tracer
```

### Validation Steps

1. **Test in Spellchecker Service First**
   ```bash
   pdm run pytest services/spellchecker_service/tests/ -v
   ```

2. **Remove Hack from conftest.py**
   - Delete the `opentelemetry_test_isolation` fixture
   - Remove related imports

3. **Run Tests Again**
   ```bash
   pdm run pytest services/spellchecker_service/tests/ -v
   ```

### Rollout Order

1. **Spellchecker Service** (Pilot)
2. **File Service**
3. **Essay Lifecycle Service**
4. **Class Management Service**
5. **CJ Assessment Service**

### Success Metrics

- ✅ All tests pass without OpenTelemetry hacks
- ✅ No RecursionError in any test
- ✅ No performance degradation
- ✅ Clean conftest.py files

### Risk Mitigation

- Test thoroughly in spellchecker service first
- Keep old conftest.py as backup until validated
- Can revert by changing property back to eager initialization

## Implementation Checklist

- [ ] Update CircuitBreaker with lazy tracer
- [ ] Test in spellchecker service
- [ ] Remove hack from spellchecker conftest.py
- [ ] Validate tests still pass
- [ ] Document any issues found
- [ ] Proceed to other services
- [ ] Update team documentation

## Emergency Rollback

If issues arise, revert line 77 to:
```python
self.tracer = tracer or trace.get_tracer(__name__)
```
And restore the `opentelemetry_test_isolation` fixture in affected conftest.py files.