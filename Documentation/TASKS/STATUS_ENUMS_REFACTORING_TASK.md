# Task: Refactor Status and Error Codes to Enums

## 🎯 **Task Purpose and Scope**

### **Problem Statement**

The successful `CourseCode` refactoring has highlighted a similar architectural inconsistency in how we handle status and error codes. Critical Pydantic event models like `ELSBatchPhaseOutcomeV1` and `EssayValidationFailedV1` currently use `str` types for fields like `phase_status` and `validation_error_code`. This practice bypasses the type safety provided by our well-defined enums (`BatchStatus`, `EssayStatus`, `FileValidationErrorCode`), increasing the risk of bugs from typos and making consumer logic more complex.

### **Solution Overview**

This task involves a comprehensive refactoring to replace all string-based status and error code fields in our `common_core` Pydantic models with their corresponding enum types. This will enforce data consistency at service boundaries, simplify consumer validation logic, and improve overall system robustness.

---

## 📋 **Implementation Plan**

### **Phase 1: Update `ELSBatchPhaseOutcomeV1` Contract**

**Objective**: Enforce the use of the `BatchStatus` enum for phase completion events, which are critical for BOS orchestration.

1. **Modify the Pydantic Model**:
    - **File**: `common_core/src/common_core/events/els_bos_events.py`
    - **Change**: The `phase_status` field from `str` to `BatchStatus`.

    **Current Code:**

    ```python
    class ELSBatchPhaseOutcomeV1(BaseModel):
        # ...
        phase_status: str = Field(...)
    ```

    **Target Code:**

    ```python
    from ..enums import BatchStatus # <-- Import the enum

    class ELSBatchPhaseOutcomeV1(BaseModel):
        # ...
        phase_status: BatchStatus = Field(...) # <-- Use the enum type
    ```

2. **Update Consumer Logic**:
    - **File**: `services/batch_orchestrator_service/implementations/els_batch_phase_outcome_handler.py`
    - **Action**: Update the `handle_els_batch_phase_outcome` method. The `event_data.phase_status` will now be a `BatchStatus` enum member, not a string. All comparisons and logic must use the enum (e.g., `if phase_status == BatchStatus.COMPLETED_SUCCESSFULLY:`).

### **Phase 2: Update `EssayValidationFailedV1` Contract**

**Objective**: Enforce the use of the `FileValidationErrorCode` enum for file validation failure events.

1. **Modify the Pydantic Model**:
    - **File**: `common_core/src/common_core/events/file_events.py`
    - **Change**: The `validation_error_code` field from `str` to `FileValidationErrorCode`.

    **Current Code:**

    ```python
    class EssayValidationFailedV1(BaseModel):
        # ...
        validation_error_code: str = Field(...)
    ```

    **Target Code:**

    ```python
    from ..enums import FileValidationErrorCode # <-- Import the enum

    class EssayValidationFailedV1(BaseModel):
        # ...
        validation_error_code: FileValidationErrorCode = Field(...) # <-- Use the enum type
    ```

2. **Update Producer Logic**:
    - **File**: `services/file_service/core_logic.py`
    - **Action**: When creating `EssayValidationFailedV1` instances, use enum members (e.g., `validation_error_code=FileValidationErrorCode.EMPTY_CONTENT`).

### **Phase 3: Verify and Update Downstream Test Fixtures**

**Objective**: Ensure all tests that create or mock these events are updated to use the new enum-based contracts.

1. **Update `ELSBatchPhaseOutcomeV1` Fixtures**:
    - Search all test files for instantiations of `ELSBatchPhaseOutcomeV1`.
    - Change string literals to enum members.
    - **Example**: `phase_status="COMPLETED_SUCCESSFULLY"` becomes `phase_status=BatchStatus.COMPLETED_SUCCESSFULLY`.

2. **Update `EssayValidationFailedV1` Fixtures**:
    - Search all test files for instantiations of `EssayValidationFailedV1`.
    - Change string literals to enum members.
    - **Example**: `validation_error_code="EMPTY_CONTENT"` becomes `validation_error_code=FileValidationErrorCode.EMPTY_CONTENT`.

---

## ✅ **Success Criteria**

- All Pydantic models for events now use `BatchStatus`, `EssayStatus`, and `FileValidationErrorCode` enums instead of `str`.
- The business logic in all services that produce or consume these events is updated to handle the enum types.
- All unit, integration, and functional tests are updated with the correct enum types in their test data and fixtures.
- Running `pdm run pytest` and `pdm run mypy` from the root directory completes without any errors.
