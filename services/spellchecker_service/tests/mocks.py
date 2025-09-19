"""Mock implementations and helpers for testing."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock

from huleedu_nlp_shared.normalization import SpellNormalizer
from huleedu_service_libs.logging_utils import create_service_logger

from services.spellchecker_service.config import settings
from services.spellchecker_service.implementations.spell_logic_impl import DefaultSpellLogic
from services.spellchecker_service.protocols import ParallelProcessorProtocol, WhitelistProtocol
from services.spellchecker_service.spell_logic.l2_dictionary_loader import load_l2_errors


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


def create_spell_normalizer_for_tests(
    whitelist: WhitelistProtocol | None = None,
    parallel_processor: ParallelProcessorProtocol | None = None,
) -> SpellNormalizer:
    """Construct a SpellNormalizer instance with real dictionaries for tests."""

    whitelist_impl = whitelist or MockWhitelist()
    parallel_impl = parallel_processor or create_mock_parallel_processor()
    l2_errors = load_l2_errors(settings.effective_filtered_dict_path, filter_entries=False)
    test_logger = create_service_logger("spellchecker_service.tests.spell_normalizer")

    return SpellNormalizer(
        l2_errors=l2_errors,
        whitelist=whitelist_impl,
        parallel_processor=parallel_impl,
        settings=settings,
        logger_override=test_logger,
    )


def create_default_spell_logic_for_tests(
    result_store: Any,
    http_session: Any,
    whitelist: WhitelistProtocol | None = None,
    parallel_processor: ParallelProcessorProtocol | None = None,
) -> DefaultSpellLogic:
    """Helper to build DefaultSpellLogic with shared spell normalizer."""

    spell_normalizer = create_spell_normalizer_for_tests(
        whitelist=whitelist,
        parallel_processor=parallel_processor,
    )
    return DefaultSpellLogic(
        result_store=result_store,
        http_session=http_session,
        spell_normalizer=spell_normalizer,
    )
