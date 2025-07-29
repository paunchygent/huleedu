# File Service - File Support Extension

## Overview

Implementation plan for extending file support with strategy pattern for text extraction and encrypted file handling.

## 1. Update Shared Libraries

### 1.1 Add Error Code to Common Core

**File:** `common_core/src/common_core/error_enums.py`

```python
from enum import Enum

class FileValidationErrorCode(str, Enum):
    """Error codes for file validation scenarios."""
    # ... existing codes ...
    RAW_STORAGE_FAILED = "RAW_STORAGE_FAILED"
    TEXT_EXTRACTION_FAILED = "TEXT_EXTRACTION_FAILED"
    ENCRYPTED_FILE_UNSUPPORTED = "ENCRYPTED_FILE_UNSUPPORTED" # ADD THIS
    UNKNOWN_VALIDATION_ERROR = "UNKNOWN_VALIDATION_ERROR"
```

### 1.2 Add Error Factory Method

**File:** `libs/huleedu_service_libs/src/huleedu_service_libs/error_handling/file_validation_factories.py`

```python
from typing import Any, NoReturn
from uuid import UUID
from common_core.error_enums import FileValidationErrorCode
from .error_detail_factory import create_error_detail_with_context
from .huleedu_error import HuleEduError

def raise_encrypted_file_error(
    service: str,
    operation: str,
    file_name: str,
    correlation_id: UUID,
    **additional_context: Any,
) -> NoReturn:
    """
    Creates and raises an error for encrypted files.
    
    Args:
        service: Service name where error occurred
        operation: Operation being performed
        file_name: Name of the encrypted file
        correlation_id: Correlation ID for tracing
        **additional_context: Additional error details
    """
    error_detail = create_error_detail_with_context(
        error_code=FileValidationErrorCode.ENCRYPTED_FILE_UNSUPPORTED,
        message=f"File '{file_name}' is encrypted and cannot be processed.",
        service=service,
        operation=operation,
        correlation_id=correlation_id,
        details={"file_name": file_name, **additional_context},
    )
    raise HuleEduError(error_detail)
```

## 2. File Service Updates

### 2.1 Update Dependencies

**File:** `services/file_service/pyproject.toml`

```toml
[project]
name = "huleedu-file-service"
requires-python = ">=3.11"
dependencies = [
    # Core dependencies
    "quart",
    "hypercorn",
    "aiokafka",
    "aiohttp",
    "python-dotenv",
    "pydantic",
    "pydantic-settings",
    "prometheus-client",
    "dishka",
    "quart-dishka",
    "alembic",
    "asyncpg",
    "sqlalchemy",
    "huleedu-common-core",
    "huleedu-service-libs",
    
    # File processing dependencies (OBS! No version pinning! pdm will handle this)
    "python-docx",  # For .docx files
    "pypdf",       # For PDF files
]
```

### 2.2 Implement Extraction Strategies

**File:** `services/file_service/implementations/extraction_strategies.py`

```python
"""
Text extraction strategies for different file types.

Implements the Strategy pattern for file type-specific text extraction.
"""

from __future__ import annotations
import asyncio
import io
from typing import Protocol, runtime_checkable
from uuid import UUID

import docx
from pypdf import PdfReader
from huleedu_service_libs.error_handling.file_validation_factories import (
    raise_encrypted_file_error,
)
from huleedu_service_libs.logging_utils import create_service_logger

logger = create_service_logger("file_service.extraction_strategies")

# Protocol Definition
@runtime_checkable
class ExtractionStrategy(Protocol):
    """
    Protocol defining the interface for text extraction strategies.
    
    All concrete strategies must implement the extract method with this signature.
    """

    async def extract(
        self, 
        file_content: bytes, 
        file_name: str, 
        correlation_id: UUID
    ) -> str:
        """
        Extract text from file content.
        
        Args:
            file_content: Binary content of the file
            file_name: Name of the file being processed
            correlation_id: UUID for request correlation
            
        Returns:
            Extracted text as a string
            
        Raises:
            HuleEduError: If extraction fails or file is encrypted
        """
        ...

# Concrete Strategy Implementations

class TxtExtractionStrategy(ExtractionStrategy):
    """Extracts text from plain text (.txt) files."""

    async def extract(
        self, 
        file_content: bytes, 
        file_name: str, 
        correlation_id: UUID
    ) -> str:
        """
        Extract text using UTF-8 decoding.
        
        Args:
            file_content: Binary content of the text file
            file_name: Name of the file being processed
            correlation_id: UUID for request correlation
            
        Returns:
            Decoded text content
        """
        text = file_content.decode("utf-8", errors="ignore")
        logger.info(
            f"Extracted {len(text)} characters from {file_name}",
            extra={"correlation_id": str(correlation_id)},
        )
        return text


class DocxExtractionStrategy(ExtractionStrategy):
    """Extracts text from Microsoft Word (.docx) files."""

    async def extract(
        self, 
        file_content: bytes, 
        file_name: str, 
        correlation_id: UUID
    ) -> str:
        """
        Extract text from .docx files using python-docx.
        
        Uses a thread pool to avoid blocking the event loop.
        """
        def _extract_docx_sync() -> str:
            """Synchronous helper for docx parsing."""
            document = docx.Document(io.BytesIO(file_content))
            paragraphs = [p.text for p in document.paragraphs if p.text.strip()]
            text = "\n".join(paragraphs)
            logger.info(
                f"Extracted {len(paragraphs)} paragraphs from {file_name}",
                extra={"correlation_id": str(correlation_id)},
            )
            return text

        return await asyncio.to_thread(_extract_docx_sync)


class PdfExtractionStrategy(ExtractionStrategy):
    """Extracts text from PDF files with encryption detection."""

    async def extract(
        self, 
        file_content: bytes, 
        file_name: str, 
        correlation_id: UUID
    ) -> str:
        """
        Extract text from PDF files using pypdf.
        
        Detects and rejects encrypted PDFs.
        Uses a thread pool for CPU-bound operations.
        """
        def _extract_pdf_sync() -> str:
            """Synchronous helper for PDF parsing."""
            reader = PdfReader(io.BytesIO(file_content))

            if reader.is_encrypted:
                raise_encrypted_file_error(
                    service="file_service",
                    operation="extract_text",
                    file_name=file_name,
                    correlation_id=correlation_id,
                )

            pages_text = [p.extract_text() for p in reader.pages if p.extract_text()]
            text = "\n".join(pages_text)
            logger.info(
                f"Extracted text from {len(reader.pages)} pages in {file_name}",
                extra={"correlation_id": str(correlation_id)},
            )
            return text

        return await asyncio.to_thread(_extract_pdf_sync)
```

