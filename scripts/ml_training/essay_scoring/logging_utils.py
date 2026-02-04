"""Logging helpers for the essay scoring research pipeline.

This module provides:
- Console + file logging setup for long-running research jobs (`configure_console_logging`,
  `run_file_logger`).
- Run-level stage markers (`status.json`) via `stage_timer` / `update_status`.
- Lightweight progress/ETA reporting:
  - human-readable log lines via `ProgressLogger`
  - machine-readable counters via `ProgressWriter` (`progress.json`)

`progress.json` is intended for external monitoring (tailing a single JSON file) without relying
on parsing `run.log`.
"""

from __future__ import annotations

import faulthandler
import json
import logging
import os
import signal
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from io import TextIOBase, UnsupportedOperation
from pathlib import Path

from rich.logging import RichHandler


def configure_console_logging(level: int | None = None) -> None:
    """Configure Rich-backed console logging.

    Notes:
    - Console logging defaults to WARNING for TTY sessions to keep large research runs readable.
    - When stdout/stderr are redirected (nohup, CI), console logging defaults to INFO so the
      driver log has useful progress output.
    - When stderr is not a TTY, use a plain `StreamHandler` (no Rich formatting) to keep the
      driver log greppable.
    - You can override the default with `ESSAY_SCORING_CONSOLE_LOG_LEVEL` (e.g. INFO, DEBUG).
    - File logging is handled separately via `run_file_logger` and should retain INFO.
    """

    if level is None:
        env_level = os.getenv("ESSAY_SCORING_CONSOLE_LOG_LEVEL")
        if env_level:
            resolved = logging.getLevelName(env_level.upper())
            if isinstance(resolved, int):
                level = resolved
            else:
                level = logging.INFO
        else:
            level = logging.WARNING if sys.stderr.isatty() else logging.INFO

    if sys.stderr.isatty():
        handler: logging.Handler = RichHandler(rich_tracebacks=True, markup=True)
        handler.setFormatter(logging.Formatter("%(message)s"))
    else:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
    handler.setLevel(level)

    root_level = min(level, logging.INFO)
    logging.basicConfig(
        level=root_level,
        handlers=[handler],
    )


def _read_current_stage(run_dir: Path) -> str:
    status_path = run_dir / "status.json"
    if not status_path.exists():
        return "unknown"
    try:
        payload = json.loads(status_path.read_text(encoding="utf-8"))
    except Exception:
        return "unknown"
    stage = payload.get("stage")
    if not stage:
        return "unknown"
    return str(stage)


