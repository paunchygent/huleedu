---
id: pyinstaller-standalone-executables-plan
title: PyInstaller Standalone Executables Plan
type: task
status: proposed
priority: medium
domain: assessment
service: ''
owner_team: agents
owner: ''
program: ''
created: '2025-11-02'
last_updated: '2026-02-01'
related: []
labels: []
---
## Objective

Create standalone executable binaries for `cj-pair-generator-tui` and `redistribute-pairs` using PyInstaller with `--onefile` mode, enabling distribution and execution on any machine without Python installation or dependency management.

## Context

The Bayesian consensus model scripts (`redistribute_tui.py` and `redistribute_pairs.py`) are currently Python modules requiring:

- Python 3.11+ environment
- PDM dependency management
- Project-relative imports
- External dependencies (textual, numpy, scipy, typer)

**Goal**: Package into single-file executables that:

- Run on any macOS/Linux/Windows machine (same architecture)
- Bundle Python interpreter + all dependencies
- Require no installation or setup
- Can be distributed via copy/symlink to `$PATH`

## Trade-offs: `--onefile` vs `--onedir`

### `--onefile` (Chosen Approach)

**How it works:**

- Single executable file (~25-35MB)
- Unpacks to temp directory on each run (`/tmp/_MEIxxxxxx/`)
- Startup time: 1-3 seconds (acceptable for interactive tools)

**Pros:**
✅ Clean distribution (single file)
✅ Easy to copy/move/symlink
✅ Simple user experience
✅ Minimal disk footprint

**Cons:**
❌ Slower startup (unpacking overhead)
❌ Temp directory bloat over time

### `--onedir` (Alternative)

**How it works:**

- Executable + libraries folder (~80-100MB)
- No unpacking, runs directly
- Startup time: <0.5 seconds

**Pros:**
✅ Fast startup

**Cons:**
❌ Messy distribution (folder, not single file)
❌ Larger disk footprint

**Decision**: Use `--onefile` for clean distribution. Startup delay (1-3s) is acceptable for interactive CLI/TUI tools.

---

## Implementation Plan

### Phase 1: Setup PyInstaller

**1.1. Add PyInstaller Dependency**

File: `pyproject.toml`

```toml
[tool.pdm.dev-dependencies]
build = [
    "pyinstaller>=6.0",
]
```

Install:

```bash
pdm install
```

**1.2. Create Build Scripts**

File: `scripts/build_standalone.sh`

```bash
#!/bin/bash
set -e

echo "Building standalone executables with PyInstaller..."

# Clean previous builds
rm -rf build/ dist/

# Build TUI
echo "Building cj-pair-generator-tui..."
pdm run pyinstaller \
  --onefile \
  --name cj-pair-generator-tui \
  --clean \
  scripts/bayesian_consensus_model/redistribute_tui.py

# Build CLI
echo "Building redistribute-pairs..."
pdm run pyinstaller \
  --onefile \
  --name redistribute-pairs \
  --clean \
  scripts/bayesian_consensus_model/redistribute_pairs.py

echo "✅ Build complete!"
echo "Executables:"
echo "  - dist/cj-pair-generator-tui"
echo "  - dist/redistribute-pairs"
echo ""
echo "To install system-wide:"
echo "  sudo cp dist/cj-pair-generator-tui /usr/local/bin/"
echo "  sudo cp dist/redistribute-pairs /usr/local/bin/"
```

Make executable:

```bash
chmod +x scripts/build_standalone.sh
```

**1.3. Add PDM Script Shortcut**

File: `pyproject.toml`

```toml
[tool.pdm.scripts]
build-standalone = {shell = "scripts/build_standalone.sh"}
```

Usage:

```bash
pdm run build-standalone
```

---

### Phase 2: Entry Point Functions

PyInstaller needs proper entry points. Add `main()` functions to both scripts.

**2.1. Update `redistribute_tui.py`**

Add at end of file (before `if __name__ == "__main__"`):

```python
def main() -> None:
    """Entry point for standalone executable."""
    RedistributeApp().run()


if __name__ == "__main__":
    main()
```