### 2.3 Implement Strategy-Based Text Extractor

**File:** `services/file_service/implementations/text_extractor_impl.py`

This file contains the main `StrategyBasedTextExtractor` that coordinates between different extraction strategies.

```python
"""Text extractor implementation using the Strategy pattern."""

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
    """Manages and executes text extraction using the Strategy pattern."""

    def __init__(self) -> None:
        """Initializes with supported extraction strategies."""
        self._strategies: dict[str, ExtractionStrategy] = {
            ".txt": TxtExtractionStrategy(),
            ".docx": DocxExtractionStrategy(),
            ".pdf": PdfExtractionStrategy(),
        }
        logger.info(
            f"Text extractor initialized for types: {', '.join(self._strategies.keys())}"
        )

    async def extract_text(
        self, file_content: bytes, file_name: str, correlation_id: UUID
    ) -> str:
        """Extracts text by selecting and executing the appropriate strategy."""
        parts = file_name.lower().split(".")
        if len(parts) < 2:
            raise_text_extraction_failed(
                service="file_service",
                operation="extract_text",
                file_name=file_name,
                message="File has no extension and type cannot be determined.",
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
            # Re-raise specific, known errors from strategies without modification.
            raise
        except Exception as e:
            # Wrap unexpected, unknown errors from a strategy in our standard error type.
            logger.error(f"Unexpected extraction error for {file_name}: {e}", exc_info=True)
            raise_text_extraction_failed(
                service="file_service",
                operation="extract_text",
                file_name=file_name,
                message=f"A failure occurred during text extraction: {e}",
                correlation_id=correlation_id,
                error_details=str(e),
            )
```

### 2.4 Update Dependency Injection

**File:** `services/file_service/di.py`

Update the dependency injection container to provide the new `StrategyBasedTextExtractor`.

```python
# ... other imports ...
from services.file_service.implementations.text_extractor_impl import (
    StrategyBasedTextExtractor,
)
from services.file_service.protocols import TextExtractorProtocol

# ... other providers ...

class ServiceImplementationsProvider(Provider):
    # ... other provider methods ...

    @provide(scope=Scope.APP)
    def provide_text_extractor(self) -> TextExtractorProtocol:
        """Provide the strategy-based text extractor implementation."""
        return StrategyBasedTextExtractor()


### 3. Final Steps

#### 3.1 Remove Obsolete Files

Remove the now-obsolete placeholder file:

```bash
rm services/file_service/text_processing.py
```

### Summary of Changes

1. **Updated Shared Libraries**
   - Added `ENCRYPTED_FILE_UNSUPPORTED` error code
   - Implemented error factory for encrypted files

2. **Enhanced File Service**
   - Added new dependencies for file processing
   - Implemented strategy pattern for text extraction
   - Added support for multiple file types (TXT, DOCX, PDF)
   - Added proper error handling for encrypted files
   - Updated dependency injection configuration

3. **Code Quality**
   - Improved type hints and documentation
   - Added comprehensive error handling
   - Followed architectural patterns and coding standards

The system is now more maintainable, extensible, and robust, with clear separation of concerns through the Strategy pattern.

!