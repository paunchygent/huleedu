# CJ ASSESSMENT SERVICE - FILE SIZE REFACTORING TASK

You are Claude Code, tasked with refactoring oversized files in the CJ Assessment Service that violate the <400 Lines of Code (LoC) rule. This refactoring emerged from the implementation of TASK-LLM-02 and TASK-CJ-03.

## ULTRATHINK MISSION OVERVIEW

PRIMARY OBJECTIVE: Refactor three critical files that significantly exceed the 400 LoC guideline by applying Single Responsibility Principle (SRP) to create focused, maintainable modules while preserving all functionality and architectural integrity.

## CONTEXT: THE PROBLEM

### Current LoC Violations 🚨

During the implementation of batch LLM processing (TASK-CJ-03), three files have grown beyond acceptable limits:

1. **`batch_processor.py`**: ~1,236 lines ❌ (3x over limit)
2. **`test_failed_comparison_pool.py`**: ~927 lines ❌ (2.3x over limit)  
3. **`batch_callback_handler.py`**: ~703 lines ❌ (1.75x over limit)

### File Size Guidelines 📏

From `.cursor/rules/050-python-coding-standards.mdc`:
- **Target Range**: 350-450 LoC per file
- **Hard Limit**: NO files above 500-600 LoC
- **Enforcement**: Hard limit enforced by CI where possible

### Why This Matters 🎯

- **Maintainability**: Large files are harder to understand and modify
- **Testing**: Focused modules are easier to test in isolation
- **Code Review**: Smaller files enable more effective reviews
- **SRP Compliance**: Each module should have a single, well-defined responsibility

## MANDATORY WORKFLOW

### STEP 1: Build Refactoring Knowledge

Read these critical resources:
1. **Current Implementation Files**:
   - `/services/cj_assessment_service/cj_core_logic/batch_processor.py`
   - `/services/cj_assessment_service/cj_core_logic/batch_callback_handler.py`
   - `/services/cj_assessment_service/tests/unit/test_failed_comparison_pool.py`

2. **Architecture Rules**:
   - `.cursor/rules/050-python-coding-standards.mdc` - File size limits
   - `.cursor/rules/040-service-implementation-guidelines.mdc` - Service patterns
   - `.cursor/rules/042-async-patterns-and-di.mdc` - Module organization

3. **Context Documents**:
   - `/documentation/TASKS/TASK-CJ-03-batch-llm-integration.md` - Implementation context
   - Current module dependencies and import patterns

### STEP 2: ULTRATHINK Analysis

Before refactoring, analyze each file to identify:
1. **Distinct Responsibilities** within each module
2. **Natural Separation Points** based on functionality
3. **Shared Dependencies** that need careful handling
4. **Public vs Internal APIs** to maintain compatibility

### STEP 3: Agent Deployment for Systematic Refactoring

**Agent Alpha: BatchProcessor Refactoring**
- Analyze the 1,236-line `batch_processor.py`
- Identify distinct responsibilities (submission, pool management, configuration)
- Propose module separation strategy
- Implement refactoring with proper imports and exports

**Agent Beta: Test File Refactoring**
- Analyze the 927-line `test_failed_comparison_pool.py`
- Group related test cases by functionality
- Create focused test modules
- Ensure test discovery remains intact

**Agent Charlie: Callback Handler Refactoring**
- Analyze the 703-line `batch_callback_handler.py`
- Separate callback processing from workflow logic
- Create focused modules for distinct responsibilities
- Maintain integration points

## REFACTORING STRATEGY

### For `batch_processor.py` (1,236 lines → 3-4 modules)

**Proposed Module Structure**:
```
batch_processor.py (350 lines)
  - Main BatchProcessor class
  - Core batch submission logic
  - Public API methods

batch_pool_manager.py (400 lines)
  - Failed comparison pool management
  - Retry logic and statistics
  - Pool-specific operations

batch_config.py (200 lines)
  - BatchConfigOverrides model
  - Configuration validation
  - Effective settings calculation

batch_submission.py (286 lines)
  - Chunk submission logic
  - State management helpers
  - Database interaction utilities
```

### For `test_failed_comparison_pool.py` (927 lines → 3 modules)

**Proposed Test Structure**:
```
test_pool_management.py (350 lines)
  - Basic pool operations tests
  - Add/remove/update tests
  - Statistics tracking tests

test_retry_logic.py (350 lines)
  - Retry batch formation tests
  - Threshold checking tests
  - Force retry scenarios

test_pool_integration.py (227 lines)
  - Integration with callback handler
  - End-to-end pool scenarios
  - Error handling tests
```

### For `batch_callback_handler.py` (703 lines → 2 modules)

**Proposed Module Structure**:
```
batch_callback_handler.py (400 lines)
  - Main callback processing logic
  - Public API (continue_cj_assessment_workflow)
  - Core integration points

callback_state_manager.py (303 lines)
  - State update logic
  - Batch completion detection
  - Workflow continuation decisions
```

## CRITICAL REFACTORING PRINCIPLES

