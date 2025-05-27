"""Configuration and fixtures for NLP analyzer tests."""

import logging
from collections.abc import Generator  # Added Generator

import pytest
from loguru import logger

# import sys # Keep commented out unless logger re-add at end is used
# Define a handler structure that matches Loguru's needs but can write to caplog


class PropagateHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        logging.getLogger(record.name).handle(record)


@pytest.fixture(autouse=True)  # Autouse ensures this runs for all tests in the directory
def caplog_interceptor(caplog: pytest.LogCaptureFixture) -> Generator[None, None, None]:
    """Intercepts loguru messages and propogates them to pytest's caplog.
    Also sets the caplog level to capture desired messages.
    """
    handler_id = None
    # Remove default loguru handler to avoid duplicate output if running pytest with -s
    try:
        # Assuming the default handler is at index 0. This might be brittle.
        # Consider configuring loguru sinks more explicitly if this causes issues.
        logger.remove(0)
    except ValueError:  # Handler already removed or never added
        pass

    # Add a handler that propagates records to the standard logging system
    handler_id = logger.add(
        PropagateHandler(),
        format="{message}",
        level=logging.DEBUG,
    )  # Capture from DEBUG level

    # Set pytest's caplog level to capture messages propagated from loguru
    caplog.set_level(logging.DEBUG)  # Capture from DEBUG level upwards in caplog

    yield  # Test runs here

    # Clean up after test: remove the handler to avoid interfering with other tests
    if handler_id is not None:
        try:
            logger.remove(handler_id)
        except ValueError:
            logger.warning(
                f"Could not remove loguru handler {handler_id}. May already be removed.",
            )
    # Optionally add back a default sink like stderr if needed globally after tests
    # logger.add(sys.stderr, format="{time} {level} {message}", level="INFO")
