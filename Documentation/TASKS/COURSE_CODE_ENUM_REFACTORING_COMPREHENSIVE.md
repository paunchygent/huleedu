# Task: Comprehensive CourseCode Enum Refactoring

## 🎯 **Task Purpose and Scope**

### **Problem Statement**

Analysis of the codebase reveals that `course_code` is inconsistently handled across the HuleEdu platform. While `common_core.enums` provides a well-designed `CourseCode` enum with helper functions (`get_course_language()`, `get_course_name()`, `get_course_level()`), **zero services currently import or use it**. Instead:

- **24+ Pydantic models** use `course_code: str` instead of the type-safe enum
- **Business logic** performs manual string parsing (`course_code.upper().startswith("SV")`) instead of using helper functions  
- **Test fixtures** use magic strings (`"ENG5"`, `"TEST_COURSE"`) instead of enum members
- **Database models** store course codes as raw strings without validation

This architectural inconsistency creates risks of typos, invalid data, and forces each service to re-implement course validation logic instead of leveraging the centralized `common_core` contracts.

### **Solution Overview**

Comprehensive refactoring to enforce `common_core.enums.CourseCode` usage across all services, eliminating magic strings and manual validation logic. This establishes the enum as the single source of truth for course codes throughout the platform.

---

## ✅ **COMPLETED PHASES**

### **Phase 1: Common Core Data Contracts (COMPLETED ✅)**

**Objective**: Update all shared Pydantic models to use `CourseCode` enum.

#### **✅ Completed Updates**
- **✅ `common_core/src/common_core/events/ai_feedback_events.py`**: `AIFeedbackInputDataV1.course_code` → `CourseCode`
- **✅ `common_core/src/common_core/events/cj_assessment_events.py`**: `ELS_CJAssessmentRequestV1.course_code` → `CourseCode`
- **✅ `common_core/src/common_core/events/batch_coordination_events.py`**: `BatchEssaysReady.course_code` → `CourseCode`
- **✅ `common_core/src/common_core/events/class_events.py`**: `ClassCreatedV1.course_codes` → `list[CourseCode]`
- **✅ `common_core/src/common_core/batch_service_models.py`**: Both command models updated to use `CourseCode`
- **✅ `services/batch_orchestrator_service/api_models.py`**: `BatchRegistrationRequestV1.course_code` → `CourseCode`

### **Phase 2: Service Logic Refactoring (COMPLETED ✅)**

**Objective**: Replace manual string-based course logic with enum-based helper functions.

#### **✅ Completed Updates**
- **✅ Language Inference Logic**: `services/batch_orchestrator_service/implementations/utils.py`
  - **Before**: `_infer_language_from_course_code(course_code: str) -> str` with manual parsing
  - **After**: `_infer_language_from_course_code(course_code: CourseCode) -> Language` using `get_course_language()`
- **✅ All Phase Initiators**: Updated to use enum values with `.value` conversion for string fields
- **✅ Protocol Interfaces**: `services/essay_lifecycle_service/protocols.py` updated
- **✅ Service Implementations**: `services/essay_lifecycle_service/implementations/service_request_dispatcher.py` updated
- **✅ String Interpolation**: `services/batch_orchestrator_service/implementations/batch_context_operations.py` uses enum values

#### **✅ ARCHITECTURAL FIX IMPLEMENTED**
**Problem**: ELS `batch_essay_tracker_impl.py` had hardcoded placeholder `course_code="ENG5"`

**Solution**: Enhanced `BatchEssaysRegistered` event to include course context:
- **✅ Added fields**: `course_code: CourseCode`, `essay_instructions: str`, `user_id: str`
- **✅ Updated BOS**: `batch_processing_service_impl.py` includes course context in events
- **✅ Updated ELS**: `BatchExpectation` stores and uses course context
- **✅ Updated ELS**: `batch_essay_tracker_impl.py` uses real course context instead of placeholders

**Result**: Course context now flows properly: **BOS → ELS → BatchEssaysReady** with correct enum usage.

---

### PHASE 4: Resolve Post-Enum Refactoring Test Failures 

#### 🎯 ** Task Purpose and Scope

##### **Problem Statement** 

The CourseCode enum refactoring has successfully updated our core contracts and business logic. However, it has exposed outdated test data and minor inconsistencies in our test suite and implementation, resulting in 22 test failures. These failures must be resolved to ensure the stability and correctness of the new architecture before proceeding.

#### Analysis of Failures

The 22 failures can be grouped into three primary categories:

**Pydantic ValidationError (Root Cause for ~90% of failures):**
 Most errors occur because test fixtures and functional test helpers are still creating Pydantic models using invalid string literals for course_code (e.g., "ENG101", "TEST101") instead of the required CourseCode enum members (e.g., CourseCode.ENG5). This affects unit, integration, and functional tests.

**AttributeError in AIFeedbackInitiatorImpl:** 
The initiator's logging logic attempts to access batch_context.teacher_name, a field that was correctly removed from BatchRegistrationRequestV1 during the lean registration refactoring.

**Flawed Test Logic (IndexError):**
 One test in test_cj_assessment_command_handler.py is logically incorrect. It tries to access the first element of an intentionally empty list, causing an IndexError instead of testing the intended validation failure.