**2.2. Update `redistribute_pairs.py`**

Add at end of file (before `if __name__ == "__main__"`):

```python
def main() -> None:
    """Entry point for standalone executable."""
    app()


if __name__ == "__main__":
    main()
```

---

### Phase 3: Ignore Build Artifacts

**3.1. Update `.gitignore`**

Add:

```gitignore
# PyInstaller
build/
dist/
*.spec
```

**Rationale:** Built executables are platform-specific binaries, not source code. Don't commit them.

---

### Phase 4: Testing & Validation

**4.1. Build Executables**

```bash
pdm run build-standalone
```

**4.2. Test Standalone Execution**

```bash
# Test TUI (should launch immediately)
./dist/cj-pair-generator-tui

# Test CLI help
./dist/redistribute-pairs --help

# Test CLI optimize command
./dist/redistribute-pairs optimize-pairs \
  --student JA24 --student II24 --student ES24 \
  --total-slots 84 \
  --output-csv test_output.csv
```

**4.3. Test on Clean Environment**

Optional: Test on machine without Python/PDM to verify true standalone:

```bash
# Copy to clean VM/container
scp dist/cj-pair-generator-tui user@clean-machine:/tmp/
ssh user@clean-machine /tmp/cj-pair-generator-tui
```

**4.4. Measure Performance**

```bash
# Measure startup time
time ./dist/cj-pair-generator-tui --help
time ./dist/redistribute-pairs --help
```

Expected: 1-3 seconds first run (unpacking), slightly faster on subsequent runs (if temp files cached).

---

### Phase 5: Distribution & Installation

**5.1. Local Installation**

```bash
# System-wide installation
sudo cp dist/cj-pair-generator-tui /usr/local/bin/
sudo cp dist/redistribute-pairs /usr/local/bin/

# User-specific installation
mkdir -p ~/bin
cp dist/cj-pair-generator-tui ~/bin/
cp dist/redistribute-pairs ~/bin/
# Add ~/bin to PATH if needed
```

**5.2. Symlink Alternative**

```bash
# Create symlinks instead of copying
sudo ln -s "$(pwd)/dist/cj-pair-generator-tui" /usr/local/bin/
sudo ln -s "$(pwd)/dist/redistribute-pairs" /usr/local/bin/
```

**5.3. Distribution to Others**

```bash
# Create distribution archive
tar -czf redistribute-tools-macos-$(uname -m).tar.gz \
  -C dist \
  cj-pair-generator-tui \
  redistribute-pairs

# Users extract and install:
# tar -xzf redistribute-tools-macos-*.tar.gz
# sudo cp redistribute-{tui,pairs} /usr/local/bin/
```

---

## File Structure After Implementation

```
huledu-reboot/
├── scripts/
│   ├── build_standalone.sh          # NEW: Build script
│   └── bayesian_consensus_model/
│       ├── redistribute_tui.py      # MODIFIED: Add main() entry point
│       └── redistribute_pairs.py    # MODIFIED: Add main() entry point
├── dist/                             # NEW: Built executables (gitignored)
│   ├── cj-pair-generator-tui             # ~25-35MB standalone binary
│   └── redistribute-pairs           # ~25-35MB standalone binary
├── build/                            # NEW: Build cache (gitignored)
├── *.spec                            # NEW: PyInstaller specs (gitignored)
├── .gitignore                        # MODIFIED: Ignore build artifacts
└── pyproject.toml                    # MODIFIED: Add pyinstaller dep + script
```

---

## Success Criteria

### Build Phase

- ✅ `pdm run build-standalone` completes without errors
- ✅ Creates `dist/cj-pair-generator-tui` and `dist/redistribute-pairs`
- ✅ Both executables are ~25-35MB single files
- ✅ File permissions are executable (`-rwxr-xr-x`)

### Execution Phase

- ✅ `./dist/cj-pair-generator-tui` launches TUI without errors
- ✅ `./dist/redistribute-pairs --help` shows CLI help
- ✅ `./dist/redistribute-pairs optimize-pairs ...` runs optimizer
- ✅ Startup time is 1-3 seconds (acceptable)
- ✅ No Python installation required on target machine

