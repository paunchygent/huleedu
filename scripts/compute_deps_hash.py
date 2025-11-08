from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[1]

LIB_DIRS = [
    REPO_ROOT / "libs/common_core",
    REPO_ROOT / "libs/huleedu_service_libs",
    REPO_ROOT / "libs/huleedu_nlp_shared",
]

SERVICE_DIR = REPO_ROOT / "services"

FILES_ALWAYS = [
    REPO_ROOT / "pyproject.toml",
    REPO_ROOT / "pdm.lock",
    REPO_ROOT / "Dockerfile.deps",
]

SERVICE_NAMES = sorted(
    p.name for p in SERVICE_DIR.iterdir() if p.is_dir() and not p.name.startswith("__")
)


def iter_files() -> Iterable[Path]:
    for path in FILES_ALWAYS:
        if path.exists():
            yield path
    for lib in LIB_DIRS:
        for sub in (lib / "pyproject.toml", lib / "pdm.lock"):
            if sub.exists():
                yield sub
        src = lib / "src"
        if src.exists():
            for file in sorted(src.rglob("*")):
                if file.is_file():
                    yield file
    for name in SERVICE_NAMES:
        svc_dir = SERVICE_DIR / name
        for filename in ("pyproject.toml", "pdm.lock"):
            candidate = svc_dir / filename
            if candidate.exists():
                yield candidate


def compute_hash() -> str:
    digest = hashlib.sha256()
    for path in iter_files():
        rel = path.relative_to(REPO_ROOT)
        digest.update(str(rel).encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
    return digest.hexdigest()[:16]


if __name__ == "__main__":
    print(compute_hash())
