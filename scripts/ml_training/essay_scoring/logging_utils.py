"""Logging helpers for the essay scoring research pipeline."""

from __future__ import annotations

import json
import logging
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from rich.logging import RichHandler


def configure_console_logging(level: int = logging.WARNING) -> None:
    """Configure Rich-backed console logging.

    Notes:
    - Console logging defaults to WARNING to keep large research runs readable.
    - File logging is handled separately via `run_file_logger` and should retain INFO.
    """

    handler = RichHandler(rich_tracebacks=True, markup=True)
    handler.setLevel(level)

    root_level = min(level, logging.INFO)
    logging.basicConfig(
        level=root_level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[handler],
    )


@contextmanager
def run_file_logger(log_path: Path, level: int = logging.INFO):
    """Attach a file logger for the duration of a run."""

    log_path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s"))
    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    try:
        yield
    finally:
        root_logger.removeHandler(handler)
        handler.close()


def update_status(run_dir: Path, stage: str, state: str, **extra: object) -> None:
    """Write a status marker for the current run stage."""

    payload = {
        "stage": stage,
        "state": state,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if extra:
        payload.update(extra)
    (run_dir / "status.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")


@contextmanager
def stage_timer(run_dir: Path, logger: logging.Logger, stage: str, **extra: object):
    """Log and time a stage, updating the run status."""

    update_status(run_dir, stage=stage, state="running", **extra)
    start = time.monotonic()
    logger.info("Stage start: %s", stage)
    try:
        yield
    finally:
        elapsed = time.monotonic() - start
        logger.info("Stage complete: %s (%.2fs)", stage, elapsed)
        update_status(
            run_dir,
            stage=stage,
            state="completed",
            elapsed_seconds=round(elapsed, 2),
        )


class ProgressLogger:
    """Log progress and ETA for iterative stages."""

    def __init__(self, logger: logging.Logger, label: str, total: int, every: int = 1) -> None:
        self._logger = logger
        self._label = label
        self._total = total
        self._every = max(1, every)
        self._start = time.monotonic()

    def update(self, index: int) -> None:
        if self._total == 0:
            return
        current = index + 1
        if current % self._every != 0 and current != self._total:
            return
        elapsed = time.monotonic() - self._start
        rate = current / elapsed if elapsed > 0 else 0.0
        remaining = (self._total - current) / rate if rate > 0 else 0.0
        percent = (current / self._total) * 100
        self._logger.info(
            "%s progress %d/%d (%.1f%%, %.2f it/s, ETA %.1fs)",
            self._label,
            current,
            self._total,
            percent,
            rate,
            remaining,
        )
