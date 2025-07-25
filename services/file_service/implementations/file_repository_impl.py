"""
Minimal repository implementation for File Service.

This module provides a basic repository implementation that currently
serves as a placeholder for future persistence needs. File Service is
primarily stateless but may need to track processing history in the future.
"""

from __future__ import annotations

from typing import Any

from common_core.status_enums import ProcessingStatus
from huleedu_service_libs.logging_utils import create_service_logger
from sqlalchemy.ext.asyncio import AsyncEngine

from services.file_service.protocols import FileRepositoryProtocol

logger = create_service_logger("file_service.repository")


class MinimalFileRepository(FileRepositoryProtocol):
    """
    Minimal implementation of FileRepositoryProtocol.

    Currently provides no-op implementations as File Service is stateless.
    This repository exists to support the outbox pattern infrastructure
    and can be extended in the future for tracking file processing history.
    """

    def __init__(self, engine: AsyncEngine) -> None:
        """
        Initialize the repository with a database engine.

        Args:
            engine: SQLAlchemy async engine (required for consistency with other services)
        """
        self._engine = engine
        logger.info("Initialized minimal file repository (no-op implementation)")

    async def record_file_processing(
        self,
        file_upload_id: str,
        batch_id: str,
        file_name: str,
        status: ProcessingStatus,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """
        Record file processing event (no-op for now).

        This is a placeholder that can be implemented when File Service
        needs to track processing history in the database.
        """
        logger.debug(
            "File processing recorded (no-op)",
            extra={
                "file_upload_id": file_upload_id,
                "batch_id": batch_id,
                "file_name": file_name,
                "status": status.value,
            },
        )

    async def get_processing_history(
        self,
        batch_id: str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """
        Retrieve file processing history (returns empty list for now).

        This is a placeholder that can be implemented when File Service
        needs to track processing history in the database.
        """
        logger.debug(
            "Processing history requested (returning empty)",
            extra={"batch_id": batch_id, "limit": limit},
        )
        return []
