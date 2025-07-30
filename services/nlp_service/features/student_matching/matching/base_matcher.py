"""Base matcher interface for student roster matching strategies."""

from __future__ import annotations

from abc import ABC, abstractmethod

from huleedu_service_libs.logging_utils import create_service_logger

from ..models import MatchingResult, StudentInfo

logger = create_service_logger("nlp_service.matching.base")


class BaseMatcher(ABC):
    """Abstract base class for matching strategies."""

    def __init__(self, name: str):
        """Initialize with strategy name for logging."""
        self.name = name
        self.logger = create_service_logger(f"nlp_service.matching.{name}")

    @abstractmethod
    async def match(
        self,
        identifier: str,
        roster: list[StudentInfo],
    ) -> list[MatchingResult]:
        """Match an identifier against the student roster.

        Args:
            identifier: The extracted identifier (name or email) to match
            roster: List of students to match against

        Returns:
            List of matching results with confidence scores
        """
        ...

    def normalize_for_matching(self, text: str) -> str:
        """Normalize text for matching - can be overridden by subclasses."""
        # Basic normalization: lowercase and strip whitespace
        return text.strip().lower()
