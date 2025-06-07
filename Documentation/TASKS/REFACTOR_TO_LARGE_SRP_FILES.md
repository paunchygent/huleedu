# Refactor Large Python Files for SRP & Maintainability

This document tracks all Python files in the codebase exceeding 400 lines. These files are candidates for refactoring to improve maintainability, testability, and adherence to the Single Responsibility Principle (SRP). For each file, a description, the main SRP/complexity issues, and recommended refactoring strategies using the project's `typing.Protocol` and Dishka DI (Dependency Injection) patterns are provided.

## Refactoring Progress (as of 2025-06-07)

### ✅ COMPLETED REFACTORING

#### 1. `services/essay_lifecycle_service/state_store.py` ✅ 

**IMPLEMENTED:** Successfully refactored from 458 → 298 lines (35% reduction)

**Implementation Summary:**
- **Extracted essay_state_model.py** (50 lines) - Pydantic EssayState data model
- **Extracted database_schema_manager.py** (77 lines) - SQLiteDatabaseSchemaManager with clean delegation pattern
- **Extracted essay_crud_operations.py** (154 lines) - SQLiteEssayCrudOperations for all database operations
- **Maintained state_store.py** (298 lines) - Clean coordination layer using delegation pattern
- **Results:** Perfect SRP compliance, clean architecture, all 88 tests passing

#### 2. `services/essay_lifecycle_service/implementations/batch_command_handler_impl.py` ✅

**IMPLEMENTED:** Successfully refactored from 435 → 84 lines (81% reduction)

**Implementation Summary:**
- **Extracted spellcheck_command_handler.py** (209 lines) - Dedicated spellcheck processing logic
- **Extracted cj_assessment_command_handler.py** (243 lines) - Dedicated CJ assessment processing logic  
- **Extracted future_services_command_handlers.py** (62 lines) - NLP and AI Feedback stubs
- **Updated batch_command_handler_impl.py** (84 lines) - Clean delegation coordinator
- **Updated DI configuration** (di.py) - Proper dependency injection for all service handlers
- **Comprehensive test coverage restored:**
  - test_spellcheck_command_handler.py (295 lines)
  - test_cj_assessment_command_handler.py (264 lines) 
  - test_future_services_command_handlers.py (62 lines)
- **Results:** Service-based SRP architecture, protocol-based testing, all 12 tests passing

### 🔄 REMAINING WORK

#### 3. `services/batch_orchestrator_service/implementations/batch_repository_postgres_impl.py` (420 lines)

**Purpose:** Implements the Postgres-backed batch repository for BOS.
**Problem:** Contains all repository logic (CRUD, pipeline state, etc.) in one class/module.
**Refactor Guidance:**

- Split into protocol-based repository interfaces (e.g., state, CRUD, batch ops).
- Use Dishka DI to compose repository implementations.
- Reference: See `.windsurf/rules/040-service-implementation-guidelines.md` and `.windsurf/rules/051-pydantic-v2-standards.md` for protocol/DI and model separation best practices.

#### 4. `tests/functional/test_pattern_alignment_validation.py` (415 lines)

**Purpose:** Functional test validating pattern alignment across services.
**Problem:** Monolithic test logic, hard to maintain or extend.
**Refactor Guidance:**

- Extract reusable fixtures and helpers to separate modules.
- Use protocol-based test utility interfaces for mocking service behaviors.

#### 5. `tests/functional/test_walking_skeleton_e2e_v2.py` (561 lines)

**Purpose:** Comprehensive end-to-end test for the walking skeleton pipeline.
**Problem:** Contains multiple logical flows and test scenarios in a single file.
**Refactor Guidance:**

- Split into scenario-focused test modules.
- Use protocol-based interfaces for pipeline mocks.

#### 6. `scripts/tests/test_phase3_bos_orchestration.py` (571 lines)

**Purpose:** BOS orchestration phase test script.
**Problem:** Multiple orchestration phases and helpers in one file.
**Refactor Guidance:**

- Move orchestration helpers to protocol-driven utility modules.
- Use DI to inject scenario-specific mocks.

#### 7. `services/essay_lifecycle_service/tests/unit/test_batch_phase_coordinator_impl.py` (408 lines)

**Purpose:** Unit tests for batch phase coordinator implementation.
**Problem:** Multiple test cases and setup logic tightly coupled.
**Refactor Guidance:**

- Extract shared fixtures and mocks to protocol-based test modules.
- Use DI for dependency isolation.

#### 8. `services/essay_lifecycle_service/tests/unit/test_batch_command_handler_impl.py` (468 lines)

**Status:** NEEDS UPDATE after refactoring - likely much smaller now due to delegation pattern
**Purpose:** Unit tests for batch command handler implementation.
**Refactor Guidance:**

- Update to test only delegation logic (should be much smaller now)
- Protocol-based mocks for service handler dependencies

#### 9. `services/essay_lifecycle_service/tests/unit/test_essay_state_machine.py` (609 lines)

**Purpose:** Unit tests for essay state machine.
**Problem:** All state transitions and edge cases in one file.
**Refactor Guidance:**

- Split by transition type or scenario.
- Use protocol-based state machine mocks and DI.

---

## Summary

**Completed:** 2/3 priority core logic files (512 lines removed total)
**Next Priority:** Batch repository Postgres implementation (BOS)
**Architectural Success:** Clean SRP patterns, protocol-based DI, comprehensive test coverage

## General Refactoring Strategy

- **Identify logical responsibilities** in each large file/class.
- **Define `typing.Protocol` interfaces** for each responsibility.
- **Move concrete implementations** to smaller, focused modules.
- **Register implementations with the Dishka DI container** for runtime injection.
- **Update tests** to use protocol-based mocks and DI for isolation.

See also: `.windsurf/rules/040-service-implementation-guidelines.md`, `.windsurf/rules/051-pydantic-v2-standards.md`, `.windsurf/rules/070-testing-and-quality-assurance.md` for detailed patterns and examples.
