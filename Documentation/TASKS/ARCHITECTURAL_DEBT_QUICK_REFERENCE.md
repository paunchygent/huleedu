# ARCHITECTURAL DEBT REMEDIATION - QUICK REFERENCE

**Task:** HULEDU-ARCH-001  
**Status:** 🚨 CRITICAL - Must complete before File Service  
**Full Details:** See `ARCHITECTURAL_DEBT_REMEDIATION_TASK.md`

## ⚡ **IMMEDIATE ACTIONS (30 minutes)**

### **1. Add TODO Acknowledgments**

Add these comments to acknowledge technical debt:

```bash
# Add to services/spell_checker_service/event_router.py (line 1):
# TODO: ARCHITECTURAL DEBT - This file violates SRP at 442 lines
# TODO: See HULEDU-ARCH-001 for detailed refactoring plan

# Add to services/spell_checker_service/tests/test_event_router.py (line 1):  
# TODO: ARCHITECTURAL DEBT - Test file violates 400-line limit at 454 lines
# TODO: See HULEDU-ARCH-001 for detailed refactoring plan
```

## 🚨 **CRITICAL FIXES NEEDED**

### **Issue 1: SRP Violations**

- `event_router.py` (442 lines) - No TODO acknowledgment
- `test_event_router.py` (454 lines) - No TODO acknowledgment

### **Issue 2: DI Violations**

- Direct `core_logic` imports in `event_router.py`
- Should use protocol injection instead

### **Issue 3: Code Duplication**

- Same protocol classes in TWO files:
  - `event_router.py` (Lines 49-200+)
  - `di.py` (Lines 67-168)

## 🔧 **QUICK VALIDATION**

```bash
# Check file sizes
find services -name "*.py" -exec wc -l {} + | sort -nr | head -5

# Check for violations  
grep -r "from core_logic import" services/spell_checker_service/

# Check for duplicates
grep -r "class DefaultContentClient" services/spell_checker_service/
```

## ✅ **SUCCESS CRITERIA**

- [ ] No files >400 lines without TODO acknowledgment
- [ ] No direct `core_logic` imports in business logic  
- [ ] No duplicate protocol implementations
- [ ] All tests pass: `pdm run pytest`
- [ ] Services start: `docker-compose up -d`

---
**⚠️ This debt must be resolved before File Service implementation to prevent architectural drift!**