##### 📋 Implementation Plan

###### Phase 1: Fix Invalid Test Data (ValidationError)

**Objective:**
Systematically update all test fixtures, helpers, and data to use the CourseCode enum, resolving the most common failure.

**Update ServiceTestManager:** Modify the create_batch helper in tests/utils/service_test_manager.py to use a valid CourseCode enum member by default and for all test calls.

**Change:** In create_batch, replace course_code: str = "TEST" with course_code: CourseCode = CourseCode.ENG5.Action: Update all calls in functional tests (e.g., test_simple_validation_e2e.py) that pass invalid strings like "E2E" or "VAL101" to use a valid enum member like CourseCode.ENG6.

**Update Unit Test Fixtures:File:** 
services/batch_orchestrator_service/tests/test_ai_feedback_initiator_impl.pyFile: services/batch_orchestrator_service/tests/test_nlp_initiator_impl.py

**Action:** In the sample_batch_context fixtures, change course_code="ENG101" to a valid enum member, like course_code=CourseCode.ENG6.Update Idempotency and Event Test 

**Data:** File: services/batch_orchestrator_service/tests/unit/test_idempotency_*.pyFile: services/essay_lifecycle_service/tests/unit/test_els_idempotency_integration.pyFile: services/cj_assessment_service/tests/unit/test_cj_idempotency_*.py

**Action:** In all fixtures and helper functions that create sample Kafka messages (e.g., sample_batch_essays_ready_event), find the course_code field and change its value from a string like "TEST101" to a valid enum member like CourseCode.ENG7.

###### Phase 2: Fix Outdated Business Logic (AttributeError)

**Objective:** Align the AIFeedbackInitiatorImpl with the lean registration contract.

**Remove Invalid Log Attribute:** File: services/batch_orchestrator_service/implementations/ai_feedback_initiator_impl.py

**Action:** Locate the logger.info call inside the initiate_phase method and remove the reference to batch_context.teacher_name, as this attribute no longer exists.

###### Phase 3: Fix Flawed Test Logic (IndexError)

**Objective:** Correct the test case to properly validate the intended behavior.Rewrite Validation Failure Test:

**File:** services/essay_lifecycle_service/tests/unit/test_cj_assessment_command_handler.pyTest: test_process_cj_assessment_command_validation_failure

**Action:** The test should not attempt to access an element of the empty essays_to_process list. Instead, it should assert that calling process_initiate_cj_assessment_command with an empty list raises a DataValidationError. This correctly tests the handler's input validation logic.

#### ✅ Success Criteria

All 22 test failures are resolved.Running pdm run pytest from the root directory results in all tests passing.The codebase consistently uses the CourseCode enum in all relevant data models and test fixtures.

## 📊 **CURRENT SUCCESS RATE**

### **Phase 1 (API Contracts)**: ✅ **100% Complete**
### **Phase 2 (Service Logic)**: ✅ **100% Complete** 
### **Phase 3 (Database Models)**: ✅ **100% Complete** (No changes needed - enum serializes to string)
### **Phase 4 (Test Infrastructure)**: 🔄 **~30% Complete**

**Overall Progress**: **75% Complete**

---

## 🎯 **REMAINING WORK**

### **Test Code Updates Needed**
The remaining type errors are all in test code using invalid course codes that don't exist in our `CourseCode` enum:

**Invalid Course Codes Found**:
- `"CS101"`, `"ENG101"`, `"LIT201"`, `"ABC123"`, `"PHIL301"`, `"SV101"`, `"VAL102"`, `"TEST_COURSE"`

**Valid Enum Members Available**:
- `CourseCode.ENG5`, `CourseCode.ENG6`, `CourseCode.ENG7`, `CourseCode.SV1`, `CourseCode.SV2`, `CourseCode.SV3`

### **Next Steps**
1. **Update test utilities** (`tests/utils/service_test_manager.py`) to use valid enum members
2. **Update contract tests** to use valid course codes  
3. **Update integration/functional tests** to use enum members
4. **Run full test suite** to verify no regressions

---

## ✅ **SUCCESS CRITERIA STATUS**

### **Type Safety Validation**
- ✅ All `course_code` fields in production code use `CourseCode` enum
- ✅ No hardcoded course code placeholders in business logic
- 🔄 Test fixtures migration to enum members (in progress)

### **Functionality Validation**  
- ✅ Language inference uses `get_course_language()` helper exclusively
- ✅ No manual string parsing of course codes in business logic
- ✅ Architectural fix ensures proper course context flow

### **Contract Compliance**
- ✅ All inter-service events use `CourseCode` enum in Pydantic models
- ✅ Database serialization works correctly (enum → string)
- ✅ API request/response models enforce enum validation

### **Code Quality**
- ✅ **Zero magic strings** for course codes in production code
- ✅ All course-related helper functions from `common_core.enums` are utilized
- ✅ Consistent import patterns across all services

---

**MAJOR ACHIEVEMENT**: The architectural fix successfully eliminated the hardcoded placeholder and established proper course context flow from BOS to ELS. Production code is now fully type-safe and uses the enum correctly. 