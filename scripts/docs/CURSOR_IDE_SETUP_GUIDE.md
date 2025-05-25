# Cursor AI IDE Setup Guide for HuleEdu

## Overview

This guide configures Cursor AI (VS Code fork) to **exactly mirror** your PDM `pyproject.toml` linting configuration. Your IDE will run the same Ruff and MyPy settings as your command-line tools.

## Required Extensions

Install these extensions in Cursor AI:

### 1. **Ruff Extension** (REQUIRED)

- **Extension ID**: `charliermarsh.ruff`
- **Latest Version**: v2025.22.0+ (January 2025)
- **Install Command**: `ext install charliermarsh.ruff`
- **Purpose**: Provides Ruff linting and formatting (replaces Black, isort, Flake8)
- **Key Feature**: Uses native Rust language server (ruff server) for enhanced performance

### 2. **MyPy Type Checker** (REQUIRED)

- **Extension ID**: `ms-python.mypy-type-checker`
- **Install Command**: `ext install ms-python.mypy-type-checker`
- **Purpose**: Provides MyPy type checking integration

### 3. **Python Extension** (REQUIRED)

- **Extension ID**: `ms-python.python`
- **Install Command**: `ext install ms-python.python`
- **Purpose**: Core Python language support

### 4. **Pylance** (RECOMMENDED)

- **Extension ID**: `ms-python.vscode-pylance`
- **Install Command**: `ext install ms-python.vscode-pylance`
- **Purpose**: Enhanced Python IntelliSense and type checking

## Installation Commands

Run these in Cursor AI's Command Palette (`Ctrl+Shift+P` / `Cmd+Shift+P`):

``` bash
ext install charliermarsh.ruff
ext install ms-python.mypy-type-checker
ext install ms-python.python
ext install ms-python.vscode-pylance
```

## Workspace Configuration

### Step 1: Create `.vscode` Directory

```bash
mkdir -p .vscode
```

### Step 2: Create `settings.json`

Create `.vscode/settings.json` with the following configuration that **exactly mirrors** your `pyproject.toml`:

```json
{
  // ===== PYTHON CONFIGURATION =====
  "[python]": {
    "editor.defaultFormatter": "charliermarsh.ruff",
    "editor.formatOnSave": true,
    "editor.codeActionsOnSave": {
      "source.fixAll.ruff": "explicit",
      "source.organizeImports.ruff": "explicit"
    }
  },

  // ===== RUFF CONFIGURATION (mirrors pyproject.toml) =====
  "ruff.nativeServer": "on",
  "ruff.lineLength": 100,
  "ruff.lint.select": ["E", "W", "F", "I"],
  "ruff.lint.ignore": ["E203"],
  "ruff.format.args": ["--force-exclude"],
  "ruff.lint.args": ["--force-exclude"],
  "ruff.organizeImports": true,
  "ruff.showNotifications": "onError",

  // ===== MYPY CONFIGURATION (mirrors pyproject.toml) =====
  "mypy-type-checker.reportingScope": "workspace",
  "mypy-type-checker.preferDaemon": true,
  "mypy-type-checker.args": [
    "--config-file=pyproject.toml",
    "--python-version=3.11",
    "--warn-return-any",
    "--warn-unused-configs",
    "--check-untyped-defs",
    "--explicit-package-bases",
    "--namespace-packages"
  ],
  "mypy-type-checker.severity": {
    "error": "Error",
    "note": "Information"
  },

  // ===== PYTHON INTERPRETER =====
  "python.defaultInterpreterPath": "./.venv/bin/python",
  "python.terminal.activateEnvironment": true,

  // ===== EDITOR SETTINGS =====
  "editor.rulers": [100],
  "editor.tabSize": 4,
  "editor.insertSpaces": true,
  "editor.trimAutoWhitespace": true,
  "files.trimTrailingWhitespace": true,
  "files.insertFinalNewline": true,

  // ===== EXCLUDE PATTERNS (mirrors .gitignore) =====
  "files.exclude": {
    "**/__pycache__": true,
    "**/.mypy_cache": true,
    "**/.pytest_cache": true,
    "**/.ruff_cache": true,
    "**/.pdm-build": true,
    ".venv": true
  },

  // ===== SEARCH EXCLUDE =====
  "search.exclude": {
    "**/__pycache__": true,
    "**/.mypy_cache": true,
    "**/.pytest_cache": true,
    "**/.ruff_cache": true,
    "**/.pdm-build": true,
    ".venv": true,
    "pdm.lock": true
  },

  // ===== JUPYTER NOTEBOOK SUPPORT =====
  "notebook.formatOnSave.enabled": true,
  "notebook.codeActionsOnSave": {
    "notebook.source.fixAll.ruff": "explicit",
    "notebook.source.organizeImports.ruff": "explicit"
  },

  // ===== DISABLE CONFLICTING EXTENSIONS =====
  "python.linting.enabled": false,
  "python.linting.pylintEnabled": false,
  "python.linting.flake8Enabled": false,
  "python.formatting.provider": "none",
  "python.formatting.blackPath": "",
  "isort.check": false,

  // ===== TERMINAL INTEGRATION =====
  "terminal.integrated.env.osx": {
    "PDM_IGNORE_SAVED_PYTHON": "1"
  },
  "terminal.integrated.env.linux": {
    "PDM_IGNORE_SAVED_PYTHON": "1"
  }
}
```

