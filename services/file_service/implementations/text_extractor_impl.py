"""Text extractor implementation using Strategy pattern."""

from __future__ import annotations

from uuid import UUID

from huleedu_service_libs.error_handling import (
    HuleEduError,
    raise_text_extraction_failed,
)
from huleedu_service_libs.logging_utils import create_service_logger

from services.file_service.implementations.extraction_strategies import (
    DocxExtractionStrategy,
    ExtractionStrategy,
    PdfExtractionStrategy,
    TxtExtractionStrategy,
)
from services.file_service.protocols import TextExtractorProtocol

logger = create_service_logger("file_service.text_extractor")


class StrategyBasedTextExtractor(TextExtractorProtocol):
    """Text extractor using Strategy pattern for multiple file types."""

    def __init__(self) -> None:
        """Initialize with supported extraction strategies."""
        self._strategies: dict[str, ExtractionStrategy] = {
            ".txt": TxtExtractionStrategy(),
            ".docx": DocxExtractionStrategy(),
            ".pdf": PdfExtractionStrategy(),
        }

    async def extract_text(self, file_content: bytes, file_name: str, correlation_id: UUID) -> str:
        """
        Extract text using appropriate strategy based on file extension.

        Args:
            file_content: Raw file bytes
            file_name: Original filename for type detection
            correlation_id: Request correlation ID for tracing

        Returns:
            Extracted text content

        Raises:
            HuleEduError: If extraction fails or file type unsupported
        """
        # Extract file extension
        parts = file_name.lower().split(".")
        if len(parts) < 2:
            raise_text_extraction_failed(
                service="file_service",
                operation="extract_text",
                file_name=file_name,
                message="File has no extension",
                correlation_id=correlation_id,
            )

        file_ext = f".{parts[-1]}"
        strategy = self._strategies.get(file_ext)

        if not strategy:
            supported = ", ".join(self._strategies.keys())
            raise_text_extraction_failed(
                service="file_service",
                operation="extract_text",
                file_name=file_name,
                message=f"Unsupported file type '{file_ext}'. Supported types: {supported}",
                correlation_id=correlation_id,
            )

        try:
            return await strategy.extract(file_content, file_name, correlation_id)
        except HuleEduError:
            # Already a structured error, re-raise as-is
            raise
        except Exception as e:
            logger.error(
                f"Extraction failed for {file_name}: {e}",
                exc_info=True,
                extra={"correlation_id": str(correlation_id)},
            )
            raise_text_extraction_failed(
                service="file_service",
                operation="extract_text",
                file_name=file_name,
                message=f"Failed to extract text: {str(e)}",
                correlation_id=correlation_id,
                error_details=str(e),
            )
