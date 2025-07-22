"""Text extractor implementation for File Service."""

from __future__ import annotations

from uuid import UUID

from services.file_service.protocols import TextExtractorProtocol
from services.file_service.text_processing import extract_text_from_file


class DefaultTextExtractor(TextExtractorProtocol):
    """Default implementation of TextExtractorProtocol."""

    async def extract_text(self, file_content: bytes, file_name: str, correlation_id: UUID) -> str:
        """
        Extract text content from file bytes.

        Args:
            file_content: Raw file bytes
            file_name: Original filename for type dispatch/context
            correlation_id: Request correlation ID for tracing

        Returns:
            Extracted text content as string

        Raises:
            HuleEduError: If extraction fails
        """
        # Pass correlation_id to text processing function
        result: str = await extract_text_from_file(file_content, file_name, correlation_id)
        return result
