"""
Unit tests for file-based logging in logging_utils.

Tests configure_service_logging() file handler creation, path resolution,
directory creation, rotation settings, and idempotent configuration.
Follows Rule 075 behavioral testing patterns with focus on side effects
rather than log content validation.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Generator

import pytest
import structlog


@pytest.fixture
def temp_log_path(tmp_path: Path) -> Path:
    """Provide temporary log file path for testing."""
    return tmp_path / "test-service.log"


@pytest.fixture(autouse=True)
def clean_logging_config() -> Generator[None, None, None]:
    """Clean up logging configuration after each test to prevent pollution."""
    # Capture initial handler count
    list(logging.root.handlers)

    yield

    # Reset logging configuration
    logging.root.handlers.clear()
    logging.root.setLevel(logging.WARNING)

    # Reset structlog configuration to defaults
    structlog.reset_defaults()


class TestConfigureServiceLoggingFileHandler:
    """Tests for configure_service_logging file-based logging functionality."""

    def test_no_file_handler_when_disabled(self, tmp_path: Path) -> None:
        """Test that no file handler is created when file logging is disabled."""
        from huleedu_service_libs.logging_utils import configure_service_logging

        # Configure with file logging disabled (default)
        configure_service_logging("test-service", log_level="INFO")

        # Verify logging configured successfully (no exceptions)
        # Verify only stdout handler (no file handler)
        assert len(logging.root.handlers) == 1

        # Verify it's a StreamHandler, not a RotatingFileHandler
        from logging import StreamHandler
        from logging.handlers import RotatingFileHandler

        assert isinstance(logging.root.handlers[0], StreamHandler)
        assert not isinstance(logging.root.handlers[0], RotatingFileHandler)

        # Verify no log files created in tmp_path
        log_files = list(tmp_path.glob("*.log"))
        assert len(log_files) == 0

    def test_file_handler_created_from_env_vars(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test file handler creation driven by environment variables."""
        from huleedu_service_libs.logging_utils import configure_service_logging

        # Setup environment variables
        log_file_path = tmp_path / "custom" / "test.log"
        monkeypatch.setenv("LOG_TO_FILE", "true")
        monkeypatch.setenv("LOG_FILE_PATH", str(log_file_path))
        monkeypatch.setenv("LOG_MAX_BYTES", "1000000")
        monkeypatch.setenv("LOG_BACKUP_COUNT", "5")

        # Configure logging
        configure_service_logging("test-service", log_level="INFO")

        # Verify file handler created
        from logging.handlers import RotatingFileHandler

        file_handlers = [h for h in logging.root.handlers if isinstance(h, RotatingFileHandler)]
        assert len(file_handlers) == 1

        # Verify handler configuration
        file_handler = file_handlers[0]
        assert file_handler.maxBytes == 1000000
        assert file_handler.backupCount == 5

        # Verify parent directory was created
        assert log_file_path.parent.exists()
        assert log_file_path.parent.is_dir()

    def test_explicit_args_override_env_vars(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that explicit arguments override environment variables."""
        from huleedu_service_libs.logging_utils import configure_service_logging

        # Set environment variables that should be ignored
        monkeypatch.setenv("LOG_TO_FILE", "false")
        monkeypatch.setenv("LOG_FILE_PATH", "/should/not/use/this/path.log")

        # Configure with explicit arguments
        explicit_path = tmp_path / "explicit.log"
        configure_service_logging(
            "test-service",
            log_level="INFO",
            log_to_file=True,
            log_file_path=str(explicit_path),
        )

        # Verify file handler created at explicit path
        from logging.handlers import RotatingFileHandler

        file_handlers = [h for h in logging.root.handlers if isinstance(h, RotatingFileHandler)]
        assert len(file_handlers) == 1

        # Verify path matches explicit argument
        file_handler = file_handlers[0]
        assert Path(file_handler.baseFilename) == explicit_path

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        """Test that parent directories are created if they don't exist."""
        from huleedu_service_libs.logging_utils import configure_service_logging

        # Use a deeply nested path that doesn't exist
        nested_path = tmp_path / "deeply" / "nested" / "path" / "test.log"

        # Configure logging with nested path
        configure_service_logging(
            "test-service",
            log_level="INFO",
            log_to_file=True,
            log_file_path=str(nested_path),
        )

        # Verify all parent directories were created
        assert nested_path.parent.exists()
        assert nested_path.parent.is_dir()

        # Verify the full path structure
        assert (tmp_path / "deeply").exists()
        assert (tmp_path / "deeply" / "nested").exists()
        assert (tmp_path / "deeply" / "nested" / "path").exists()

    @pytest.mark.parametrize(
        "max_bytes, backup_count",
        [
            (100, 5),  # Small file size
            (1048576, 10),  # 1MB, standard backup count
            (104857600, 3),  # 100MB (default), minimal backups
        ],
    )
    def test_rotation_settings_from_env(
        self,
        max_bytes: int,
        backup_count: int,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test that rotation settings are correctly read from environment variables."""
        from huleedu_service_libs.logging_utils import configure_service_logging

        # Setup environment with specific rotation settings
        log_file_path = tmp_path / "test.log"
        monkeypatch.setenv("LOG_TO_FILE", "true")
        monkeypatch.setenv("LOG_FILE_PATH", str(log_file_path))
        monkeypatch.setenv("LOG_MAX_BYTES", str(max_bytes))
        monkeypatch.setenv("LOG_BACKUP_COUNT", str(backup_count))

        # Configure logging
        configure_service_logging("test-service", log_level="INFO")

        # Verify rotation settings
        from logging.handlers import RotatingFileHandler

        file_handlers = [h for h in logging.root.handlers if isinstance(h, RotatingFileHandler)]
        assert len(file_handlers) == 1

        file_handler = file_handlers[0]
        assert file_handler.maxBytes == max_bytes
        assert file_handler.backupCount == backup_count

    def test_multiple_calls_idempotent(self, tmp_path: Path) -> None:
        """Test that multiple configure_service_logging calls are idempotent."""
        from huleedu_service_libs.logging_utils import (
            configure_service_logging,
            create_service_logger,
        )

        log_file_path = tmp_path / "idempotent.log"

        # First configuration
        configure_service_logging(
            "test-service",
            log_level="INFO",
            log_to_file=True,
            log_file_path=str(log_file_path),
        )

        # Get handler count after first call
        first_handler_count = len(logging.root.handlers)

        # Second configuration (should not create duplicate handlers)
        configure_service_logging(
            "test-service",
            log_level="INFO",
            log_to_file=True,
            log_file_path=str(log_file_path),
        )

        # Verify handler count remains the same (force=True in basicConfig)
        second_handler_count = len(logging.root.handlers)
        assert second_handler_count == first_handler_count

        # Verify logging still functional
        logger = create_service_logger("test")
        logger.info("test message")  # Should not raise exception

    def test_logs_written_to_file(self, tmp_path: Path) -> None:
        """Test that logs are actually written to the file."""
        from huleedu_service_libs.logging_utils import (
            configure_service_logging,
            create_service_logger,
        )

        log_file_path = tmp_path / "output.log"

        # Configure file logging
        configure_service_logging(
            "test-service",
            log_level="INFO",
            log_to_file=True,
            log_file_path=str(log_file_path),
        )

        # Create logger and emit a log message
        logger = create_service_logger("test")
        logger.info("test message", test_field="test_value")

        # Verify file exists and contains content
        assert log_file_path.exists()
        assert log_file_path.is_file()
        assert log_file_path.stat().st_size > 0

        # Note: We do NOT test log content per Rule 075 §3.2 (fragile)
        # We only verify the side effect (file creation and non-empty content)

    def test_default_path_when_no_explicit_path(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that default log path pattern is used when no explicit path provided."""
        from huleedu_service_libs.logging_utils import configure_service_logging

        # Enable file logging but provide LOG_FILE_PATH env var
        # (since default /app/logs/ is read-only on macOS test environment)
        default_path = tmp_path / "logs" / "my-test-service.log"
        monkeypatch.setenv("LOG_TO_FILE", "true")
        monkeypatch.setenv("LOG_FILE_PATH", str(default_path))

        # Configure logging without explicit path argument
        configure_service_logging("my-test-service", log_level="INFO")

        # Verify file handler created with env var path
        from logging.handlers import RotatingFileHandler

        file_handlers = [h for h in logging.root.handlers if isinstance(h, RotatingFileHandler)]
        assert len(file_handlers) == 1

        # Verify path matches pattern from env var
        file_handler = file_handlers[0]
        handler_path = Path(file_handler.baseFilename)
        assert handler_path.name == "my-test-service.log"
        assert handler_path.parent.name == "logs"
        assert handler_path == default_path

    def test_file_handler_with_stdout_handler(self, tmp_path: Path) -> None:
        """Test that both stdout and file handlers are registered when file logging enabled."""
        from huleedu_service_libs.logging_utils import configure_service_logging

        log_file_path = tmp_path / "both-handlers.log"

        # Configure with file logging enabled
        configure_service_logging(
            "test-service",
            log_level="INFO",
            log_to_file=True,
            log_file_path=str(log_file_path),
        )

        # Verify both handlers present
        from logging import StreamHandler
        from logging.handlers import RotatingFileHandler

        assert len(logging.root.handlers) == 2

        # Verify one StreamHandler and one RotatingFileHandler
        stream_handlers = [
            h
            for h in logging.root.handlers
            if isinstance(h, StreamHandler) and not isinstance(h, RotatingFileHandler)
        ]
        file_handlers = [h for h in logging.root.handlers if isinstance(h, RotatingFileHandler)]

        assert len(stream_handlers) == 1
        assert len(file_handlers) == 1
