# Task Ticket: ELS Realignment & Walking Skeleton Simplification

**Ticket ID**: HULEDU-ELS-REALIGN-001
**Date Created**: January 2, 2025
**Reporter**: System Architect (Enum Validation Analysis)
**Assignee**: Development Team
**Priority**: P0 - Critical (Blocks Walking Skeleton)

**Title**: Fix Essay Lifecycle Service Enum Misalignments & Simplify for Walking Skeleton

## 🎯 **Problem Statement**

The Essay Lifecycle Service (ELS) contains multiple critical issues that prevent the walking skeleton from functioning:

1. **Import Errors**: ELS uses 7+ enum values that don't exist in `common_core/src/common_core/enums.py`
2. **Scope Violation**: ELS implements full multi-pipeline complexity instead of simple spellcheck-only walking skeleton
3. **Runtime Failures**: Invalid enum references will cause service crashes
4. **Architectural Violations**: ELS API endpoints violate BOS-centric architecture by providing inappropriate control mechanisms
5. **Documentation Misalignment**: ELS README doesn't clearly reflect subordinate role in BOS-centric architecture

**Impact**: Walking skeleton cannot run, blocking all development progress.

## 📝 **Acceptance Criteria**

### **Must Pass All of These**

1. **✅ Import Success**: All ELS Python files import without `ImportError`
2. **✅ Enum Alignment**: Zero references to non-existent enum values in ELS codebase
3. **✅ Walking Skeleton Scope**: VALID_ELS_STATE_TRANSITIONS contains only 7 states (uploaded, text_extracted, awaiting_spellcheck, spellchecking_in_progress, spellchecked_success, spellcheck_failed, essay_critical_failure)
4. **✅ Service Startup**: ELS worker starts without runtime errors
5. **✅ MyPy Compliance**: `pdm run mypy services/essay_lifecycle_service/` passes
6. **✅ Test Suite**: All ELS tests pass
7. **✅ No Advanced Pipelines**: Zero references to NLP, AI Feedback, Editor Revision, Grammar Check, or CJ Assessment in state transitions
8. **✅ API Architectural Compliance**: No control endpoints (POST/PUT/DELETE) except healthz, only query endpoints remain
9. **✅ BOS-Centric Documentation**: README clearly reflects ELS subordinate role and read-only API nature

### **Must NOT Include**

- Any enum values not present in `common_core/src/common_core/enums.py`
- State transitions for pipelines beyond spellcheck
- Complex multi-pipeline logic
- References to `ESSAY_ALL_PROCESSING_COMPLETED` or `ESSAY_PARTIALLY_PROCESSED_WITH_FAILURES`
- Retry or other control endpoints in API
- Any suggestion that ELS initiates processing decisions

---

## 🚀 **Implementation Order**

1. **Fix Enum Imports** (Phase 1) - Blocks everything else
2. **Simplify State Machine** (Phase 2) - Required for walking skeleton
3. **Update Tests** (Phase 3) - Validates implementation
4. **Fix API Violations** (Phase 4) - Ensures architectural compliance
5. **Align Documentation** (Phase 5) - Prevents future confusion
6. **Run All Validation Steps** - Confirms success

**Estimated Time**: 3-4 hours for careful implementation
**Risk Level**: Low (well-defined changes)
**Rollback Plan**: Git revert if validation fails

---

**Notes**: This is a **critical blocking issue** for the walking skeleton. All changes are well-defined with specific line numbers and exact replacements to eliminate implementation ambiguity. The result will be a BOS-centric ELS that properly serves its subordinate role as a stateful command handler with read-only query capabilities.