def _read_status_payload(run_dir: Path) -> dict[str, object] | None:
    status_path = run_dir / "status.json"
    if not status_path.exists():
        return None
    try:
        payload = json.loads(status_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def mark_run_failed(
    run_dir: Path,
    *,
    stage: str | None = None,
    reason: str,
    signal_name: str | None = None,
    error_type: str | None = None,
    message: str | None = None,
    **extra: object,
) -> None:
    """Best-effort write of a failed run status marker.

    This is used both for normal exception handling and for SIGINT/SIGTERM so
    interrupted runs don't look like they are still running.
    """

    resolved_stage = stage or _read_current_stage(run_dir)
    payload_extra: dict[str, object] = {"failure_reason": reason}
    if signal_name:
        payload_extra["signal"] = signal_name
    if error_type:
        payload_extra["error_type"] = error_type
    if message:
        payload_extra["message"] = message
    if extra:
        payload_extra.update(extra)
    update_status(run_dir, stage=resolved_stage, state="failed", **payload_extra)


class _Tee(TextIOBase):
    def __init__(self, *streams: TextIOBase) -> None:
        self._streams = [stream for stream in streams if stream is not None]

    def write(self, s: str) -> int:
        for stream in self._streams:
            stream.write(s)
        return len(s)

    def flush(self) -> None:
        for stream in self._streams:
            stream.flush()

    def writable(self) -> bool:
        return True

    def isatty(self) -> bool:
        return any(getattr(stream, "isatty", lambda: False)() for stream in self._streams)

    def fileno(self) -> int:
        for stream in self._streams:
            fileno = getattr(stream, "fileno", None)
            if fileno is None:
                continue
            try:
                return int(fileno())
            except UnsupportedOperation:
                continue
        raise UnsupportedOperation("fileno")

    @property
    def encoding(self) -> str | None:
        for stream in self._streams:
            encoding = getattr(stream, "encoding", None)
            if encoding is not None:
                return encoding
        return None


@contextmanager
def run_file_logger(log_path: Path, level: int = logging.INFO):
    """Attach a file logger for the duration of a run."""

    log_path.parent.mkdir(parents=True, exist_ok=True)
    run_dir = log_path.parent
    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s"))
    root_logger = logging.getLogger()
    root_logger.addHandler(handler)

    stderr_path = log_path.with_name("stderr.log")
    fault_path = log_path.with_name("fault.log")
    original_stderr = sys.stderr
    stderr_handle = stderr_path.open("w", encoding="utf-8")
    fault_handle = fault_path.open("w", encoding="utf-8")

    sys.stderr = _Tee(original_stderr, stderr_handle)
    was_enabled = faulthandler.is_enabled()
    faulthandler.enable(file=fault_handle, all_threads=True)

    dump_enabled = False
    try:
        faulthandler.dump_traceback_later(600, repeat=True, file=fault_handle)
        dump_enabled = True
    except RuntimeError:
        dump_enabled = False
    sigusr1_registered = False
    try:
        faulthandler.register(signal.SIGUSR1, file=fault_handle, all_threads=True)
        sigusr1_registered = True
    except (ValueError, AttributeError, RuntimeError):
        pass

    prev_sigint = signal.getsignal(signal.SIGINT)
    prev_sigterm = signal.getsignal(signal.SIGTERM)
    sig_handlers_installed = False

    def _handle_interrupt(signum: int, _frame: object) -> None:
        sig = signal.Signals(signum)
        mark_run_failed(run_dir, reason="signal", signal_name=sig.name)
        if sig == signal.SIGINT:
            raise KeyboardInterrupt
        raise SystemExit(128 + signum)

    try:
        signal.signal(signal.SIGINT, _handle_interrupt)
        signal.signal(signal.SIGTERM, _handle_interrupt)
        sig_handlers_installed = True
    except Exception:
        # Signal registration can fail in some embedded environments; treat as best-effort.
        sig_handlers_installed = False

    try:
        yield
    finally:
        if sig_handlers_installed:
            try:
                signal.signal(signal.SIGINT, prev_sigint)
            except Exception:
                pass
            try:
                signal.signal(signal.SIGTERM, prev_sigterm)
            except Exception:
                pass
        if dump_enabled:
            try:
                faulthandler.cancel_dump_traceback_later()
            except RuntimeError:
                pass
        if sigusr1_registered:
            try:
                faulthandler.unregister(signal.SIGUSR1)
            except RuntimeError:
                pass
        try:
            faulthandler.disable()
        except RuntimeError:
            pass
        if was_enabled:
            try:
                faulthandler.enable(file=sys.__stderr__, all_threads=True)
            except UnsupportedOperation:
                pass
        sys.stderr = original_stderr
        stderr_handle.close()
        fault_handle.close()
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


class ProgressWriter:
    """Write a throttled, atomic progress counter file (`progress.json`) for monitoring.

    This is intentionally small and low-risk:
    - writes are throttled (default: 0.5s) to avoid IO overhead during tight loops
    - writes are atomic (write temp file, then replace)
    - payload is stable JSON intended for shell tooling (`jq`, file watchers, dashboards)

    The file is updated with *substage* counters (processed/total) and optionally includes a
    derived ETA from the first update time for that substage.
    """

    def __init__(
        self,
        run_dir: Path,
        *,
        filename: str = "progress.json",
        throttle_s: float = 0.5,
    ) -> None:
        self._run_dir = run_dir
        self._path = run_dir / filename
        self._tmp_path = run_dir / f"{filename}.tmp"
        self._throttle_s = max(0.0, float(throttle_s))
        self._last_write_monotonic: float | None = None
        self._substage_start_monotonic: dict[str, float] = {}

    def update(
        self,
        *,
        substage: str,
        processed: int,
        total: int,
        unit: str = "items",
        details: dict[str, object] | None = None,
        force: bool = False,
    ) -> None:
        if total < 0 or processed < 0:
            raise ValueError("processed/total must be non-negative")
        if processed > total:
            processed = total

        now = time.monotonic()
        if not force and self._last_write_monotonic is not None:
            if now - self._last_write_monotonic < self._throttle_s:
                return

        if substage not in self._substage_start_monotonic:
            self._substage_start_monotonic[substage] = now

        stage = _read_current_stage(self._run_dir)
        started = self._substage_start_monotonic[substage]
        elapsed = now - started
        rate = processed / elapsed if elapsed > 0 and processed > 0 else 0.0
        remaining = total - processed
        eta = remaining / rate if rate > 0 else 0.0
        percent = (processed / total) * 100.0 if total > 0 else 0.0

        payload: dict[str, object] = {
            "schema_version": 1,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "stage": stage,
            "substage": substage,
            "state": "completed" if processed >= total and total > 0 else "running",
            "processed": int(processed),
            "total": int(total),
            "unit": unit,
            "percent": round(percent, 2),
            "rate_per_s": round(rate, 4),
            "eta_seconds": round(eta, 2),
        }
        if details:
            payload["details"] = details

        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._tmp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        self._tmp_path.replace(self._path)
        self._last_write_monotonic = now


@contextmanager
def stage_timer(run_dir: Path, logger: logging.Logger, stage: str, **extra: object):
    """Log and time a stage, updating the run status."""

    update_status(run_dir, stage=stage, state="running", **extra)
    start = time.monotonic()
    logger.info("Stage start: %s", stage)
    try:
        yield
    except BaseException as exc:
        elapsed = time.monotonic() - start
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            logger.warning("Stage interrupted: %s", stage)
        else:
            logger.exception("Stage failed: %s", stage)

        existing = _read_status_payload(run_dir)
        if (
            existing is not None
            and existing.get("state") == "failed"
            and existing.get("failure_reason") == "signal"
        ):
            existing_stage = str(existing.get("stage") or stage)
            preserved = {
                k: v for k, v in existing.items() if k not in {"stage", "state", "timestamp"}
            }
            preserved.setdefault("elapsed_seconds", round(elapsed, 2))
            update_status(run_dir, stage=existing_stage, state="failed", **preserved)
            raise

        mark_run_failed(
            run_dir,
            stage=stage,
            reason="exception",
            error_type=type(exc).__name__,
            elapsed_seconds=round(elapsed, 2),
        )
        raise
    else:
        elapsed = time.monotonic() - start
        logger.info("Stage complete: %s (%.2fs)", stage, elapsed)
        update_status(run_dir, stage=stage, state="completed", elapsed_seconds=round(elapsed, 2))


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
