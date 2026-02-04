"""Tests for progress.json writer utilities.

These tests verify that the research runner can expose machine-readable progress
signals (processed/total per substage) without relying on parsing logs.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from scripts.ml_training.essay_scoring.logging_utils import ProgressWriter


def test_progress_writer_writes_stage_and_eta(tmp_path: Path) -> None:
    run_dir = tmp_path
    (run_dir / "status.json").write_text(
        json.dumps({"stage": "feature_extraction_train", "state": "running"}), encoding="utf-8"
    )

    writer = ProgressWriter(run_dir, throttle_s=0.0)
    writer.update(
        substage="tier1.spacy",
        processed=5,
        total=10,
        unit="records",
        details={"note": "test"},
        force=True,
    )

    payload = json.loads((run_dir / "progress.json").read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["stage"] == "feature_extraction_train"
    assert payload["substage"] == "tier1.spacy"
    assert payload["processed"] == 5
    assert payload["total"] == 10
    assert payload["unit"] == "records"
    assert payload["percent"] == 50.0
    assert "eta_seconds" in payload
    assert payload["details"]["note"] == "test"
    assert not (run_dir / "progress.json.tmp").exists()


def test_progress_writer_throttles_writes(tmp_path: Path) -> None:
    run_dir = tmp_path
    (run_dir / "status.json").write_text(
        json.dumps({"stage": "cv_feature_store_train_extract", "state": "running"}),
        encoding="utf-8",
    )

    writer = ProgressWriter(run_dir, throttle_s=3600.0)
    writer.update(substage="embedding.fetch_missing", processed=1, total=10, force=True)
    first = json.loads((run_dir / "progress.json").read_text(encoding="utf-8"))

    # Should be throttled: no update without force.
    writer.update(substage="embedding.fetch_missing", processed=2, total=10, force=False)
    second = json.loads((run_dir / "progress.json").read_text(encoding="utf-8"))
    assert second["processed"] == first["processed"]

    # Force should bypass throttle.
    time.sleep(0.01)
    writer.update(substage="embedding.fetch_missing", processed=3, total=10, force=True)
    third = json.loads((run_dir / "progress.json").read_text(encoding="utf-8"))
    assert third["processed"] == 3
