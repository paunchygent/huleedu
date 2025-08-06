"""Mock implementations for testing."""

from unittest.mock import AsyncMock, MagicMock

from services.spellchecker_service.protocols import ParallelProcessorProtocol, WhitelistProtocol


class MockWhitelist(WhitelistProtocol):
    """Mock whitelist that never whitelists anything (default behavior)."""

    def __init__(self, whitelisted_words: set[str] | None = None):
        """Initialize with optional set of whitelisted words.

        Args:
            whitelisted_words: Optional set of words to whitelist (lowercase)
        """
        self.whitelisted_words = whitelisted_words or set()

    def is_whitelisted(self, word: str) -> bool:
        """Check if word is whitelisted.

        Args:
            word: Word to check

        Returns:
            True if word is in whitelist, False otherwise
        """
        return word.lower() in self.whitelisted_words


def create_mock_parallel_processor() -> ParallelProcessorProtocol:
    """Create a mock parallel processor for tests.

    Returns:
        Mock parallel processor that returns empty corrections dict
    """
    mock = MagicMock(spec=ParallelProcessorProtocol)
    mock.process_corrections_parallel = AsyncMock(return_value={})
    return mock