### MUST Maintain:
1. **All Existing Functionality** - No feature regression
2. **Public API Compatibility** - External interfaces unchanged
3. **Import Patterns** - Follow project conventions
4. **Test Coverage** - All tests must continue passing

### MUST Follow:
1. **Single Responsibility Principle** - Each module has one clear purpose
2. **High Cohesion** - Related functionality stays together
3. **Low Coupling** - Minimize inter-module dependencies
4. **Clear Naming** - Module names reflect their responsibility

### FORBIDDEN:
1. **Breaking Changes** - Public APIs must remain stable
2. **Circular Imports** - Careful dependency management
3. **God Objects** - No "utility" modules with mixed responsibilities
4. **Test Fragmentation** - Related tests stay together

## IMPLEMENTATION APPROACH

### Phase 1: Analysis and Planning
1. **Create Dependency Map** - Understand current inter-dependencies
2. **Identify Cut Points** - Find natural module boundaries
3. **Design Import Structure** - Plan clean import hierarchy
4. **Document Public APIs** - Clarify what must remain stable

### Phase 2: Incremental Refactoring
1. **Start with Largest File** - `batch_processor.py` first
2. **Extract One Module at a Time** - Gradual transformation
3. **Run Tests After Each Step** - Ensure nothing breaks
4. **Update Imports Systematically** - Fix all references

### Phase 3: Validation
1. **Run Full Test Suite** - All tests must pass
2. **Check Import Cycles** - No circular dependencies
3. **Validate LoC Compliance** - All files under 500 lines
4. **Update Documentation** - Reflect new module structure

## DELIVERABLES

### Required Outputs:
1. **Refactored Modules** - All files under 500 LoC (target 350-450)
2. **Updated Imports** - All references fixed throughout codebase
3. **Passing Tests** - Full test suite success
4. **Module Documentation** - Clear docstrings for each new module
5. **Migration Guide** - Document what moved where for future reference

### Success Metrics:
- ✅ No file exceeds 500 LoC
- ✅ All tests pass without modification
- ✅ Public APIs remain unchanged
- ✅ Clear separation of concerns
- ✅ Improved code organization

## KEY CONSIDERATIONS

### Import Management:
```python
# Old (single module)
from cj_core_logic.batch_processor import BatchProcessor, BatchConfigOverrides

# New (multiple modules)  
from cj_core_logic.batch_processor import BatchProcessor
from cj_core_logic.batch_config import BatchConfigOverrides
```

### Backward Compatibility:
Consider creating `__init__.py` re-exports for smooth transition:
```python
# cj_core_logic/__init__.py
from .batch_processor import BatchProcessor
from .batch_config import BatchConfigOverrides
from .batch_pool_manager import FailedComparisonPool
# Maintain existing import patterns
```

### Test Organization:
Ensure pytest can still discover all tests:
```python
# Keep related tests together
# Use consistent naming: test_*.py
# Maintain existing test class structures where sensible
```

## EXAMPLE REFACTORING PATTERN

### Before: Monolithic Module
```python
# batch_processor.py (1,236 lines)
class BatchConfigOverrides(BaseModel):
    ...

class BatchSubmissionResult(BaseModel):
    ...

class BatchProcessor:
    def __init__(self, ...):
        ...
    
    def submit_comparison_batch(self, ...):
        ...
    
    def add_to_failed_pool(self, ...):
        ...
    
    def check_retry_batch_needed(self, ...):
        ...
    
    # ... many more methods
```

### After: Focused Modules
```python
# batch_config.py (focused on configuration)
class BatchConfigOverrides(BaseModel):
    ...

# batch_submission.py (focused on submission logic)
class BatchSubmissionResult(BaseModel):
    ...

def submit_batch_chunk(...):
    ...

# batch_pool_manager.py (focused on failed pool)
class FailedPoolManager:
    def add_to_failed_pool(self, ...):
        ...
    
    def check_retry_batch_needed(self, ...):
        ...

# batch_processor.py (orchestration and public API)
class BatchProcessor:
    def __init__(self, ...):
        self.pool_manager = FailedPoolManager(...)
        ...
    
    def submit_comparison_batch(self, ...):
        # Delegates to appropriate modules
        ...
```

## IMMEDIATE NEXT STEPS

1. **Deploy Agent Alpha** - Begin `batch_processor.py` analysis and refactoring
2. **Create Module Structure** - Implement proposed module separation
3. **Update All Imports** - Fix references throughout codebase
4. **Run Test Suite** - Validate no regression
5. **Deploy Remaining Agents** - Complete other file refactoring

## ARCHITECTURAL COMPLIANCE

Remember to follow all architectural rules:
- `.cursor/rules/010-foundational-principles.mdc` - No vibe coding
- `.cursor/rules/020-architectural-mandates.mdc` - Clean architecture
- `.cursor/rules/040-service-implementation-guidelines.mdc` - Service patterns
- `.cursor/rules/050-python-coding-standards.mdc` - Coding standards

This refactoring will improve code maintainability while preserving all the excellent functionality implemented in TASK-CJ-03. Focus on creating clean, focused modules that each serve a single, well-defined purpose.