"""Text extractor implementation for File Service."""

from __future__ import annotations

from services.file_service.protocols import TextExtractorProtocol
from services.file_service.text_processing import extract_text_from_file


class DefaultTextExtractor(TextExtractorProtocol):
    """Default implementation of TextExtractorProtocol."""

    async def extract_text(self, file_content: bytes, file_name: str) -> str:
        """Extract text content from file bytes."""
        result: str = await extract_text_from_file(file_content, file_name)
        return result
