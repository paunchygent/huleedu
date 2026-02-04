from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from scripts.ml_training.essay_scoring.logging_utils import (
    mark_run_failed,
    stage_timer,
    update_status,
)


def _read_status(run_dir: Path) -> dict[str, object]:
    return json.loads((run_dir / "status.json").read_text(encoding="utf-8"))


def test_stage_timer_marks_failed_on_keyboard_interrupt(tmp_path: Path) -> None:
    logger = logging.getLogger("test_stage_timer_marks_failed_on_keyboard_interrupt")
    with pytest.raises(KeyboardInterrupt):
        with stage_timer(tmp_path, logger, "feature_extraction_train", records=123):
            raise KeyboardInterrupt

    payload = _read_status(tmp_path)
    assert payload["stage"] == "feature_extraction_train"
    assert payload["state"] == "failed"
    assert payload["failure_reason"] == "exception"
    assert payload["error_type"] == "KeyboardInterrupt"
    assert "elapsed_seconds" in payload


def test_signal_marker_is_not_overwritten_by_stage_timer(tmp_path: Path) -> None:
    logger = logging.getLogger("test_signal_marker_is_not_overwritten_by_stage_timer")
    with pytest.raises(KeyboardInterrupt):
        with stage_timer(tmp_path, logger, "feature_extraction_train", records=123):
            mark_run_failed(tmp_path, reason="signal", signal_name="SIGINT")
            raise KeyboardInterrupt

    payload = _read_status(tmp_path)
    assert payload["stage"] == "feature_extraction_train"
    assert payload["state"] == "failed"
    assert payload["failure_reason"] == "signal"
    assert payload["signal"] == "SIGINT"
    assert "elapsed_seconds" in payload


def test_mark_run_failed_uses_existing_stage_when_present(tmp_path: Path) -> None:
    update_status(tmp_path, stage="feature_extraction_train", state="running")
    mark_run_failed(tmp_path, reason="signal", signal_name="SIGTERM")

    payload = _read_status(tmp_path)
    assert payload["stage"] == "feature_extraction_train"
    assert payload["state"] == "failed"
    assert payload["failure_reason"] == "signal"
    assert payload["signal"] == "SIGTERM"
