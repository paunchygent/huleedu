
### **Prompt: Structured Enum Refactoring Task**

**Objective:**
The goal is to systematically refactor the HuleEdu codebase to replace hardcoded string literals with the newly created enums from the `common_core` package. This task should be performed in a structured, incremental manner to ensure stability and allow for verification at each stage.

**Core Principles & Guidelines:**

* **Incremental Changes:** Do not attempt to refactor the entire codebase at once. Work on a per-service or per-enum-group basis as outlined in the phases below.
* **Verify After Each Major Step:** After refactoring each service, run the full suite of quality checks (`lint`, `typecheck`, `test`) to ensure no regressions have been introduced.
* **Protocols First:** Within each service, begin by updating the `protocols.py` file. Modifying the type hints here (`status: str` -> `status: BatchStatus`) will define the new "contract" and allow the type checker (`mypy`) to guide the refactoring of the implementation files.
* **Update Tests Concurrently:** As you update an implementation file, immediately update the corresponding test files. Tests should use the new enum objects directly, not string literals.
* **Respect Boundaries:** Remember the established pattern for boundaries. Internal logic, protocols, and tests **must** use enum objects. At serialization boundaries (API request/response models, Kafka event models), Pydantic will handle the conversion from strings to enums automatically.

***

### **Phased Implementation Plan**

#### **Phase 0: Prerequisite - Enum File Structure**

Confirm that the single `common_core/src/common_core/enums.py` file has been successfully refactored into the following new files, and that `common_core/src/common_core/__init__.py` exports all the necessary enums.

* `status_enums.py`
* `domain_enums.py`
* `event_enums.py`
* `observability_enums.py`
* `error_enums.py`
* `config_enums.py`

#### **Phase 1: Refactor the Batch Orchestrator Service**

Focus on a single, complex service first to establish a pattern. The Batch Orchestrator Service is a good candidate due to its central role.

1. **Update Protocol Contracts:**
    * **File:** `services/batch_orchestrator_service/protocols.py`
    * **Action:** Change all relevant `str` type hints to their corresponding enum types (`BatchStatus`, `PhaseName`, etc.).

2. **Update API Models:**
    * **File:** `services/batch_orchestrator_service/api_models.py`
    * **Action:** Ensure Pydantic models like `BatchRegistrationRequestV1` use the correct enum types (e.g., `course_code: CourseCode`). This ensures incoming JSON with string values is correctly validated and coerced into enum objects.

3. **Refactor Implementation Logic:**
    * **Files:** All files in `services/batch_orchestrator_service/implementations/`.
    * **Action:** Replace all string literals with their enum counterparts (e.g., use `PhaseName.SPELLCHECK` instead of `"spellcheck"`). The type checker will now report errors where the implementation violates the updated protocol contracts, guiding you to the exact locations that need changes.

4. **Update Configuration:**
    * **File:** `services/batch_orchestrator_service/config.py`
    * **Action:** If applicable (e.g., for the `Environment` enum), update the `Settings` model to use the new configuration enum.

5. **Update Tests:**
    * **Directory:** `services/batch_orchestrator_service/tests/`
    * **Action:** Modify all tests to pass enum objects instead of strings to the methods being tested. Update assertions to check for enum objects.

6. **Verification:**
    * Run `pdm run lint-all` and `pdm run typecheck-all` to ensure quality.
    * Run `pdm run pytest services/batch_orchestrator_service/` to confirm all tests for the service pass.

#### **Phase 2: Refactor Remaining Services (Iteratively)**

Apply the exact same pattern from Phase 1 to each of the remaining services, one at a time.

* Essay Lifecycle Service
* CJ Assessment Service
* Content Service
* File Service
* Batch Conductor Service
* Spell Checker Service
* `huleedu-service-libs`

#### **Phase 3: Final System-Wide Verification**

Once all individual services have been refactored and verified:

1. Run all quality checks from the monorepo root:
    * `pdm run lint-all`
    * `pdm run typecheck-all`
    * `pdm run test-all`
2. Bring up the entire stack with `pdm run docker-up` and run the E2E functional tests in `tests/functional/` to ensure the integrated system behaves as expected.

***

### **Definition of Done**

The refactoring task is complete when:

* All string literals identified in the "String to Enum Refactoring Task" document have been replaced with their corresponding enum members.
* All relevant type hints in protocol files, implementation files, and API models have been updated.
* All unit, integration, and functional tests pass successfully.
* The entire project passes `mypy` and `ruff` checks without errors.
* The full application stack runs correctly via Docker Compose.
