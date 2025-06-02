"""Main entry point for CJ Assessment Service worker."""

from __future__ import annotations

import asyncio
import signal
import sys
from typing import Any

from huleedu_service_libs.logging_utils import configure_service_logging, create_service_logger

from .config import settings

# Configure logging
configure_service_logging(settings.SERVICE_NAME, log_level=settings.LOG_LEVEL)
logger = create_service_logger("worker_main")


async def main() -> None:
    """Main entry point for CJ Assessment Service worker.
    
    This will be implemented in Phase 6 with:
    - Dishka container initialization
    - Kafka consumer setup
    - Message processing loop
    - Graceful shutdown handling
    """
    logger.info("CJ Assessment Service worker starting...")

    # TODO: Phase 6 implementation
    # - Initialize Dishka container with CJAssessmentServiceProvider
    # - Set up Kafka consumer for CJ_ASSESSMENT_REQUEST_TOPIC
    # - Start metrics server
    # - Run message consumption loop
    # - Handle graceful shutdown on SIGTERM/SIGINT

    logger.info("CJ Assessment Service worker ready (shell implementation)")

    # Placeholder - keep running until interrupted
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        logger.info("CJ Assessment Service worker shutting down...")


def signal_handler(signum: int, frame: Any) -> None:
    """Handle shutdown signals."""
    logger.info(f"Received signal {signum}, initiating shutdown...")
    sys.exit(0)


if __name__ == "__main__":
    # Set up signal handlers
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    try:
        asyncio.run(main())
    except Exception as e:
        logger.error(f"CJ Assessment Service worker failed: {e}", exc_info=True)
        sys.exit(1)
