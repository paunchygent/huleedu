"""Default implementation of WhitelistProtocol."""

from __future__ import annotations

from pathlib import Path

from huleedu_service_libs.logging_utils import create_service_logger

from services.spellchecker_service.config import Settings
from services.spellchecker_service.protocols import WhitelistProtocol

logger = create_service_logger("spellchecker_service.whitelist_impl")


class DefaultWhitelist(WhitelistProtocol):
    """Default whitelist implementation that loads names at startup.

    Following the same pattern as L2 dictionary:
    - Load once at service startup (APP scope in DI)
    - Cache in memory as a set for O(1) lookup
    - Case-insensitive matching
    """

    def __init__(self, settings: Settings):
        """Initialize whitelist by loading from file.

        Args:
            settings: Service settings containing data paths
        """
        self.whitelist: set[str] = set()

        # Construct path to combined whitelist file
        # Use absolute path - following HuleEdu pattern
        whitelist_path = Path(
            "/Users/olofs_mba/Documents/Repos/huledu-reboot/services/spellchecker_service/data/whitelist/combined_whitelist.txt"
        )

        if not whitelist_path.exists():
            logger.warning(
                f"Whitelist file not found at {whitelist_path}. "
                "Spell checker will flag all proper names as errors."
            )
            return

        logger.info(f"Loading whitelist from {whitelist_path}")

        try:
            with open(whitelist_path, "r", encoding="utf-8") as f:
                for line in f:
                    name = line.strip()
                    if name:
                        # Store lowercase for case-insensitive matching
                        self.whitelist.add(name.lower())

            logger.info(
                f"Whitelist loaded successfully: {len(self.whitelist):,} entries, "
                f"estimated memory usage: ~{len(self.whitelist) * 50 / 1024 / 1024:.1f} MB"
            )

            # Log some sample entries for verification
            if self.whitelist:
                sample = list(sorted(self.whitelist))[:10]
                logger.debug(f"Sample whitelist entries: {sample}")

        except Exception as e:
            logger.error(f"Failed to load whitelist: {e}", exc_info=True)
            # Continue with empty whitelist rather than failing startup

    def is_whitelisted(self, word: str) -> bool:
        """Check if word is in the whitelist.

        Args:
            word: Word to check (case-insensitive)

        Returns:
            True if word is whitelisted, False otherwise
        """
        # Lowercase for case-insensitive matching
        return word.lower() in self.whitelist
