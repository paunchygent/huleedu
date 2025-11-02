# PyInstaller Standalone TUI Executable - Active Task Handoff

**Task Status**: IN PROGRESS - Critical fix applied, needs rebuild and testing
**Priority**: HIGH - User needs working TUI executable
**Date**: 2025-11-02
**Context Window**: 128K/200K used - HANDOFF REQUIRED

---

## IMMEDIATE ACTION REQUIRED

**User wants ONLY the TUI executable, NOT the CLI.**

### Critical Fix Already Applied ✅

Fixed `NameError: name 'Input' is not defined` in `scripts/bayesian_consensus_model/tui/workflow_executor.py:7-8`:

```python
from textual.widgets import Input, Select
```

Removed TYPE_CHECKING block because Input/Select are used as runtime values.

### Next Steps (In Order)

1. **Update `scripts/build_standalone.sh`** - Remove redistribute-pairs (CLI) build
2. **Rebuild**: `pdm run build-standalone`
3. **Test**: `./dist/redistribute-tui` with actual workflow
4. **Verify**: No NameError, successful assignment generation

---

## Current Situation

### What Was Accomplished ✅

1. Added PyInstaller 6.16.0 to `pyproject.toml` (monorepo-tools group)
2. Moved numpy/scipy to main dependencies (required for bundling)
3. Added main() entry points to both scripts
4. Created `scripts/build_standalone.sh` with PyInstaller 6.16.0 best practices
5. Updated `.gitignore` to ignore build/, dist/, *.spec
6. First build completed - created 106MB executables
7. **CRITICAL FIX APPLIED**: Fixed TYPE_CHECKING import bug

### The Critical Bug (FIXED)

**Problem**: TUI crashed with `NameError: name 'Input' is not defined` when generating assignments.

**Root Cause**: `workflow_executor.py` lines 27-28 had:
```python
if TYPE_CHECKING:
    from textual.widgets import Input, Select
```

`TYPE_CHECKING` is `False` at runtime, so imports didn't execute. But code uses `Input` and `Select` as runtime values (not just type hints) on lines 80, 87, 106, etc.:
```python
students_csv=query_one("#students_csv_input", Input).value.strip()
```

**Fix Applied** (line 8):
```python
from textual.widgets import Input, Select
```

### Comprehensive Code Analysis ✅

Analyzed all 27 Python files in `bayesian_consensus_model/`:
- ✅ No other TYPE_CHECKING issues
- ✅ No __file__ usage problems
- ✅ No dynamic imports (importlib, __import__)
- ✅ No sys.path manipulation
- ✅ No platform-specific issues
- ✅ File operations use Path.open() (PyInstaller compatible)
- ✅ Safe getattr usage (only for argparse defaults in generate_reports.py)

**Conclusion**: TYPE_CHECKING fix was the ONLY runtime issue. Code is PyInstaller-safe.

---

## TASK: Update Build Script (USER REQUIREMENT)

**User explicitly stated**: "I am not interested in building the CLI, only the TUI."

### File to Modify

**`scripts/build_standalone.sh`**

### Changes Required

**REMOVE these sections**:

1. **Lines ~20-30** (redistribute-pairs build):
```bash
# Build CLI
echo "Building redistribute-pairs..."
pdm run pyinstaller \
  --onefile \
  --clean \
  --noconfirm \
  --name redistribute-pairs \
  --distpath ./dist \
  --workpath ./build \
  scripts/bayesian_consensus_model/redistribute_pairs.py
```

2. **Lines ~36-41** (redistribute-pairs smoke test):
```bash
# Test redistribute-pairs CLI (supports --help)
if ! ./dist/redistribute-pairs --help >/dev/null 2>&1; then
    echo "ERROR: redistribute-pairs --help failed"
    exit 1
fi
echo "✓ redistribute-pairs --help passed"
```

3. **Update final message** to only mention redistribute-tui:
```bash
echo "Executables:"
echo "  - dist/redistribute-tui"
```

Remove mention of redistribute-pairs from installation instructions.

### Expected Final Script Structure

```bash
#!/bin/bash
set -e

echo "Building standalone executable with PyInstaller 6.16.0..."

# Clean previous builds
rm -rf build/ dist/

# Build TUI
echo "Building redistribute-tui..."
pdm run pyinstaller \
  --onefile \
  --clean \
  --noconfirm \
  --name redistribute-tui \
  --distpath ./dist \
  --workpath ./build \
  scripts/bayesian_consensus_model/redistribute_tui.py

# Smoke tests
echo ""
echo "Running smoke tests..."

# Test redistribute-tui (verify it exists and is executable)
if [ ! -x "./dist/redistribute-tui" ]; then
    echo "ERROR: redistribute-tui is not executable"
    exit 1
fi
echo "✓ redistribute-tui is executable"

echo ""
echo "✅ Build complete!"
echo "Executable:"
echo "  - dist/redistribute-tui"
echo ""
echo "To install system-wide:"
echo "  sudo cp dist/redistribute-tui /usr/local/bin/"
```

