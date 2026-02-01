"""Environment helpers for the essay scoring research pipeline."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


def repo_root_from_package() -> Path:
    """Resolve the repository root relative to this package."""

    return Path(__file__).resolve().parents[3]


def ensure_matplotlib_cache_dir() -> Path:
    """Ensure Matplotlib uses a writable cache directory."""

    cache_root = repo_root_from_package() / "output" / "essay_scoring" / ".cache"
    mpl_cache = cache_root / "matplotlib"
    lt_cache = cache_root / "language_tool_python"
    mpl_cache.mkdir(parents=True, exist_ok=True)
    lt_cache.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("XDG_CACHE_HOME", str(cache_root))
    os.environ.setdefault("MPLCONFIGDIR", str(mpl_cache))
    os.environ.setdefault("LTP_PATH", str(lt_cache))
    return mpl_cache


def gather_git_sha(repo_root: Path) -> str:
    """Return the current HEAD SHA (or ``UNKNOWN`` on failure)."""

    try:
        result = subprocess.check_output(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            stderr=subprocess.STDOUT,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "UNKNOWN"
    return result.decode().strip()


ensure_matplotlib_cache_dir()
