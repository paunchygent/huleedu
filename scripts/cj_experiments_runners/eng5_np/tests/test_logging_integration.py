"""Integration test for ENG5 NP runner file-based logging.

Validates that execute mode creates persistent log files with proper:
- Directory structure (.claude/research/data/eng5_np_2016/logs/)
- File naming pattern (eng5-{batch_id}-{timestamp}.log)
- Structured log content (JSON lines with correlation context)
- Log rotation configuration (100MB per file, 10 backups)
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path

import pytest
from common_core.domain_enums import CourseCode, Language

from scripts.cj_experiments_runners.eng5_np.logging_support import configure_execute_logging
from scripts.cj_experiments_runners.eng5_np.settings import RunnerMode, RunnerSettings


@pytest.fixture
def test_settings() -> RunnerSettings:
    """Create test settings for execute mode logging."""
    return RunnerSettings(
        assignment_id=uuid.uuid4(),
        course_id=uuid.uuid4(),
        grade_scale="test_scale",
        mode=RunnerMode.EXECUTE,
        use_kafka=False,
        output_dir=Path("/tmp/test_output"),
        runner_version="test",
        git_sha="test_sha",
        batch_uuid=uuid.uuid4(),
        batch_id="TEST-BATCH-001",
        user_id=str(uuid.uuid4()),
        org_id=str(uuid.uuid4()),
        course_code=CourseCode.ENG5,
        language=Language.ENGLISH,
        correlation_id=uuid.uuid4(),
        kafka_bootstrap="localhost:9092",
        kafka_client_id="test-client",
        content_service_url="http://localhost:8000",
    )


@pytest.fixture
def cleanup_log_dir():
    """Cleanup test log directory after test."""
    log_dir = Path(".claude/research/data/eng5_np_2016/logs")
    yield
    # Cleanup test log files after test
    if log_dir.exists():
        for log_file in log_dir.glob("eng5-TEST-BATCH-*.log*"):
            log_file.unlink()


def test_execute_logging_creates_log_directory(test_settings: RunnerSettings, cleanup_log_dir):
    """Test that execute mode logging creates the log directory."""
    log_dir = Path(".claude/research/data/eng5_np_2016/logs")

    # Configure logging (creates directory)
    configure_execute_logging(settings=test_settings, verbose=False)

    # Verify directory was created
    assert log_dir.exists()
    assert log_dir.is_dir()


def test_execute_logging_creates_log_file_with_correct_pattern(
    test_settings: RunnerSettings, cleanup_log_dir
):
    """Test that execute mode creates log file with correct naming pattern."""
    log_dir = Path(".claude/research/data/eng5_np_2016/logs")

    # Configure logging
    configure_execute_logging(settings=test_settings, verbose=False)

    # Find log file matching pattern
    log_files = list(log_dir.glob(f"eng5-{test_settings.batch_id}-*.log"))

    assert len(log_files) >= 1, "Expected at least one log file to be created"

    log_file = log_files[0]
    assert log_file.name.startswith(f"eng5-{test_settings.batch_id}-")
    assert log_file.name.endswith(".log")

    # Validate timestamp format (YYYYMMDD_HHMMSS)
    timestamp_part = log_file.stem.split("-")[-1]
    assert len(timestamp_part) == 15  # YYYYMMDD_HHMMSS
    assert "_" in timestamp_part

    # Verify timestamp can be parsed
    try:
        datetime.strptime(timestamp_part, "%Y%m%d_%H%M%S")
    except ValueError:
        pytest.fail(
            f"Log file timestamp '{timestamp_part}' is not in expected format YYYYMMDD_HHMMSS"
        )


def test_execute_logging_writes_structured_logs(test_settings: RunnerSettings, cleanup_log_dir):
    """Test that execute mode writes structured JSON logs."""
    from huleedu_service_libs.logging_utils import create_service_logger

    log_dir = Path(".claude/research/data/eng5_np_2016/logs")

    # Configure logging
    configure_execute_logging(settings=test_settings, verbose=False)

    # Create logger and write test log
    logger = create_service_logger("test_component")
    test_event = "test_validation_event"
    test_data = {"test_key": "test_value", "correlation_id": str(test_settings.correlation_id)}
    logger.info(test_event, **test_data)

    # Find and read log file
    log_files = list(log_dir.glob(f"eng5-{test_settings.batch_id}-*.log"))
    assert len(log_files) >= 1

    log_content = log_files[0].read_text()
    assert len(log_content) > 0, "Log file should contain content"

    # Verify structured JSON format
    log_lines = [line for line in log_content.strip().split("\n") if line]
    assert len(log_lines) >= 1, "Log file should contain at least one log line"

    # Parse first log line as JSON
    try:
        log_entry = json.loads(log_lines[0])
    except json.JSONDecodeError as exc:
        pytest.fail(f"Log line is not valid JSON: {exc}")

    # Verify log structure
    assert "event" in log_entry or "message" in log_entry
    assert "timestamp" in log_entry
    assert "level" in log_entry


def test_execute_logging_rotation_configuration(test_settings: RunnerSettings, cleanup_log_dir):
    """Test that file rotation is configured with service-standard settings."""
    import logging
    from logging.handlers import RotatingFileHandler

    log_dir = Path(".claude/research/data/eng5_np_2016/logs")

    # Configure logging
    configure_execute_logging(settings=test_settings, verbose=False)

    # Find the RotatingFileHandler in the root logger
    root_logger = logging.getLogger()
    rotating_handlers = [h for h in root_logger.handlers if isinstance(h, RotatingFileHandler)]

    assert len(rotating_handlers) >= 1, "Expected at least one RotatingFileHandler"

    handler = rotating_handlers[0]

    # Verify rotation settings (service standards: 100MB, 10 backups)
    assert handler.maxBytes == 104857600, "Expected 100MB (104857600 bytes) max file size"
    assert handler.backupCount == 10, "Expected 10 backup files"

    # Verify log file is in correct directory
    assert handler.baseFilename.startswith(str(log_dir.resolve()))


def test_verbose_mode_sets_debug_level(test_settings: RunnerSettings, cleanup_log_dir):
    """Test that verbose mode sets DEBUG log level."""
    import logging

    # Configure with verbose=True
    configure_execute_logging(settings=test_settings, verbose=True)

    # Check root logger level is DEBUG
    root_logger = logging.getLogger()
    assert root_logger.level <= logging.DEBUG, "Expected DEBUG or lower log level in verbose mode"


def test_non_verbose_mode_sets_info_level(test_settings: RunnerSettings, cleanup_log_dir):
    """Test that non-verbose mode sets INFO log level."""
    import logging

    # Configure with verbose=False
    configure_execute_logging(settings=test_settings, verbose=False)

    # Check root logger level is INFO
    root_logger = logging.getLogger()
    assert root_logger.level == logging.INFO, "Expected INFO log level in non-verbose mode"