### Distribution Phase

- ✅ Executables can be copied to `/usr/local/bin/`
- ✅ Run from any directory: `cj-pair-generator-tui` works globally
- ✅ No dependency errors on clean environment

---

## Advanced Optimizations (Optional Future Work)

### Reduce Binary Size

```bash
# Use UPX compression (requires upx installed)
pdm run pyinstaller \
  --onefile \
  --name cj-pair-generator-tui \
  --upx-dir /usr/local/bin \
  scripts/bayesian_consensus_model/redistribute_tui.py
```

Result: ~15-20MB (instead of 25-35MB)

### Exclude Unnecessary Modules

Create `pyinstaller-hooks/hook-exclude.py`:

```python
# Exclude test frameworks, unused stdlib modules
excludedimports = ['pytest', 'unittest', 'tkinter']
```

Add to build:

```bash
pdm run pyinstaller \
  --onefile \
  --additional-hooks-dir=pyinstaller-hooks \
  ...
```

### Cross-Platform Builds

PyInstaller can't cross-compile. To build for multiple platforms:

```bash
# On macOS: builds macOS binary
pdm run build-standalone

# On Linux VM: builds Linux binary
pdm run build-standalone

# On Windows VM: builds Windows binary
pdm run build-standalone
```

Distribute platform-specific archives:

- `redistribute-tools-macos-arm64.tar.gz`
- `redistribute-tools-macos-x86_64.tar.gz`
- `redistribute-tools-linux-x86_64.tar.gz`
- `redistribute-tools-windows-x86_64.zip`

---

## Maintenance

### Rebuilding After Code Changes

```bash
# After modifying TUI/CLI code:
pdm run build-standalone

# Reinstall if using symlinks (automatic)
# Or copy if using direct installation:
sudo cp dist/cj-pair-generator-tui /usr/local/bin/
```

### Cleanup

```bash
# Remove build artifacts
rm -rf build/ dist/ *.spec
```

---

## Constraints & Limitations

### File Size

- ✅ **Acceptable**: 25-35MB per executable (modern machines)
- ❌ **Not suitable**: Environments with strict size limits (<10MB)

### Startup Time

- ✅ **Acceptable**: 1-3 seconds for interactive tools
- ❌ **Not suitable**: High-frequency automation (use Python module instead)

### Platform Dependence

