# IMPLEMENTATION PLAN

## \#\#\# 1. Update Shared Libraries (`common_core` and `huleedu_service_libs`)

These changes introduce the new, specific error type into our platform's shared vocabulary.

#### **`common_core/src/common_core/error_enums.py`**

Add the `ENCRYPTED_FILE_UNSUPPORTED` error code to the `FileValidationErrorCode` enum.

```python
from enum import Enum

class FileValidationErrorCode(str, Enum):
    # ... existing codes ...
    RAW_STORAGE_FAILED = "RAW_STORAGE_FAILED"
    TEXT_EXTRACTION_FAILED = "TEXT_EXTRACTION_FAILED"
    ENCRYPTED_FILE_UNSUPPORTED = "ENCRYPTED_FILE_UNSUPPORTED"  # ✅ ADD THIS
    UNKNOWN_VALIDATION_ERROR = "UNKNOWN_VALIDATION_ERROR"
```

\<br/\>

#### **`libs/huleedu_service_libs/src/huleedu_service_libs/error_handling/file_validation_factories.py`**

Add the new factory function to create and raise the specific error for encrypted files.

```python
from typing import Any, NoReturn
from uuid import UUID

from common_core.error_enums import FileValidationErrorCode

from .error_detail_factory import create_error_detail_with_context
from .huleedu_error import HuleEduError

# ... existing factory functions ...

def raise_text_extraction_failed(
    # ...
) -> NoReturn:
    # ...
    raise HuleEduError(error_detail)


# ✅ ADD THIS NEW FACTORY FUNCTION
def raise_encrypted_file_error(
    service: str,
    operation: str,
    file_name: str,
    correlation_id: UUID,
    **additional_context: Any,
) -> NoReturn:
    """Creates and raises an error for encrypted, unsupported files."""
    error_detail = create_error_detail_with_context(
        error_code=FileValidationErrorCode.ENCRYPTED_FILE_UNSUPPORTED,
        message=f"File '{file_name}' is encrypted and cannot be processed.",
        service=service,
        operation=operation,
        correlation_id=correlation_id,
        details={"file_name": file_name, **additional_context},
    )
    raise HuleEduError(error_detail)


def raise_unknown_validation_error(
    # ...
) -> NoReturn:
    # ...
    raise HuleEduError(error_detail)
```

-----

## \#\#\# 2. Update File Service Dependencies and Implementation

These changes implement the new strategy pattern within the File Service itself.

#### **`services/file_service/pyproject.toml`**

Add `python-docx` and `pypdf` as dependencies with pinned versions.

```toml
[project]
name = "huleedu-file-service"
# ...
requires-python = ">=3.11"
dependencies = [
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
    "python-docx==1.1.2",
    "pypdf==4.2.0",
]
```

*Note: I've updated `pypdf` to a more recent stable version.*

\<br/\>

#### **`services/file_service/implementations/extraction_strategies.py` (New File)**

Create this new file to house the individual extraction strategies.

```python
"""Concrete implementations of text extraction strategies for different file types."""

from __future__ import annotations

import asyncio
import io
from typing import Protocol, runtime_checkable
from uuid import UUID

import docx
from huleedu_service_libs.error_handling.file_validation_factories import (
    raise_encrypted_file_error,
)
from huleedu_service_libs.logging_utils import create_service_logger
from pypdf import PdfReader

logger = create_service_logger("file_service.extraction_strategies")


@runtime_checkable
class ExtractionStrategy(Protocol):
    """Protocol for file type extraction strategies."""

    async def extract(
        self, file_content: bytes, file_name: str, correlation_id: UUID
    ) -> str:
        """Extracts text from the given file content."""
        ...


class TxtExtractionStrategy(ExtractionStrategy):
    """Strategy for extracting text from .txt files."""

    async def extract(
        self, file_content: bytes, file_name: str, correlation_id: UUID
    ) -> str:
        """Performs direct UTF-8 decoding."""
        text = file_content.decode("utf-8", errors="ignore")
        logger.info(
            f"Extracted {len(text)} characters from {file_name}",
            extra={"correlation_id": str(correlation_id)},
        )
        return text


class DocxExtractionStrategy(ExtractionStrategy):
    """Strategy for extracting text from .docx files."""

    async def extract(
        self, file_content: bytes, file_name: str, correlation_id: UUID
    ) -> str:
        """Extracts text from Word documents using a thread pool."""

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
    """Strategy for extracting text from .pdf files."""

    async def extract(
        self, file_content: bytes, file_name: str, correlation_id: UUID
    ) -> str:
        """Extracts text from PDF documents using a thread pool."""

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

\<br/\>

#### **`services/file_service/implementations/text_extractor_impl.py` (Full Replacement)**

Replace the entire contents of this file with the new `StrategyBasedTextExtractor`.

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

\<br/\>

#### **`services/file_service/di.py` (Modified)**

Update the DI provider to inject the new `StrategyBasedTextExtractor`.

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
```

-----

## \#\#\# 3. Final Cleanup

The last step is to remove the now-obsolete placeholder file.

  * **Delete the file `services/file_service/text_processing.py`**.

This completes the refactor. The system is now extensible, robust, and fully compliant with our architectural standards.