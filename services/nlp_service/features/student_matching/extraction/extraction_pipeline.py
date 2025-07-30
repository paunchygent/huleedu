"""Orchestrator for running multiple extraction strategies."""

from __future__ import annotations

from typing import Any

from huleedu_service_libs.logging_utils import create_service_logger

from ..models import ExtractedIdentifier, ExtractionResult
from .base_extractor import BaseExtractor

logger = create_service_logger("nlp_service.extraction.pipeline")


class ExtractionPipeline:
    """Orchestrates multiple extraction strategies with early exit."""

    def __init__(
        self,
        strategies: list[BaseExtractor],
        confidence_threshold: float = 0.7,
        max_strategies: int = 3,
    ):
        """Initialize the extraction pipeline.

        Args:
            strategies: List of extraction strategies to try in order
            confidence_threshold: Confidence level to trigger early exit
            max_strategies: Maximum number of strategies to try
        """
        self.strategies = strategies
        self.confidence_threshold = confidence_threshold
        self.max_strategies = max_strategies

    async def extract(
        self,
        text: str,
        filename: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ExtractionResult:
        """Run extraction strategies until threshold met or exhausted.

        Args:
            text: The essay text to extract from
            filename: Optional filename hint
            metadata: Optional additional context

        Returns:
            Consolidated ExtractionResult from all strategies tried
        """
        result = ExtractionResult()
        strategies_tried = 0

        logger.info(
            f"Starting extraction pipeline with {len(self.strategies)} strategies",
            extra={"confidence_threshold": self.confidence_threshold},
        )

        for strategy in self.strategies:
            if strategies_tried >= self.max_strategies:
                logger.info(f"Reached max strategies limit ({self.max_strategies})")
                break

            try:
                logger.debug(f"Trying strategy: {strategy.name}")

                # Run the strategy
                strategy_result = await strategy.extract(text, filename, metadata)

                # Merge results
                result = self._merge_results(result, strategy_result)

                strategies_tried += 1

                # Check if we should exit early
                if self._should_exit_early(result):
                    logger.info(
                        f"Exiting early after {strategy.name} - confidence threshold met",
                        extra={
                            "highest_name_confidence": self._get_highest_confidence(
                                result.possible_names
                            ),
                            "highest_email_confidence": self._get_highest_confidence(
                                result.possible_emails
                            ),
                        },
                    )
                    break

            except Exception as e:
                logger.warning(
                    f"Strategy {strategy.name} failed: {e}",
                    exc_info=True,
                    extra={"strategy": strategy.name},
                )
                # Continue with next strategy

        # Update metadata
        result.metadata["strategies_tried"] = strategies_tried
        result.metadata["strategies_available"] = len(self.strategies)
        result.metadata["early_exit"] = strategies_tried < len(self.strategies)

        logger.info(
            "Extraction pipeline completed",
            extra={
                "strategies_tried": strategies_tried,
                "names_found": len(result.possible_names),
                "emails_found": len(result.possible_emails),
            },
        )

        return result

    def _merge_results(self, current: ExtractionResult, new: ExtractionResult) -> ExtractionResult:
        """Merge new extraction results into current results.

        Deduplicates based on value (case-insensitive for emails).
        """
        # Track existing values to avoid duplicates
        existing_names = {ident.value.lower() for ident in current.possible_names}
        existing_emails = {ident.value.lower() for ident in current.possible_emails}

        # Add new names if not duplicates
        for name_ident in new.possible_names:
            if name_ident.value.lower() not in existing_names:
                current.possible_names.append(name_ident)
                existing_names.add(name_ident.value.lower())

        # Add new emails if not duplicates
        for email_ident in new.possible_emails:
            if email_ident.value.lower() not in existing_emails:
                current.possible_emails.append(email_ident)
                existing_emails.add(email_ident.value.lower())

        # Merge metadata
        for key, value in new.metadata.items():
            if key not in current.metadata:
                current.metadata[key] = value
            else:
                # For lists, extend; for dicts, update; otherwise overwrite
                if isinstance(value, list) and isinstance(current.metadata[key], list):
                    current.metadata[key].extend(value)
                elif isinstance(value, dict) and isinstance(current.metadata[key], dict):
                    current.metadata[key].update(value)
                else:
                    current.metadata[key] = value

        return current

    def _should_exit_early(self, result: ExtractionResult) -> bool:
        """Check if we have high enough confidence to exit early."""
        # Check if we have at least one high-confidence name
        if result.possible_names:
            highest_name_conf = self._get_highest_confidence(result.possible_names)
            if highest_name_conf >= self.confidence_threshold:
                # Also should have an email, or very high name confidence
                if result.possible_emails or highest_name_conf >= 0.85:
                    return True

        # Check if we have both name and email with reasonable confidence
        if result.possible_names and result.possible_emails:
            name_conf = self._get_highest_confidence(result.possible_names)
            email_conf = self._get_highest_confidence(result.possible_emails)

            # If we have both with decent confidence, we can exit
            if name_conf >= 0.6 and email_conf >= 0.8:
                return True

        return False

    def _get_highest_confidence(self, identifiers: list[ExtractedIdentifier]) -> float:
        """Get the highest confidence score from a list of identifiers."""
        if not identifiers:
            return 0.0
        return max(ident.confidence for ident in identifiers)