---

## Testing Instructions

### 1. Rebuild

```bash
pdm run build-standalone
```

Expected: ~60 seconds (only building one executable now)

### 2. Test TUI Functionality

```bash
# Launch the TUI
./dist/redistribute-tui

# In the TUI interface:
# 1. Enter students in "Students" field: JA24, II24, ES24
# 2. Keep default rater count (14) and per-rater (10)
# 3. Press 'g' key OR click "Generate Assignments" button
# 4. Verify NO NameError occurs
# 5. Verify it generates assignments successfully
# 6. Check log panel shows success messages
```

### 3. Expected Output

✅ TUI launches without error
✅ Generate Assignments works (no NameError)
✅ Creates `optimized_pairs.csv`
✅ Creates `session2_dynamic_assignments.csv`
✅ Log panel displays optimization summary
✅ Log panel displays assignment summary

### 4. Success Criteria

- No `NameError: name 'Input' is not defined`
- Workflow completes end-to-end
- Both CSV files created with valid data
- User can use TUI for actual CJ session planning

---

## File Modifications Summary

### Modified (5 files)

1. **`pyproject.toml`**:
   - Added `pyinstaller` to monorepo-tools (line ~41)
   - Moved `numpy` and `scipy` to main dependencies (lines 32-33)
   - Added `build-standalone` PDM script (line 404)

2. **`scripts/bayesian_consensus_model/redistribute_tui.py:177-183`**:
   ```python
   def main() -> None:
       """Entry point for standalone executable."""
       RedistributeApp().run()

   if __name__ == "__main__":
       main()
   ```

3. **`scripts/bayesian_consensus_model/redistribute_pairs.py:364-370`**:
   ```python
   def main() -> None:
       """Entry point for standalone executable."""
       app()

   if __name__ == "__main__":
       main()
   ```

4. **`scripts/bayesian_consensus_model/tui/workflow_executor.py:7-8`**:
   ```python
   from textual.widgets import Input, Select
   ```
   **CRITICAL**: Removed TYPE_CHECKING block

5. **`.gitignore:68-71`**:
   ```gitignore
   # PyInstaller
   build/
   dist/
   *.spec
   ```

### Created (1 file)

1. **`scripts/build_standalone.sh`**: Build script (needs update to remove CLI)

---

## Technical Details

### PyInstaller Command

```bash
pdm run pyinstaller \
  --onefile \          # Single file executable
  --clean \            # Clean cache before building
  --noconfirm \        # Non-interactive mode
  --name redistribute-tui \
  --distpath ./dist \
  --workpath ./build \
  scripts/bayesian_consensus_model/redistribute_tui.py
```

### Why 106MB (Not 25-35MB)?

Bundles complete scientific stack:
- Python 3.11 interpreter
- numpy, scipy (large)
- pandas, matplotlib
- textual (TUI framework)
- All transitive dependencies

This is **expected and acceptable** for the use case.

### PyInstaller Version

**PyInstaller 6.16.0** (latest as of October 2025, verified from docs)

---

## Common Issues & Solutions

### If Build Fails

```bash
# Clean completely
rm -rf build/ dist/ *.spec

# Rebuild
pdm run build-standalone
```

### If TUI Crashes

1. Check error traceback for import errors
2. Verify workflow_executor.py has no TYPE_CHECKING blocks around runtime imports
3. Review PyInstaller warnings in build stderr

### If Dependencies Missing

```bash
# Reinstall all
pdm install

# Verify numpy/scipy in main dependencies
grep -A5 "^dependencies" pyproject.toml | grep -E "numpy|scipy"
```

---

## Project Standards Compliance

### From CLAUDE.local.md
- ✅ No backwards compatibility (pure development)
- ✅ DRY, SOLID, YAGNI principles
- ✅ No "helpful" extra features
- ✅ Structured error handling

### From CLAUDE.md
- ✅ PDM from root only
- ✅ No version pinning (PDM manages)
- ✅ Follow established patterns
- ✅ Delete debug scripts when done

---

## Next Claude: Exact Action Sequence

```bash
# 1. Edit build script
vim scripts/build_standalone.sh
# Remove redistribute-pairs sections (see above)

# 2. Rebuild
pdm run build-standalone

# 3. Test
./dist/redistribute-tui
# Try Generate Assignments workflow

# 4. Verify success
ls -lh dist/
# Should show only redistribute-tui (~106MB)

# 5. Report to user
# Confirm TUI works, no NameError, generates assignments successfully
```

---

## Status

**READY FOR COMPLETION**
- Critical bug fixed ✅
- Build script needs simple update (remove CLI)
- Rebuild and test required
- Estimated time: 8 minutes total

**Last Context**: workflow_executor.py TYPE_CHECKING fix is the ONLY code change needed. Everything else is configuration/build script updates.
