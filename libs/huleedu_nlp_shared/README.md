# HuleEdu NLP Shared Library

Shared NLP processing components for HuleEdu services and tooling, currently providing the three-stage spell normalization pipeline extracted from Spellchecker Service.

## Key Features

- **Three-Stage Pipeline**: Whitelist filtering → Swedish L2 corrections → PySpellChecker
- **Protocol-Based**: Dependency injection via `WhitelistProtocol`, `ParallelProcessorProtocol`
- **Performance Optimized**: Singleton SpellChecker cache, optional parallel processing
- **Service Integration**: DI-ready with Dishka providers

## Structure

``` text
huleedu_nlp_shared/
├── normalization/
│   ├── __init__.py           # Public exports
│   ├── models.py             # SpellNormalizationResult
│   ├── protocols.py          # Protocol interfaces
│   └── spell_normalizer.py   # Core normalization logic
└── tests/
    └── normalization/        # Unit tests
```

## Installation

```toml
# In service pyproject.toml
dependencies = [
    "huleedu-nlp-shared",
]
```

## API Reference

### SpellNormalizer

```python
class SpellNormalizer:
    def __init__(
        self,
        *,
        l2_errors: dict[str, str],
        whitelist: WhitelistProtocol | None,
        parallel_processor: ParallelProcessorProtocol | None,
        settings: SpellcheckerSettingsProtocol,
        logger_override: logging.Logger | None = None,
    )

    async def normalize_text(
        self,
        *,
        text: str,
        essay_id: str | None = None,
        language: str = "en",
        correlation_id: UUID | None = None,
        # Optional overrides for parallel processing
    ) -> SpellNormalizationResult
```

### SpellNormalizationResult

```python
class SpellNormalizationResult(BaseModel):
    corrected_text: str
    total_corrections: int
    l2_dictionary_corrections: int
    spellchecker_corrections: int
    word_count: int
    correction_density: float  # Per 100 words
```

## Service Integration

### Dishka Provider Setup

```python
# services/spellchecker_service/di.py
class SpellCheckerServiceProvider(Provider):
    @provide(scope=Scope.APP)
    def provide_l2_errors(self, settings: Settings) -> dict[str, str]:
        return load_l2_errors(
            settings.effective_filtered_dict_path,
            filter_entries=False
        )

    @provide(scope=Scope.APP)
    def provide_spell_normalizer(
        self,
        l2_errors: dict[str, str],
        whitelist: WhitelistProtocol,
        parallel_processor: ParallelProcessorProtocol,
        settings: Settings,
    ) -> SpellNormalizer:
        return SpellNormalizer(
            l2_errors=l2_errors,
            whitelist=whitelist,
            parallel_processor=parallel_processor,
            settings=settings,
        )
```

### Usage in Business Logic

```python
class DefaultSpellLogic(SpellLogicProtocol):
    def __init__(self, spell_normalizer: SpellNormalizer):
        self.spell_normalizer = spell_normalizer

    async def perform_spell_check(
        self, text: str, essay_id: str, correlation_id: UUID
    ) -> SpellcheckResultDataV1:
        result = await self.spell_normalizer.normalize_text(
            text=text,
            essay_id=essay_id,
            correlation_id=correlation_id,
        )
        # Process result...
```

## Protocol Implementations

### WhitelistProtocol

```python
class WhitelistProtocol(Protocol):
    def is_whitelisted(self, word: str) -> bool:
        ...
```

### ParallelProcessorProtocol

```python
class ParallelProcessorProtocol(Protocol):
    async def process_corrections_parallel(
        self,
        words_to_correct: list[tuple[int, str]],
        spell_checker_cache: dict[str, Any],
        correlation_id: UUID,
        essay_id: str | None = None,
    ) -> dict[int, tuple[str | None, float]]:
        ...
```

### SpellcheckerSettingsProtocol

```python
class SpellcheckerSettingsProtocol(Protocol):
    ENABLE_PARALLEL_PROCESSING: bool
    MAX_CONCURRENT_CORRECTIONS: int
    SPELLCHECK_BATCH_SIZE: int
    PARALLEL_TIMEOUT_SECONDS: float
    PARALLEL_PROCESSING_MIN_WORDS: int
    ENABLE_CORRECTION_LOGGING: bool

    @property
    def effective_correction_log_dir(self) -> str:
        ...
```

## Configuration

Services provide configuration via settings object:

- `L2_DICTIONARY_PATH`: Path to L2 errors JSON
- `WHITELIST_PATH`: Path to whitelist file
- `ENABLE_PARALLEL_PROCESSING`: Enable parallel corrections
- `MAX_CONCURRENT_CORRECTIONS`: Concurrency limit
- `ENABLE_CORRECTION_LOGGING`: Enable detailed logs

## Testing

```python
import pytest
from huleedu_nlp_shared.normalization import SpellNormalizer

@pytest.mark.asyncio
async def test_normalization():
    normalizer = SpellNormalizer(
        l2_errors={"teh": "the"},
        whitelist=MockWhitelist(["HuleEdu"]),
        parallel_processor=None,
        settings=TestSettings(),
    )

    result = await normalizer.normalize_text(text="teh test")
    assert result.corrected_text.startswith("the")
    assert result.l2_dictionary_corrections == 1
```

## Notes

- L2 dictionary loaded once at startup via DI, not per-request
- Global `_spellchecker_cache` shared across all normalizer instances
- Parallel processing recommended for texts >1000 words