## Configuration Mapping

### Your `pyproject.toml` → Cursor Settings

| pyproject.toml Setting | Cursor Setting | Value |
|------------------------|----------------|-------|
| `[tool.ruff] line-length = 100` | `"ruff.lineLength"` | `100` |
| `[tool.ruff] target-version = "py311"` | `"mypy-type-checker.args"` | `"--python-version=3.11"` |
| `[tool.ruff.lint] select = ["E", "W", "F", "I"]` | `"ruff.lint.select"` | `["E", "W", "F", "I"]` |
| `[tool.ruff.lint] ignore = ["E203"]` | `"ruff.lint.ignore"` | `["E203"]` |
| `[tool.ruff.format] quote-style = "double"` | Built into Ruff | Auto-detected |
| `[tool.mypy] python_version = "3.11"` | `"mypy-type-checker.args"` | `"--python-version=3.11"` |
| `[tool.mypy] warn_return_any = true` | `"mypy-type-checker.args"` | `"--warn-return-any"` |
| `[tool.mypy] check_untyped_defs = true` | `"mypy-type-checker.args"` | `"--check-untyped-defs"` |

## Verification Steps

### 1. Test Ruff Integration

1. Open any Python file in your project
2. Make a formatting error (e.g., add extra spaces)
3. Save the file (`Ctrl+S` / `Cmd+S`)
4. **Expected**: File should auto-format according to your Ruff rules

### 2. Test MyPy Integration

1. Open a Python file with type annotations
2. Add a type error (e.g., assign string to int variable)
3. **Expected**: Red squiggles should appear with MyPy error messages

### 3. Test Import Organization

1. Add some imports in wrong order
2. Save the file
3. **Expected**: Imports should auto-organize according to your Ruff rules

### 4. Verify Command Equivalence

Run these commands and compare output:

```bash
# Command line
pdm run lint-all
pdm run format-all
pdm run typecheck-all

# Should match what you see in Cursor's Problems panel
```

## Advanced Configuration

### Per-File Ignores

Your `pyproject.toml` includes per-file ignores:

```toml
[tool.ruff.lint.per-file-ignores]
"services/*/app.py" = ["E402"]
"services/*/worker.py" = ["E402"]
```

These are automatically respected by the Ruff extension when using `--config-file=pyproject.toml`.

### MyPy Module Overrides

Your MyPy overrides for external libraries are automatically applied:

```toml
[[tool.mypy.overrides]]
module = ["aiokafka.*", "aiofiles.*"]
ignore_missing_imports = true
```

## Troubleshooting

### Issue: Ruff Not Finding Configuration

**Problem**: Ruff uses default settings instead of `pyproject.toml`

**Solution**:

1. Ensure `pyproject.toml` is in workspace root
2. Check Ruff output panel: `View` → `Output` → Select "Ruff"
3. Verify configuration path in logs

### Issue: MyPy Not Using Workspace Settings

**Problem**: MyPy shows different errors than command line

**Solution**:

1. Set `"mypy-type-checker.reportingScope": "workspace"`
2. Restart MyPy daemon: `Ctrl+Shift+P` → "MyPy: Restart Server"
3. Check MyPy output panel for configuration loading

### Issue: Conflicting Formatters

**Problem**: Multiple formatters fighting over Python files

**Solution**:

1. Disable Python extension's built-in linting:

   ```json
   "python.linting.enabled": false
   ```

2. Set Ruff as default formatter:

   ```json
   "[python]": {
     "editor.defaultFormatter": "charliermarsh.ruff"
   }
   ```

### Issue: Virtual Environment Not Detected

**Problem**: Extensions can't find PDM virtual environment

**Solution**:

1. Set explicit interpreter path:

   ```json
   "python.defaultInterpreterPath": "./.venv/bin/python"
   ```

2. Or use Command Palette: `Python: Select Interpreter`

## Status Bar Indicators

When properly configured, you should see:

- **Ruff (native)**: Indicates Ruff native server is running
- **MyPy**: Shows MyPy daemon status
- **Python 3.11.x**: Shows correct Python interpreter

## Performance Tips

### For Large Codebases

```json
{
  "mypy-type-checker.reportingScope": "file",  // Only check open files
  "ruff.showNotifications": "off",             // Reduce noise
  "python.analysis.autoImportCompletions": false  // Faster completions
}
```

### For Maximum Accuracy

```json
{
  "mypy-type-checker.reportingScope": "workspace",  // Check entire workspace
  "mypy-type-checker.preferDaemon": true,           // Use daemon for speed
  "ruff.showNotifications": "onError"               // Show important issues
}
```

## Integration with PDM Scripts

Your Cursor settings will run the same checks as these PDM commands:

- `pdm run format-all` ↔ Format on Save in Cursor
- `pdm run lint-all` ↔ Ruff linting in Problems panel
- `pdm run typecheck-all` ↔ MyPy type checking in Problems panel

## Summary

With this configuration:

✅ **Ruff** handles formatting, linting, and import sorting
✅ **MyPy** provides type checking with your exact configuration
✅ **Settings mirror** your `pyproject.toml` exactly
✅ **No conflicts** with other Python extensions
✅ **PDM integration** works seamlessly

Your IDE now enforces the same code quality standards as your CI/CD pipeline!
