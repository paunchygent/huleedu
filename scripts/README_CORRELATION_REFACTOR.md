# Correlation ID Refactoring Scripts

This directory contains scripts to help refactor correlation_id from optional to required throughout the HuleEdu codebase.

## Background

The HuleEdu platform uses correlation IDs for distributed tracing and debugging across microservices. Currently, correlation_id is optional (`UUID | None`) in many places, which reduces the effectiveness of our observability implementation. These scripts help automate the refactoring to make correlation_id required everywhere.

## Scripts Overview

### 1. `analyze_correlation_id_usage.py`
Analyzes current correlation_id usage patterns across the codebase.

**Usage:**
```bash
# Analyze and generate report
python scripts/analyze_correlation_id_usage.py

# Export findings as JSON for programmatic use
python scripts/analyze_correlation_id_usage.py --json correlation_analysis.json

# Analyze specific directories
python scripts/analyze_correlation_id_usage.py --services services/batch_orchestrator_service common_core
```

**Output:**
- `correlation_id_analysis.md` - Comprehensive analysis report
- Statistics on optional parameters, None defaults, generation points
- List of test files requiring updates
- Detailed findings by pattern

### 2. `update_correlation_signatures.py`
Updates method signatures to make correlation_id required.

**Usage:**
```bash
# Dry run (default) - shows what would be changed
python scripts/update_correlation_signatures.py

# Apply changes
python scripts/update_correlation_signatures.py --apply

# Process specific directories
python scripts/update_correlation_signatures.py --apply --services services/essay_lifecycle_service
```

**What it does:**
- Changes `correlation_id: UUID | None = None` to `correlation_id: UUID`
- Updates EventEnvelope to use `Field(default_factory=uuid4)`
- Adds necessary UUID imports
- Updates method calls from `correlation_id=None` to `correlation_id=uuid4()`

### 3. `verify_correlation_refactor.py`
Verifies the refactoring and finds any remaining issues.

**Usage:**
```bash
# Verify refactoring
python scripts/verify_correlation_refactor.py

# Also check for missing imports
python scripts/verify_correlation_refactor.py --check-imports

# Verify specific directories
python scripts/verify_correlation_refactor.py --services services/batch_orchestrator_service
```

**Output:**
- `correlation_verification.md` - Verification report
- Lists any remaining optional correlation_ids
- Identifies None comparisons and assignments
- Checks for missing UUID imports

## Recommended Workflow

1. **Analyze current state:**
   ```bash
   python scripts/analyze_correlation_id_usage.py
   ```
   Review the generated `correlation_id_analysis.md` to understand the scope.

2. **Create a new branch:**
   ```bash
   git checkout -b refactor/required-correlation-ids
   ```

3. **Run the update script in dry-run mode:**
   ```bash
   python scripts/update_correlation_signatures.py
   ```
   Review what changes would be made.

4. **Apply changes incrementally by service:**
   ```bash
   # Start with common_core
   python scripts/update_correlation_signatures.py --apply --services common_core
   
   # Then each service
   python scripts/update_correlation_signatures.py --apply --services services/essay_lifecycle_service
   python scripts/update_correlation_signatures.py --apply --services services/batch_orchestrator_service
   # ... etc
   ```

5. **After each service, run tests:**
   ```bash
   pdm run pytest services/essay_lifecycle_service/tests/
   ```

6. **Verify the refactoring:**
   ```bash
   python scripts/verify_correlation_refactor.py --check-imports
   ```

7. **Fix any remaining issues manually:**
   - Review `correlation_verification.md`
   - Address any complex cases the scripts couldn't handle
   - Update test files as needed

8. **Run full test suite:**
   ```bash
   pdm run test-all
   ```

9. **Run linting and type checking:**
   ```bash
   pdm run lint-all
   pdm run typecheck-all
   ```

## Manual Changes Required

Some changes may require manual intervention:

1. **Test Files**: Many test files create events with `correlation_id=None`. These need to be updated to generate UUIDs.

2. **Complex Conditionals**: Some code has complex logic around correlation_id that needs manual review.

3. **External API Contracts**: If any external APIs expect optional correlation_ids, those interfaces need careful handling.

4. **Database Schemas**: If correlation_id is stored in databases, ensure columns are NOT NULL.

## Notes

- The scripts skip files in `.venv`, `__pycache__`, `.git`, `build`, and `dist` directories
- Always run in dry-run mode first to review changes
- Commit changes incrementally by service for easier review
- The refactoring maintains backward compatibility by using `default_factory=uuid4` in EventEnvelope

## Troubleshooting

If you encounter issues:

1. **Import Errors**: Run `verify_correlation_refactor.py --check-imports` to find missing imports
2. **Type Errors**: Some Protocol definitions might need manual alignment
3. **Test Failures**: Tests may need to be updated to always provide correlation_ids

## Future Improvements

After completing the refactoring:

1. Add a pre-commit hook to prevent optional correlation_ids
2. Update coding standards to require correlation_ids
3. Consider adding runtime validation for correlation_id presence