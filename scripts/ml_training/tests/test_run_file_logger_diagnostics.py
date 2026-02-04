import logging
import sys
from pathlib import Path

from scripts.ml_training.essay_scoring.logging_utils import run_file_logger


def test_run_file_logger_writes_stderr_and_creates_fault_log(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    log_path = run_dir / "run.log"

    original_stderr = sys.stderr
    logger = logging.getLogger(__name__)

    with run_file_logger(log_path):
        logger.info("hello from logger")
        print("hello from stderr", file=sys.stderr)
        sys.stderr.flush()

    assert sys.stderr is original_stderr

    assert log_path.exists()
    assert (run_dir / "stderr.log").exists()
    assert (run_dir / "fault.log").exists()

    assert "hello from stderr" in (run_dir / "stderr.log").read_text(encoding="utf-8")
