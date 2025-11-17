# ERROR HANDLING MIGRATION - FINAL PHASE CONTINUATION PROMPT

## SESSION CONTEXT: Final 2 Services Migration

You are continuing the error handling migration for the HuleEdu platform. In previous sessions, we successfully completed 10 of 12 services (83.3%) using a CLEAN REFACTOR approach with NO backwards compatibility. The remaining 2 services require migration to complete platform standardization.

## CRITICAL CONTEXT FROM USER

From `/Users/olofs_mba/.claude/CLAUDE.md`:
- NO backwards compatibility, NO adapters, NO wrappers - CLEAN BREAK approach
- Always delete deprecated patterns completely
- Respect codebase patterns and conventions
- Never make up false assertions to claim task completion
- When analyzing implementations, always raise code smells with the user

## WHAT HAS BEEN ACCOMPLISHED

### Services Successfully Migrated (10/12 - 83.3%)
1. ✅ LLM Provider Service - Reference implementation
2. ✅ Spell Checker Service - Database error_detail JSON pattern
3. ✅ Essay Lifecycle Service - Complex state machine migration
4. ✅ CJ Assessment Service - Custom exception hierarchy eliminated
5. ✅ Batch Conductor Service - Tuple return patterns removed
6. ✅ API Gateway Service - Standardized error responses
7. ✅ WebSocket Service - Real-time error handling
8. ✅ Batch Orchestrator Service - Database schema migrated
9. ✅ Result Aggregator Service - 3 error_message fields migrated
10. ✅ Class Management Service - Complete exception hierarchy removed

### Key Achievements from Class Management Service
- Deleted `exceptions.py` entirely (5 custom exceptions removed)
- Consolidated 12 API route exception handlers to single pattern
- Added correlation_id throughout all service layers
- All tests migrated from custom exceptions to HuleEduError
- Type checking and linting completed successfully

## REMAINING SERVICES REQUIRING MIGRATION

### 1. Content Service - Mixed Error Patterns
**Complexity**: HIGH (3 development cycles)
**Location**: `services/content_service/`
**Issues**: 
- Mixed error handling patterns with inconsistent approaches
- No correlation ID tracking
- No modern error structure

**Migration Requirements**:
- Implement HuleEduError patterns throughout service
- Add correlation ID tracking to all operations
- Standardize error handling in content storage
- Update all protocol signatures

### 2. File Service - ValidationResult Pattern
**Complexity**: VERY HIGH (4 development cycles)
**Location**: `services/file_service/`
**Issues**:
- ValidationResult model with `error_message` field central to validation
- 12+ test files dependent on ValidationResult
- Tuple return patterns in implementations

**Migration Requirements**:
- Complete elimination of ValidationResult model
- Replace with direct HuleEduError raising
- Update all protocol signatures to remove ValidationResult returns
- Add correlation_id parameters throughout
- Migrate extensive test suite

## YOUR IMMEDIATE TASKS

ULTRATHINK and execute the following:

### Phase 1: Service Analysis
1. **Analyze Content Service**
   - Read `services/content_service/` structure
   - Identify all error handling patterns
   - Map to HuleEduError factories
   - Document migration approach

2. **Analyze File Service** 
   - Read `services/file_service/validation_models.py`
   - Understand ValidationResult usage patterns
   - Identify all test dependencies
   - Plan complete elimination strategy

### Phase 2: Migration Execution
Based on complexity, recommend starting with Content Service (simpler) before tackling File Service.

## CRITICAL FILES AND RULES REFERENCE

### Essential Rules to Read First
Use `.cursor/rules/000-rule-index.mdc` to navigate:

1. `.cursor/rules/010-foundational-principles.mdc` - Core principles
2. `.cursor/rules/020-architectural-mandates.mdc` - Service requirements  
3. `.cursor/rules/048-structured-error-handling-standards.mdc` - Error patterns
4. `.cursor/rules/050-python-coding-standards.mdc` - Code standards
5. `.cursor/rules/070-testing-and-quality-assurance.mdc` - Test patterns
6. `.cursor/rules/110.2-coding-mode.mdc` - Implementation approach

### Error Handling Resources
- `libs/huleedu_service_libs/src/huleedu_service_libs/error_handling/factories.py` - Generic factories
- `libs/huleedu_service_libs/src/huleedu_service_libs/error_handling/file_validation_factories.py` - File service specific
- `common_core/src/common_core/models/error_models.py` - ErrorDetail model
- `common_core/src/common_core/error_enums.py` - Error code enums

### Reference Implementations
Look at these completed services for patterns:
- `services/class_management_service/` - Latest clean refactor example
- `services/spell_checker_service/` - Database error_detail pattern
- `services/batch_orchestrator_service/` - Database migration example

## ERROR HANDLING PATTERN SUMMARY

### Modern HuleEduError Pattern
```python
# NEVER USE
raise ValueError("error message")
return False, "error message"
result = ValidationResult(is_valid=False, error_message="...")

# ALWAYS USE
from huleedu_service_libs.error_handling import raise_validation_error

raise_validation_error(
    service="content_service",
    operation="store_content", 
    field="content",
    message="Detailed error message",
    correlation_id=correlation_id,
    **additional_context
)
```

### API Error Response Pattern
```python
# NEVER USE
except SomeError as e:
    return jsonify({"error": e.message}), 400

# ALWAYS USE  
except HuleEduError as e:
    logger.warning(
        f"Operation failed: {e.error_detail.message}",
        extra={
            "correlation_id": str(e.error_detail.correlation_id),
            "error_code": e.error_detail.error_code,
        }
    )
    return jsonify({"error": e.error_detail.model_dump()}), 400
```

## VALIDATION CRITERIA

For each service migration:
- ✅ NO tuple returns for error handling
- ✅ NO custom exception classes
- ✅ NO .message or .error_code attribute access
- ✅ NO ValidationResult or similar patterns
- ✅ ALL errors use HuleEduError factories
- ✅ ALL methods include correlation_id parameter
- ✅ ALL tests pass with new patterns
- ✅ Type checking passes (pdm run typecheck-all)
- ✅ Linting passes (pdm run lint-all)

## ULTRATHINK APPROACH

1. **Understand Before Acting**
   - Read service implementation thoroughly
   - Identify ALL error patterns (grep for "raise", "error", "exception")
   - Check test patterns to understand current behavior

2. **Plan Complete Migration**
   - Map each error pattern to appropriate factory
   - Identify protocol signature changes needed
   - Plan test migration strategy

3. **Execute Clean Refactor**
   - DELETE old patterns completely
   - Implement new patterns consistently
   - Update tests to match new patterns

4. **Validate Thoroughly**
   - Run tests for migrated service
   - Run type checking
   - Run linting
   - Fix all issues before completing

## CONTEXT FROM LATEST SESSION

In the previous session, we also:
1. Created Architecture Decision Records (ADRs) for Class Management Service
   - ADR-001: Course skill level architecture
   - ADR-002: Student to user account linking
2. Established `/Documentation/adr/` directory structure
3. Updated service roadmap documentation

These architectural improvements demonstrate the maturity of the codebase and should be considered when making migration decisions.

## NEXT STEPS

After completing these final 2 services:
1. Update `Documentation/TASKS/ERROR_HANDLING_MIGRATION_PLAN.md` to show 100% completion
2. Create final migration report summarizing the entire journey
3. Ensure all services follow identical error handling patterns
4. Celebrate achieving platform-wide error handling standardization!

Remember: This is the FINAL PUSH - only 2 services remain to achieve 100% modern error handling across the entire HuleEdu platform!
