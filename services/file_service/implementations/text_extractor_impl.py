"""Text extractor implementation using Strategy pattern."""

from __future__ import annotations

import os
from uuid import UUID

from huleedu_service_libs.error_handling import (
    HuleEduError,
    raise_text_extraction_failed,
)
from huleedu_service_libs.logging_utils import create_service_logger

from services.file_service.implementations.extraction_strategies import (
    ExtractionStrategy,
)
from services.file_service.protocols import (
    FileValidatorProtocol,
    TextExtractorProtocol,
)

logger = create_service_logger("file_service.text_extractor")


class StrategyBasedTextExtractor(TextExtractorProtocol):
    """Extracts text by validating and then selecting a file-type strategy."""

    def __init__(
        self,
        validators: list[FileValidatorProtocol],
        strategies: dict[str, ExtractionStrategy],
    ):
        self._validators = validators
        self._strategies = strategies
        logger.info(
            f"Initialized with {len(validators)} validators "
            f"and strategies for keys: {list(strategies.keys())}"
        )

    async def extract_text(self, file_content: bytes, file_name: str, correlation_id: UUID) -> str:
        """First, run all validators, then select and execute the extraction strategy."""
        # 1. Run all pre-validation checks sequentially
        for validator in self._validators:
            await validator.validate(file_name, file_content, correlation_id)

        logger.info(
            f"All validators passed for '{file_name}'.",
            extra={"correlation_id": str(correlation_id)},
        )

        # 2. Select strategy based on file extension
        file_extension = os.path.splitext(file_name)[1].lower()
        strategy = self._strategies.get(file_extension)

        if not strategy:
            raise_text_extraction_failed(
                service="file_service",
                operation="select_strategy",
                file_name=file_name,
                message=f"No extraction strategy found for file type '{file_extension}'.",
                correlation_id=correlation_id,
            )

        logger.info(
            f"Using strategy '{type(strategy).__name__}' for '{file_name}'.",
            extra={"correlation_id": str(correlation_id)},
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
            )
