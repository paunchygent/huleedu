"""
Repository implementation for File Service with user attribution.

This module provides database operations for tracking file uploads
with user attribution, enabling audit trails and notification support.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, AsyncGenerator
from uuid import UUID

from common_core.status_enums import ProcessingStatus
from huleedu_service_libs.logging_utils import create_service_logger
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from services.file_service.models_db import FileUpload
from services.file_service.protocols import FileRepositoryProtocol

logger = create_service_logger("file_service.repository")


class FileRepository(FileRepositoryProtocol):
    """
    Repository implementation for File Service with user attribution.

    Tracks file uploads with user information for audit trails,
    debugging, and notification support.
    """

    def __init__(self, engine: AsyncEngine) -> None:
        """
        Initialize the repository with a database engine.

        Args:
            engine: SQLAlchemy async engine for database operations
        """
        self._engine = engine
        self._sessionmaker = async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        logger.info("Initialized file repository with user attribution support")

    @asynccontextmanager
    async def _get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """Get a database session with proper cleanup."""
        async with self._sessionmaker() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    async def create_file_upload(
        self,
        file_upload_id: str,
        batch_id: str,
        user_id: str,
        filename: str,
        assignment_id: str | None = None,
        file_size_bytes: int | None = None,
        correlation_id: UUID | None = None,
    ) -> None:
        """
        Create a new file upload record with user attribution.

        Args:
            file_upload_id: Unique identifier for the file upload
            batch_id: Associated batch identifier
            user_id: User who uploaded the file
            filename: Original file name
            assignment_id: Optional assignment identifier for traceability
            file_size_bytes: Size of the file in bytes
            correlation_id: Request correlation ID for tracing
        """
        async with self._get_session() as session:
            file_upload = FileUpload(
                file_upload_id=file_upload_id,
                batch_id=batch_id,
                user_id=user_id,
                assignment_id=assignment_id,
                filename=filename,
                file_size_bytes=file_size_bytes,
                correlation_id=correlation_id,
                processing_status=ProcessingStatus.PENDING.value,
                upload_timestamp=datetime.now(),
            )
            session.add(file_upload)

            logger.info(
                "Created file upload record",
                extra={
                    "file_upload_id": file_upload_id,
                    "batch_id": batch_id,
                    "user_id": user_id,
                    "filename": filename,
                },
            )

    async def get_file_upload(
        self,
        file_upload_id: str,
    ) -> dict[str, Any] | None:
        """
        Retrieve file upload record by ID.

        Args:
            file_upload_id: Unique identifier for the file upload

        Returns:
            File upload record with user_id and metadata, or None if not found
        """
        async with self._get_session() as session:
            stmt = select(FileUpload).where(FileUpload.file_upload_id == file_upload_id)
            result = await session.execute(stmt)
            file_upload = result.scalar_one_or_none()

            if file_upload:
                return {
                    "file_upload_id": file_upload.file_upload_id,
                    "batch_id": file_upload.batch_id,
                    "user_id": file_upload.user_id,
                    "filename": file_upload.filename,
                    "file_size_bytes": file_upload.file_size_bytes,
                    "processing_status": file_upload.processing_status,
                    "raw_file_storage_id": file_upload.raw_file_storage_id,
                    "text_storage_id": file_upload.text_storage_id,
                    "validation_error_code": file_upload.validation_error_code,
                    "validation_error_message": file_upload.validation_error_message,
                    "upload_timestamp": file_upload.upload_timestamp,
                    "processed_timestamp": file_upload.processed_timestamp,
                    "correlation_id": file_upload.correlation_id,
                }

            return None

    async def update_file_processing_status(
        self,
        file_upload_id: str,
        status: ProcessingStatus,
        raw_file_storage_id: str | None = None,
        text_storage_id: str | None = None,
        validation_error_code: str | None = None,
        validation_error_message: str | None = None,
    ) -> None:
        """
        Update the processing status of a file upload.

        Args:
            file_upload_id: Unique identifier for the file upload
            status: New processing status
            raw_file_storage_id: Storage ID for raw file (if stored)
            text_storage_id: Storage ID for extracted text (if stored)
            validation_error_code: Error code if validation failed
            validation_error_message: Error message if validation failed
        """
        async with self._get_session() as session:
            stmt = (
                update(FileUpload)
                .where(FileUpload.file_upload_id == file_upload_id)
                .values(
                    processing_status=status.value,
                    processed_timestamp=datetime.now(),
                    raw_file_storage_id=raw_file_storage_id or FileUpload.raw_file_storage_id,
                    text_storage_id=text_storage_id or FileUpload.text_storage_id,
                    validation_error_code=validation_error_code or FileUpload.validation_error_code,
                    validation_error_message=validation_error_message
                    or FileUpload.validation_error_message,
                )
            )
            await session.execute(stmt)

            logger.info(
                "Updated file processing status",
                extra={
                    "file_upload_id": file_upload_id,
                    "status": status.value,
                    "validation_error_code": validation_error_code,
                },
            )

    async def get_batch_uploads(
        self,
        batch_id: str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """
        Retrieve all file uploads for a batch.

        Args:
            batch_id: Batch identifier to query
            limit: Maximum number of records to return

        Returns:
            List of file upload records with user attribution
        """
        async with self._get_session() as session:
            stmt = (
                select(FileUpload)
                .where(FileUpload.batch_id == batch_id)
                .order_by(FileUpload.upload_timestamp.desc())
                .limit(limit)
            )
            result = await session.execute(stmt)
            file_uploads = result.scalars().all()

            return [
                {
                    "file_upload_id": upload.file_upload_id,
                    "batch_id": upload.batch_id,
                    "user_id": upload.user_id,
                    "filename": upload.filename,
                    "file_size_bytes": upload.file_size_bytes,
                    "processing_status": upload.processing_status,
                    "raw_file_storage_id": upload.raw_file_storage_id,
                    "text_storage_id": upload.text_storage_id,
                    "validation_error_code": upload.validation_error_code,
                    "validation_error_message": upload.validation_error_message,
                    "upload_timestamp": upload.upload_timestamp,
                    "processed_timestamp": upload.processed_timestamp,
                    "correlation_id": upload.correlation_id,
                }
                for upload in file_uploads
            ]


# Keep the minimal implementation for backward compatibility
class MinimalFileRepository(FileRepositoryProtocol):
    """
    Minimal implementation of FileRepositoryProtocol.

    This is a no-op implementation for testing and backward compatibility.
    """

    def __init__(self, engine: AsyncEngine) -> None:
        """Initialize the minimal repository."""
        self._engine = engine
        logger.info("Initialized minimal file repository (no-op implementation)")

    async def create_file_upload(
        self,
        file_upload_id: str,
        batch_id: str,
        user_id: str,
        filename: str,
        assignment_id: str | None = None,
        file_size_bytes: int | None = None,
        correlation_id: UUID | None = None,
    ) -> None:
        """No-op implementation."""
        logger.debug(
            "File upload recorded (no-op)",
            extra={
                "file_upload_id": file_upload_id,
                "batch_id": batch_id,
                "user_id": user_id,
                "filename": filename,
                "assignment_id": assignment_id,
            },
        )

    async def get_file_upload(
        self,
        file_upload_id: str,
    ) -> dict[str, Any] | None:
        """No-op implementation - returns None."""
        return None

    async def update_file_processing_status(
        self,
        file_upload_id: str,
        status: ProcessingStatus,
        raw_file_storage_id: str | None = None,
        text_storage_id: str | None = None,
        validation_error_code: str | None = None,
        validation_error_message: str | None = None,
    ) -> None:
        """No-op implementation."""
        logger.debug(
            "File processing status updated (no-op)",
            extra={
                "file_upload_id": file_upload_id,
                "status": status.value,
            },
        )

    async def get_batch_uploads(
        self,
        batch_id: str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """No-op implementation - returns empty list."""
        return []
