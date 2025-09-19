# TASK-052L.0.2 — Spell Normalizer Extraction Implementation Plan (CORRECTED)

## Objective

Extract the existing spell correction pipeline from `services/spellchecker_service` into a shared library `libs/huleedu_nlp_shared` for reuse between runtime services and offline tooling. NO new logic, NO improvements - pure extraction maintaining existing patterns.

## Critical Corrections from Review

This plan has been corrected based on code review findings:
- ✅ Fixed non-existent file references (adaptive_distance.py doesn't exist)
- ✅ Corrected all line numbers to match actual code
- ✅ Fixed constructor signatures (DefaultWhitelist takes Settings, not path)
- ✅ Removed hallucinated WHITELIST_PATH configuration
- ✅ Preserved singleton pattern for settings

## Phase 1: Create Shared Library Structure

### 1.1 Create Package Structure
```bash
# Create directories
mkdir -p libs/huleedu_nlp_shared/src/huleedu_nlp_shared/normalization
mkdir -p libs/huleedu_nlp_shared/tests/normalization

# Create package files
touch libs/huleedu_nlp_shared/pyproject.toml
touch libs/huleedu_nlp_shared/src/huleedu_nlp_shared/__init__.py
touch libs/huleedu_nlp_shared/src/huleedu_nlp_shared/py.typed
```

### 1.2 Package Configuration
```toml
# libs/huleedu_nlp_shared/pyproject.toml
[project]
name = "huleedu-nlp-shared"
version = "0.1.0"
description = "Shared NLP utilities for HuleEdu services"
dependencies = [
    "pydantic>=2.5.0",
    "pyspellchecker>=0.8.0",
    "aiohttp>=3.9.0",
]

[project.optional-dependencies]
test = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
]

[build-system]
requires = ["pdm-backend"]
build-backend = "pdm.backend"
```

## Phase 2: Extract Core Components (VERIFIED)

### 2.1 Files to Extract From (CORRECTED LINE NUMBERS)

#### VERIFIED SOURCE FILES:
1. **`services/spellchecker_service/core_logic.py`**
   - Function: `default_perform_spell_check_algorithm` (lines 44-551)
   - Global: `_spellchecker_cache` (line 41)

2. **`services/spellchecker_service/spell_logic/l2_dictionary_loader.py`**
   - Function: `load_l2_errors` (lines 37-100)
   - Function: `filter_l2_entries` (lines 11-34)

3. **`services/spellchecker_service/implementations/whitelist_impl.py`**
   - Class: `DefaultWhitelist` (entire file)
   - **NOTE**: Constructor takes Settings object, not path

4. **`services/spellchecker_service/implementations/parallel_processor_impl.py`**
   - Class: `DefaultParallelProcessor` (entire file)
   - Function: `get_adaptive_edit_distance` (lines 18-35)
   - **NOTE**: No constructor parameters, uses imported settings

5. **`services/spellchecker_service/protocols.py`**
   - Protocol: `WhitelistProtocol` (lines 69-74)
   - Protocol: `ParallelProcessorProtocol` (lines 77-88)

### 2.2 Core Algorithm Migration Strategy

Since components use singleton settings pattern, we need to refactor carefully:

#### Option A: Minimal Change (RECOMMENDED)
Keep singleton pattern in shared library, pass settings at module level:

```python
# libs/huleedu_nlp_shared/src/huleedu_nlp_shared/normalization/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class NormalizationSettings(BaseSettings):
    """Settings for spell normalization."""
    model_config = SettingsConfigDict(env_prefix="SPELLCHECK_")

    # From existing spellchecker service config
    L2_DICT_PATH: str = Field(default="./data/l2_errors.txt")
    WHITELIST_DIR: str = Field(default="./data/whitelist")
    ENABLE_PARALLEL_PROCESSING: bool = Field(default=True)
    MAX_CONCURRENT_CORRECTIONS: int = Field(default=10)
    SPELLCHECK_BATCH_SIZE: int = Field(default=100)
    PARALLEL_TIMEOUT_SECONDS: float = Field(default=5.0)
    PARALLEL_PROCESSING_MIN_WORDS: int = Field(default=5)

# Singleton instance
normalization_settings = NormalizationSettings()
```

### 2.3 Create Models
```python
# libs/huleedu_nlp_shared/src/huleedu_nlp_shared/normalization/models.py
from pydantic import BaseModel, Field

class SpellNormalizationResult(BaseModel):
    """Result from spell normalization process."""
    corrected_text: str = Field(description="Text after all corrections")
    total_corrections: int = Field(description="Total corrections made")
    l2_corrections: int = Field(description="L2 learner error corrections")
    spelling_corrections: int = Field(description="General spelling corrections")
    word_count: int = Field(description="Total word count")
    correction_density: float = Field(description="Corrections per 100 words")

    def to_feature_dict(self) -> dict[str, float]:
        """Convert to feature dictionary for ML pipeline."""
        return {
            "spelling_error_rate_p100w": self.correction_density,
            "l2_error_count": float(self.l2_corrections),
            "spelling_error_count": float(self.spelling_corrections),
        }
```

### 2.4 Extract L2 Dictionary Loader
```python
# libs/huleedu_nlp_shared/src/huleedu_nlp_shared/normalization/l2_dictionary.py
# Copy EXACTLY from services/spellchecker_service/spell_logic/l2_dictionary_loader.py
# Lines 1-100 (entire file)

import logging
import os

logger = logging.getLogger(__name__)

def filter_l2_entries(l2_errors: dict[str, str]) -> dict[str, str]:
    """Filter L2 entries to remove problematic corrections."""
    # Lines 11-34 from original
    ...

def load_l2_errors(filename: str, filter_entries: bool = True) -> dict[str, str]:
    """Load L2 errors and their corrections from a file."""
    # Lines 37-100 from original
    ...
```

### 2.5 Extract Whitelist (MAINTAINING SETTINGS PATTERN)
```python
# libs/huleedu_nlp_shared/src/huleedu_nlp_shared/normalization/whitelist.py
import logging
from pathlib import Path
from .config import normalization_settings

logger = logging.getLogger(__name__)

class DefaultWhitelist:
    """Default whitelist implementation using settings."""

    def __init__(self):
        """Initialize whitelist from configured directory."""
        # Adapt from lines 24-44 of whitelist_impl.py
        # Use normalization_settings.WHITELIST_DIR instead of settings.WHITELIST_DIR
        self.whitelist_dir = Path(normalization_settings.WHITELIST_DIR)
        self.whitelisted_words = self._load_whitelist()

    def _load_whitelist(self) -> set[str]:
        """Load whitelist from files."""
        # Copy implementation from whitelist_impl.py lines 46-75
        ...

    def is_whitelisted(self, word: str) -> bool:
        """Check if word is whitelisted."""
        # Copy from lines 77-85
        return word.lower() in self.whitelisted_words
```

### 2.6 Extract Parallel Processor
```python
# libs/huleedu_nlp_shared/src/huleedu_nlp_shared/normalization/parallel_processor.py
# Copy from services/spellchecker_service/implementations/parallel_processor_impl.py

import asyncio
import logging
from typing import Dict, Any
from uuid import UUID
from .config import normalization_settings

logger = logging.getLogger(__name__)

def get_adaptive_edit_distance(word: str) -> int:
    """Determine optimal edit distance based on word length."""
    # Copy lines 18-35 from parallel_processor_impl.py
    ...

class DefaultParallelProcessor:
    """Default implementation of parallel word correction."""

    async def process_corrections_parallel(
        self,
        words_to_correct: list[tuple[int, str]],
        spell_checker_cache: Dict[str, Any],
        correlation_id: UUID,
        essay_id: str | None = None,
    ) -> dict[int, tuple[str | None, float]]:
        """Process word corrections in parallel."""
        # Copy implementation from lines 39-134
        ...
```

### 2.7 Create Main Normalizer
```python
# libs/huleedu_nlp_shared/src/huleedu_nlp_shared/normalization/spell_normalizer.py
import logging
import time
from typing import Dict, Any
from uuid import UUID

from .models import SpellNormalizationResult
from .l2_dictionary import load_l2_errors
from .whitelist import DefaultWhitelist
from .parallel_processor import DefaultParallelProcessor, get_adaptive_edit_distance
from .config import normalization_settings

logger = logging.getLogger(__name__)

# Global cache (matching existing pattern from core_logic.py line 41)
_spellchecker_cache: Dict[str, Any] = {}

async def normalize_text(
    text: str,
    language: str = "en",
    essay_id: str | None = None,
    correlation_id: UUID | None = None,
) -> SpellNormalizationResult:
    """Normalize text using L2 dictionary and PySpellChecker.

    This is a DIRECT PORT of default_perform_spell_check_algorithm
    from services/spellchecker_service/core_logic.py lines 44-551
    """
    # Initialize components using singleton pattern
    l2_errors = load_l2_errors(
        normalization_settings.L2_DICT_PATH,
        filter_entries=False
    )
    whitelist = DefaultWhitelist()
    parallel_processor = DefaultParallelProcessor()

    # Copy EXACT implementation from core_logic.py lines 44-551
    # Phase 1: L2 corrections (lines 90-131)
    # Phase 2: PySpellChecker corrections (lines 133-445)
    # Return result (lines 447-551)

    # ... exact implementation ...

    return SpellNormalizationResult(
        corrected_text=corrected_text,
        total_corrections=total_corrections,
        l2_corrections=len(l2_corrections),
        spelling_corrections=len(pyspellchecker_corrections),
        word_count=word_count,
        correction_density=correction_density,
    )
```

## Phase 3: Update Spellchecker Service (CORRECTED)

### 3.1 Add Feature Flag
```python
# services/spellchecker_service/config.py
# Add to existing Settings class (after line 90):
USE_SHARED_NORMALIZER: bool = Field(
    default=False,
    description="Use shared normalizer from huleedu_nlp_shared",
    validation_alias="SPELLCHECK_USE_SHARED_NORMALIZER",
)
```

### 3.2 Update DefaultSpellLogic (CORRECTED)
```python
# services/spellchecker_service/implementations/spell_logic_impl.py
# Modify __init__ method (lines 42-58):

def __init__(
    self,
    result_store: ResultStoreProtocol,
    http_session: aiohttp.ClientSession,
    whitelist: WhitelistProtocol,
    parallel_processor: ParallelProcessorProtocol,
):
    self.result_store = result_store
    self.http_session = http_session
    self.whitelist = whitelist
    self.parallel_processor = parallel_processor

    if settings.USE_SHARED_NORMALIZER:
        # Shared normalizer will load its own L2 dictionary
        self.use_shared = True
    else:
        # Keep existing implementation
        logger.info("Loading L2 dictionary at service startup...")
        self.l2_errors = load_l2_errors(settings.effective_filtered_dict_path, filter_entries=False)
        logger.info(f"L2 dictionary cached at startup: {len(self.l2_errors)} entries")
        self.use_shared = False

# Modify perform_spell_check method (lines 60-233):
async def perform_spell_check(self, ...):
    if self.use_shared:
        from huleedu_nlp_shared.normalization.spell_normalizer import normalize_text
        from huleedu_nlp_shared.normalization.models import SpellNormalizationResult

        norm_result = await normalize_text(
            text=text,
            language=language,
            essay_id=essay_id,
            correlation_id=correlation_id,
        )
        corrected_text = norm_result.corrected_text
        corrections_count = norm_result.total_corrections
    else:
        # Keep existing implementation (lines 95-118)
        metrics = await default_perform_spell_check_algorithm(
            text,
            self.l2_errors,
            essay_id,
            language=language,
            correlation_id=correlation_id,
            whitelist=self.whitelist,
            parallel_processor=self.parallel_processor,
            # ... rest of parameters
        )
        corrected_text = metrics.corrected_text
        corrections_count = metrics.total_corrections

    # Rest of method remains unchanged (storage, event publishing)
```

### 3.3 Add to pyproject.toml
```toml
# services/spellchecker_service/pyproject.toml
# Add to dependencies:
dependencies = [
    # ... existing dependencies ...
    "huleedu-nlp-shared @ file:///${PROJECT_ROOT}/libs/huleedu_nlp_shared",
]
```

## Phase 4: Testing & Validation

### 4.1 Regression Test
```python
# services/spellchecker_service/tests/test_shared_normalizer_regression.py
import pytest
from services.spellchecker_service.core_logic import default_perform_spell_check_algorithm
from services.spellchecker_service.spell_logic.l2_dictionary_loader import load_l2_errors
from services.spellchecker_service.implementations.whitelist_impl import DefaultWhitelist
from services.spellchecker_service.implementations.parallel_processor_impl import DefaultParallelProcessor
from services.spellchecker_service.config import settings

@pytest.mark.asyncio
async def test_normalizer_produces_identical_results():
    """Verify shared normalizer produces identical results to original."""
    test_text = "This is a tst with som misspeled words"

    # Original implementation
    l2_errors = load_l2_errors(settings.effective_filtered_dict_path, filter_entries=False)
    whitelist = DefaultWhitelist(settings)
    parallel_processor = DefaultParallelProcessor()

    original_result = await default_perform_spell_check_algorithm(
        text=test_text,
        l2_errors=l2_errors,
        language="en",
        whitelist=whitelist,
        parallel_processor=parallel_processor,
        enable_parallel=settings.ENABLE_PARALLEL_PROCESSING,
        max_concurrent=settings.MAX_CONCURRENT_CORRECTIONS,
        batch_size=settings.SPELLCHECK_BATCH_SIZE,
        parallel_timeout=settings.PARALLEL_TIMEOUT_SECONDS,
        min_words_for_parallel=settings.PARALLEL_PROCESSING_MIN_WORDS,
    )

    # Shared implementation
    from huleedu_nlp_shared.normalization.spell_normalizer import normalize_text

    shared_result = await normalize_text(
        text=test_text,
        language="en",
    )

    # Compare results
    assert shared_result.corrected_text == original_result.corrected_text
    assert shared_result.total_corrections == original_result.total_corrections
    assert shared_result.l2_corrections == original_result.l2_dictionary_corrections
    assert shared_result.spelling_corrections == original_result.spellchecker_corrections
```

## Critical Implementation Checklist

### BEFORE Starting:
- [ ] Verify `services/spellchecker_service/core_logic.py` lines 44-551
- [ ] Verify `services/spellchecker_service/spell_logic/l2_dictionary_loader.py` exists
- [ ] Verify `services/spellchecker_service/implementations/whitelist_impl.py` exists
- [ ] Verify `services/spellchecker_service/implementations/parallel_processor_impl.py` exists
- [ ] Confirm whitelist directory path in deployment environment

### MUST PRESERVE:
- [ ] Global `_spellchecker_cache` dictionary
- [ ] Singleton pattern for settings
- [ ] Exact algorithm implementation (no optimizations)
- [ ] All existing logging statements
- [ ] Error handling patterns

### MUST NOT:
- [ ] Change any algorithm logic
- [ ] Add new features or optimizations
- [ ] Modify error messages
- [ ] Change function behavior
- [ ] Create multiple instances of components

## Acceptance Criteria

1. **Functional Parity**: Shared normalizer produces identical output
2. **Performance**: No regression (< 5% difference) in processing time
3. **Testing**: All existing spellchecker tests pass with flag enabled
4. **Backward Compatibility**: Service works with flag disabled
5. **Documentation**: Migration path documented

## Files Summary (CORRECTED)

### New Files Created:
- `libs/huleedu_nlp_shared/pyproject.toml`
- `libs/huleedu_nlp_shared/src/huleedu_nlp_shared/__init__.py`
- `libs/huleedu_nlp_shared/src/huleedu_nlp_shared/py.typed`
- `libs/huleedu_nlp_shared/src/huleedu_nlp_shared/normalization/__init__.py`
- `libs/huleedu_nlp_shared/src/huleedu_nlp_shared/normalization/config.py`
- `libs/huleedu_nlp_shared/src/huleedu_nlp_shared/normalization/models.py`
- `libs/huleedu_nlp_shared/src/huleedu_nlp_shared/normalization/spell_normalizer.py`
- `libs/huleedu_nlp_shared/src/huleedu_nlp_shared/normalization/l2_dictionary.py`
- `libs/huleedu_nlp_shared/src/huleedu_nlp_shared/normalization/whitelist.py`
- `libs/huleedu_nlp_shared/src/huleedu_nlp_shared/normalization/parallel_processor.py`

### Files Modified:
- `services/spellchecker_service/config.py` - Add USE_SHARED_NORMALIZER flag
- `services/spellchecker_service/implementations/spell_logic_impl.py` - Conditional normalizer use
- `services/spellchecker_service/pyproject.toml` - Add dependency