- ✅ Binary is platform-specific (macOS binary won't run on Linux)
- ❌ Need separate builds for each platform

### Python Version Lock

- ✅ Built binary uses Python 3.11 (frozen at build time)
- ❌ Can't upgrade Python without rebuilding

---

## Adherence to Project Standards

### DRY (Don't Repeat Yourself)

✅ Single build script handles both executables
✅ Reuses existing Python modules (no duplication)

### SOLID

✅ No architectural changes needed
✅ Entry points (`main()`) follow SRP

### YAGNI (You Aren't Gonna Need It)

✅ No extra features beyond standalone execution
✅ Optional optimizations documented but not implemented unless needed

### Clean Code

✅ No sys.path hacks (removed in previous task)
✅ Entry points are minimal wrappers

### Documentation Standards (Rule 090)

✅ This task document follows TASKS/ structure
✅ Includes context, implementation steps, success criteria
✅ Future maintenance guidance included

---

## Estimated Effort

- **Phase 1 (Setup)**: 15 minutes
- **Phase 2 (Entry points)**: 10 minutes
- **Phase 3 (Gitignore)**: 5 minutes
- **Phase 4 (Testing)**: 20 minutes
- **Phase 5 (Installation)**: 10 minutes

**Total**: ~60 minutes

---

## Dependencies

**Required:**

- PDM environment (already present)
- pyinstaller>=6.0 (to be added)

**Optional:**

- UPX compressor (for size optimization)
- Cross-platform VMs (for multi-platform builds)

---

## Risk Assessment

**Low Risk:**

- ✅ No changes to core logic
- ✅ Minimal code changes (2 entry point functions)
- ✅ Build artifacts are gitignored
- ✅ Existing tests validate functionality

**Potential Issues:**

- ⚠️ First-time PyInstaller setup may require debugging import paths
- ⚠️ Platform-specific libraries (numpy, scipy) may need PyInstaller hooks
- ⚠️ Textual TUI framework may have hidden dependencies

**Mitigation:**

- Test thoroughly before distribution
- Keep original Python module workflow as fallback
- Document any PyInstaller-specific configuration needed

---

## PyInstaller Standalone TUI ✅ COMPLETED

**Status**: Functional - 106MB onefile executable, PyInstaller 6.16.0, Textual 6.5.0
**Build**: `pdm run build-standalone` → `dist/cj-pair-generator-tui` (~60s)
**Distribution**: `sudo cp dist/cj-pair-generator-tui /usr/local/bin/`

### Setup Complete

- Dependencies: PyInstaller 6.16.0 (monorepo-tools), numpy/scipy moved to main deps
- Build script: `scripts/build_standalone.sh` (`--onefile --clean --noconfirm`)
- Gitignore: build/, dist/, *.spec
- Entry point: `main()` in redistribute_tui.py

### Critical Fixes Applied

**1. UI Blocking** - CPU-intensive operations froze event loop

```python
from textual import work  # NOT from textual.worker (ImportError)

@work(thread=True, exclusive=True, exit_on_error=False)
async def _generate_assignments(self) -> None:
    self.call_from_thread(log_widget.write, "Status...")  # Thread-safe UI updates
```

**2. Text Truncation** - Log widget API misuse

- `Log.write()` ignores newlines → use `Log.write_line()` for wrapping
- CSS: `text-wrap: wrap; overflow-x: hidden` required
- Removed obsolete manual `textwrap.fill()` wrapping

**3. Rich Markup** - Log doesn't support markup, switched to RichLog

```python
from textual.widgets import RichLog as TextLog
yield TextLog(id="result", markup=True, wrap=True, auto_scroll=True)
self.call_from_thread(log_widget.write, "[green]Complete![/]")  # RichLog uses write()
```

**4. TYPE_CHECKING** - Runtime NameError for Input/Select (previous session)

```python
from textual.widgets import Input, Select  # Removed TYPE_CHECKING guard
```

**Textual API Gotchas** (training data errors):

- ❌ `from textual.worker import work` → ✅ `from textual import work`
- ❌ `Log(markup=True)` → ✅ `RichLog(markup=True)`
- ❌ `RichLog.write_line()` → ✅ `RichLog.write()`
- Verify imports: `pdm run python -c "from textual import work; print(work)"`

**macOS Splash Screen Limitation**:

- PyInstaller `--splash` incompatible (Tcl/Tk threading restriction)
- Native Swift launcher viable but out of scope (YAGNI)
- Accepted 1-3s startup delay without feedback

### Build Details

- Binary size: 106MB (vs estimated 25-35MB) - includes numpy/scipy/pandas/matplotlib + Python 3.11
- TUI-only build (CLI removed per user request)
- Build time: ~60s
- PyInstaller-safe codebase verified (27 files analyzed, no dynamic imports/sys.path hacks)

### Files Modified

- `pyproject.toml`: PyInstaller dep, numpy/scipy to main, build-standalone script
- `redistribute_tui.py`: @work decorator, RichLog import, write() calls, main() entry
- `workflow_executor.py`: Removed TYPE_CHECKING guard for Input/Select
- `form_layout.py`: RichLog import, CSS `text-wrap: wrap; overflow-x: hidden`
- `build_standalone.sh`: TUI-only (CLI removed)
- `.gitignore`: PyInstaller artifacts
- `.agent/rules/095-textual-tui-patterns.md`: Sections 9-12 (workers, Log vs RichLog, API gotchas)

### Success Criteria ✅

- Build: `pdm run build-standalone` completes, 106MB onefile, ~60s
- Runtime: TUI responsive, background threading works, Rich markup renders, text wraps
- Distribution: No Python required, 1-3s startup
