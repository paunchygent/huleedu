"""Concrete implementations of text extraction strategies for different file types."""

from __future__ import annotations

import asyncio
import io
from typing import Protocol, runtime_checkable
from uuid import UUID

import docx
from huleedu_service_libs.error_handling import (
    raise_encrypted_file_error,
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
