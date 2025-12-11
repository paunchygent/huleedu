---
paths: "**/*.ipynb"
---

# Jupyter Notebook Development Rules (Hybrid/Colab)

**Constraint**: Notebooks must be agnostic to the runtime environment (Host vs. Container/Colab).

1. **Filesystem Isolation (The "Container Gap")**:
    - **NEVER** use hardcoded absolute paths (e.g., `/Users/...`). The kernel is likely in a container (`/content`).
    - **ALWAYS** use dynamic paths relative to `Path.cwd()`.

2. **Secret Management**:
    - Host `.env` files are **NOT** visible to containerized kernels.
    - **Pattern**: Try loading `.env` dynamically; fall back to manual injection or explicit prompts if missing.
    - **Do not** rely on `python-dotenv` finding files in parent directories outside the mount.

3. **Dependencies**:
    - The notebook kernel is isolated from the host's `pdm` environment.
    - **ALWAYS** use `%pip install package` within the notebook to install dependencies.

4. **Process Management**:
    - Explicitly kill background processes (e.g., `ngrok.kill()`, `!pkill -f streamlit`) before starting new ones to prevent zombie processes and port conflicts.

5. **File I/O**:
    - Write files to `Path.cwd()` or ensure target directories exist via `mkdir(parents=True)`.
