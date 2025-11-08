"""Environment helpers for ENG5 NP runner."""

from __future__ import annotations

import subprocess
from pathlib import Path


def repo_root_from_package() -> Path:
    """Resolve the repository root relative to this package."""

    return Path(__file__).resolve().parents[3]


def gather_git_sha(repo_root: Path) -> str:
    """Return the current HEAD SHA (or ``UNKNOWN`` on failure)."""

    try:
        result = subprocess.check_output(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            stderr=subprocess.STDOUT,
        )
    except subprocess.CalledProcessError:
        return "UNKNOWN"
    return result.decode().strip()
