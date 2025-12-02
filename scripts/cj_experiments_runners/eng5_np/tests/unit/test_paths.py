"""Unit tests for ENG5 NP RunnerPaths helpers."""

from __future__ import annotations

import os
from pathlib import Path

from scripts.cj_experiments_runners.eng5_np.paths import RunnerPaths


def test_from_repo_root_uses_default_anchor_dir(monkeypatch, tmp_path: Path) -> None:
    """When no override is set, anchor_docs_dir points to anchor_essays."""
    monkeypatch.delenv("ENG5_ANCHOR_DIR_OVERRIDE", raising=False)

    repo_root = tmp_path
    role_models_root = repo_root / "test_uploads" / "ANCHOR ESSAYS" / "ROLE_MODELS_ENG5_NP_2016"
    (role_models_root / "anchor_essays").mkdir(parents=True, exist_ok=True)

    paths = RunnerPaths.from_repo_root(repo_root)

    assert paths.anchor_docs_dir == role_models_root / "anchor_essays"


def test_from_repo_root_honors_anchor_dir_override(monkeypatch, tmp_path: Path) -> None:
    """ENG5_ANCHOR_DIR_OVERRIDE takes precedence over default anchor directory."""
    override_dir = tmp_path / "custom_anchors"
    override_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("ENG5_ANCHOR_DIR_OVERRIDE", os.fspath(override_dir))

    repo_root = tmp_path
    paths = RunnerPaths.from_repo_root(repo_root)

    assert paths.anchor_docs_dir == override_dir
