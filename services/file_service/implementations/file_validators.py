"""Concrete implementations of file pre-validation checks."""

from __future__ import annotations

from uuid import UUID

import magic
from huleedu_service_libs.error_handling import raise_text_extraction_failed
from huleedu_service_libs.logging_utils import create_service_logger

from services.file_service.protocols import FileValidatorProtocol

logger = create_service_logger("file_service.file_validators")


class TemporaryFileValidator(FileValidatorProtocol):
    """Validates that a file is not a temporary 'owner' file created by MS Word."""

    async def validate(self, file_name: str, file_content: bytes, correlation_id: UUID) -> None:
        """Checks for the temporary file prefix '~$'.

        Raises:
            HuleEduError: If the file is a temporary file.
        """
        if file_name.startswith("~$"):
            logger.warning(
                f"Validation failed: file '{file_name}' is a temporary owner file.",
                extra={"correlation_id": str(correlation_id)},
            )
            raise_text_extraction_failed(
                service="file_service",
                operation="validate_file_type",
                file_name=file_name,
                message="File is a temporary Word 'owner' file and cannot be processed.",
                correlation_id=correlation_id,
            )


class MagicNumberValidator(FileValidatorProtocol):
    """Validates the file's true MIME type using its magic number signature."""

    def __init__(self, allowed_mime_types: set[str]):
        self._magic = magic.Magic(mime=True)
        self._allowed_mime_types = allowed_mime_types
        logger.info(f"MagicNumberValidator initialized for types: {allowed_mime_types}")

    async def validate(self, file_name: str, file_content: bytes, correlation_id: UUID) -> None:
        """Checks if the file's detected MIME type is in the allowed list.

        Raises:
            HuleEduError: If the MIME type is not supported.
        """
        # An empty file can't be validated and will fail extraction anyway.
        if not file_content:
            return

        detected_mime = self._magic.from_buffer(file_content)
        if detected_mime not in self._allowed_mime_types:
            logger.warning(
                f"Validation failed for '{file_name}': unsupported MIME type '{detected_mime}'.",
                extra={"correlation_id": str(correlation_id)},
            )
            raise_text_extraction_failed(
                service="file_service",
                operation="validate_mime_type",
                file_name=file_name,
                message=f"File format '{detected_mime}' is not supported.",
                correlation_id=correlation_id,
            )
