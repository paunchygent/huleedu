"""Concrete implementations of text extraction strategies for different file types."""

from __future__ import annotations

import asyncio
import io
from typing import Protocol, runtime_checkable
from uuid import UUID

import docx
import pypandoc
from huleedu_service_libs.error_handling import (
    raise_encrypted_file_error,
    raise_text_extraction_failed,
)
from huleedu_service_libs.logging_utils import create_service_logger
from pypdf import PdfReader

logger = create_service_logger("file_service.extraction_strategies")


@runtime_checkable
class ExtractionStrategy(Protocol):
    """Protocol for file type extraction strategies."""

    async def extract(
        self,
        file_content: bytes,
        file_name: str,
        correlation_id: UUID,
    ) -> str:
        """Extract text from file content."""
        ...


class TxtExtractionStrategy:
    """Extract text from .txt files."""

    async def extract(self, file_content: bytes, file_name: str, correlation_id: UUID) -> str:
        """Direct UTF-8 decoding with error handling."""
        text = file_content.decode("utf-8", errors="ignore")
        logger.info(
            f"Extracted {len(text)} characters from {file_name}",
            extra={"correlation_id": str(correlation_id)},
        )
        return text


class DocxExtractionStrategy:
    """Extract text from .docx files."""

    async def extract(self, file_content: bytes, file_name: str, correlation_id: UUID) -> str:
        """Extract text from Word documents."""

        def _extract_docx_sync() -> str:
            document = docx.Document(io.BytesIO(file_content))
            paragraphs = [para.text for para in document.paragraphs if para.text.strip()]
            text = "\n".join(paragraphs)
            logger.info(
                f"Extracted {len(paragraphs)} paragraphs from {file_name}",
                extra={"correlation_id": str(correlation_id)},
            )
            return text

        return await asyncio.to_thread(_extract_docx_sync)


class PdfExtractionStrategy:
    """Extract text from .pdf files."""

    async def extract(self, file_content: bytes, file_name: str, correlation_id: UUID) -> str:
        """Extract text from PDF documents."""

        def _extract_pdf_sync() -> str:
            reader = PdfReader(io.BytesIO(file_content))

            if reader.is_encrypted:
                raise_encrypted_file_error(
                    service="file_service",
                    operation="extract_text",
                    file_name=file_name,
                    correlation_id=correlation_id,
                )

            pages_text = []
            for page_num, page in enumerate(reader.pages, 1):
                page_text = page.extract_text()
                if page_text.strip():
                    pages_text.append(page_text)

            text = "\n".join(pages_text)
            logger.info(
                f"Extracted text from {len(reader.pages)} pages in {file_name}",
                extra={"correlation_id": str(correlation_id)},
            )
            return text

        return await asyncio.to_thread(_extract_pdf_sync)


class PandocFallbackStrategy(ExtractionStrategy):
    """Universal fallback strategy using pandoc for difficult or legacy files."""

    async def extract(
        self, file_content: bytes, file_name: str, correlation_id: UUID
    ) -> str:
        """Extracts text using pandoc, running the blocking call in a thread."""
        logger.warning(
            f"Using Pandoc fallback strategy for '{file_name}'.",
            extra={"correlation_id": str(correlation_id)},
        )
        try:
            # Let pandoc auto-detect the format from the buffer
            return await asyncio.to_thread(
                pypandoc.convert_text,
                source=file_content,
                to="plain",
                format=None,
                encoding="utf-8",
            )
        except Exception as e:
            logger.critical(
                f"Pandoc fallback failed for '{file_name}': {e}",
                extra={"correlation_id": str(correlation_id)},
            )
            # Raise the standard error after the final attempt fails
            raise_text_extraction_failed(
                service="file_service",
                operation="extract_pandoc_fallback",
                file_name=file_name,
                message=f"All extraction strategies failed. Final error: {e}",
                correlation_id=correlation_id,
            )


class ResilientDocxStrategy(ExtractionStrategy):
    """A composite strategy that tries a primary strategy then falls back."""

    def __init__(
        self, primary_strategy: ExtractionStrategy, fallback_strategy: ExtractionStrategy
    ):
        self._primary = primary_strategy
        self._fallback = fallback_strategy

    async def extract(
        self, file_content: bytes, file_name: str, correlation_id: UUID
    ) -> str:
        """Attempts the primary strategy, using the fallback on any failure."""
        try:
            return await self._primary.extract(file_content, file_name, correlation_id)
        except Exception:  # The primary strategy already logs its specific error
            logger.warning(
                f"Primary strategy failed for '{file_name}', attempting fallback.",
                extra={"correlation_id": str(correlation_id)},
            )
            return await self._fallback.extract(file_content, file_name, correlation_id)
