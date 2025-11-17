# Cursor AI Extensions Quick Reference

## Required Extensions for HuleEdu Development

### 🔧 Core Extensions (REQUIRED)

| Extension | ID | Purpose | Status |
|-----------|----|---------| -------|
| **Ruff** | `ms-python.ruff` | Linting, formatting, import sorting | ✅ REQUIRED |
| **MyPy Type Checker** | `ms-python.mypy-type-checker` | Type checking | ✅ REQUIRED |
| **Python** | `ms-python.python` | Core Python support | ✅ REQUIRED |
| **Pylance** | `ms-python.vscode-pylance` | Enhanced IntelliSense | 🔄 RECOMMENDED |

### 📦 Installation Commands

```bash
# Install all required extensions at once
ext install charliermarsh.ruff ms-python.mypy-type-checker ms-python.python ms-python.vscode-pylance
```

Or install individually:

```bash
ext install charliermarsh.ruff
ext install ms-python.mypy-type-checker
ext install ms-python.python
ext install ms-python.vscode-pylance
```

### ⚙️ Key Settings Verification

After installation, verify these settings in your `.vscode/settings.json`:

```json
{
  // Ruff as default formatter
  "[python]": {
    "editor.defaultFormatter": "charliermarsh.ruff"
  },

  // Ruff native server enabled
  "ruff.nativeServer": "on",

  // MyPy workspace checking
  "mypy-type-checker.reportingScope": "workspace",

  // Disable conflicting tools
  "python.linting.enabled": false
}
```

### 🚀 Quick Test

1. **Open any Python file**
2. **Add formatting issues** (extra spaces, wrong imports)
3. **Save file** (`Ctrl+S` / `Cmd+S`)
4. **Expected**: Auto-format + import organization
5. **Add type error** (assign string to int)
6. **Expected**: Red squiggles with MyPy errors

### 🔍 Status Bar Indicators

When working correctly, you should see:

- **Ruff (native)** - Ruff server running
- **MyPy** - Type checker active
- **Python 3.11.x** - Correct interpreter

### 🛠️ Troubleshooting

| Issue | Solution |
|-------|----------|
| Ruff not formatting | Check `"editor.defaultFormatter": "charliermarsh.ruff"` |
| MyPy not working | Restart: `Ctrl+Shift+P` → "MyPy: Restart Server" |
| Wrong Python version | Set `"python.defaultInterpreterPath": "./.venv/bin/python"` |
| Multiple formatters | Disable: `"python.linting.enabled": false` |

### 📋 Command Palette Quick Actions

| Command | Shortcut | Purpose |
|---------|----------|---------|
| `Ruff: Fix all auto-fixable problems` | - | Fix all Ruff issues |
| `Ruff: Format Document` | - | Format current file |
| `MyPy: Restart Server` | - | Restart type checker |
| `Python: Select Interpreter` | - | Choose Python version |

### 🎯 PDM Integration

Your IDE settings mirror these PDM commands:

| PDM Command | IDE Equivalent |
|-------------|----------------|
| `pdm run format-all` | Format on Save |
| `pdm run lint-all` | Problems Panel (Ruff) |
| `pdm run typecheck-all` | Problems Panel (MyPy) |

## 🚨 Deprecated Settings (2025 Update)

**IMPORTANT**: Remove these deprecated Ruff settings from your `settings.json`:

```json
// ❌ REMOVE THESE DEPRECATED SETTINGS
"ruff.format.args": ["--force-exclude"],
"ruff.lint.args": ["--force-exclude"],
"ruff.showNotifications": "onError"
```

**Why deprecated?**: The native Rust language server (ruff server) handles these automatically and more efficiently.

**Updated settings** for 2025:

```json
// ✅ USE THESE MODERN SETTINGS
"ruff.nativeServer": "auto",  // Uses native server by default
"ruff.logLevel": "info",      // Replaces showNotifications
// format.args and lint.args are handled automatically
```

---

**✅ Setup Complete**: Your Cursor AI now enforces the same code quality as your CI/CD pipeline!
