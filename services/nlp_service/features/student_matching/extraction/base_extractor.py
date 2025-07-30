"""Base extractor interface for student identification strategies."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from huleedu_service_libs.logging_utils import create_service_logger

from ..models import ExtractionResult

logger = create_service_logger("nlp_service.extraction.base")


class BaseExtractor(ABC):
    """Abstract base class for extraction strategies."""

    def __init__(self, name: str):
        """Initialize with strategy name for logging."""
        self.name = name
        self.logger = create_service_logger(f"nlp_service.extraction.{name}")

    @abstractmethod
    async def extract(
        self,
        text: str,
        filename: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ExtractionResult:
        """Extract student identifiers from text.

        Args:
            text: The essay text to extract from
            filename: Optional filename hint (e.g., for exam.net format detection)
            metadata: Optional additional context

        Returns:
            ExtractionResult with possible names and emails
        """
        ...

    def normalize_text(self, text: str) -> str:
        """Basic text normalization - can be overridden by subclasses."""
        # Remove excessive whitespace
        lines = text.strip().split("\n")
        normalized_lines = []

        for line in lines:
            # Preserve line structure but clean up spacing
            cleaned = " ".join(line.split())
            normalized_lines.append(cleaned)

        return "\n".join(normalized_lines)
