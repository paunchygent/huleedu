# Notebook & Colab Development Patterns

This rule defines standards for developing Jupyter notebooks in VS Code that are intended to run in hybrid environments (local VS Code connected to local kernels OR remote Colab/containerized kernels).

## 1. Core Principle: Environment Agnosticism

Notebooks must be written to execute successfully regardless of the underlying runtime environment (Host OS, Docker Container, or Google Colab VM).

### 1.1 The "Container Gap"
- **Problem**: When running notebooks in VS Code with certain extensions or remote kernels, the execution context is often a container (e.g., CWD is `/content` or `/workspace`) that **cannot see** the host machine's absolute paths (e.g., `/Users/name/...`).
- **Mandate**: **NEVER** use hardcoded absolute paths from your host machine.
- **Mandate**: **ALWAYS** use dynamic path resolution relative to `Path.cwd()` or the notebook file location.

```python
# ❌ BAD
data_path = "/Users/olof/repos/project/data.csv"

# ✅ GOOD
from pathlib import Path
REPO_ROOT = Path.cwd() # Or robust finding logic
data_path = REPO_ROOT / "data.csv"
```

## 2. Secret Management

Host environment variables (like those in a local `.env` file) do **not** automatically propagate to containerized notebook kernels.

### 2.1 Robust Loading Strategy
Notebooks must implement a "tiered" secret loading strategy:
1. **Attempt 1**: Dynamic search for `.env` (walk up directories).
2. **Attempt 2**: Check existing environment variables (if injected by the runner).
3. **Fallback**: Allow manual injection or hardcoded fallbacks (for specific dev scenarios) if secure/appropriate, or fail gracefully with clear instructions.

```python
# Example Robust Pattern
import os
from pathlib import Path
from dotenv import load_dotenv

def load_secrets():
    # 1. Search for .env
    current = Path.cwd()
    env_path = None
    for _ in range(5):
        if (current / ".env").exists():
            env_path = current / ".env"
            break
        if current.parent == current: break
        current = current.parent
    
    if env_path:
        load_dotenv(env_path, override=True)
        return

    # 2. Fallback for isolated containers (e.g., Colab / Dev Container)
    # If specific critical keys are missing, you might inject them here 
    # OR prompt the user to set them.
    if not os.environ.get("MY_API_KEY"):
        print("⚠️ .env not found. Ensure secrets are set in the runtime environment.")
```

## 3. Dependency Management

The notebook kernel is an **isolated Python environment**. It does NOT share packages with your local `pdm` or `poetry` environment.

- **Mandate**: Use `%pip install` magic commands within the notebook to ensure dependencies are installed into the *active kernel*.
- **Mandate**: Do not rely on `pdm install` run on the host to make packages available to the notebook.

```python
# Cell 1: Setup
%pip install pandas streamlit pyngrok python-dotenv
```

## 4. Process Management (Streamlit/Ngrok)

Notebook cells that spawn background processes (like web servers or tunnels) can leave "zombie" processes running if cells are re-executed.

- **Mandate**: Always explicitly **kill** existing instances of your target process before starting a new one.

```python
import subprocess
from pyngrok import ngrok

# 1. Cleanup first
!pkill -f streamlit
ngrok.kill()

# 2. Start fresh
# ...
```

## 5. File I/O in Containers

When writing files (e.g., generating a `app.py` script for Streamlit):
- **Mandate**: Verify the target directory exists or create it (`mkdir(parents=True)`).
- **Mandate**: Write to `Path.cwd()` or a subdirectory relative to it. Do not attempt to write to host-specific paths.

```python
APP_DIR = Path.cwd()
APP_PATH = APP_DIR / "app.py"
APP_PATH.write_text(code, encoding="utf-8")
```
