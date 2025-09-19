# Spell Logic Module for HuleEdu Spell Checker Service

## Overview

This module contains the core business logic for preparing and applying spelling corrections within the HuleEdu Spell Checker Service. Its primary goal is to perform accurate spell correction, with an initial focus on common L2 (Second Language) learner errors, followed by a general-purpose spell checker. The design emphasizes deterministic corrections and careful handling of L2 characteristics.

The spell correction process within this module, as utilized by the parent `spellchecker_service`, involves a multi-stage approach:

1. **L2 Error Dictionary Loading**: An L2 error dictionary (typically pre-filtered) is loaded. This dictionary maps common L2 misspellings to their correct forms.
2. **Initial L2 Correction Application**: The loaded L2 dictionary is used to perform an initial wave of spelling corrections on the input essay text.
3. **Main Spell Checking**: The "L2-corrected text" is then processed by a main spell checker, which is currently `pyspellchecker`.

The module provides utilities for loading L2 dictionaries, applying these corrections, filtering L2 dictionaries based on heuristic rules, and logging the correction process.

## Module Components and Workflow

### 1. L2 Dictionary Management

* **`l2_dictionary_loader.py`**:
  * `load_l2_errors()`: Loads L2 error-correction pairs from a specified file path. It can optionally apply filtering during loading if the `l2_filter` module is available and `filter_entries` is true.
  * `apply_l2_corrections()`: Applies corrections from a loaded L2 dictionary to an input text, preserving case and handling basic tokenization.
  * `apply_specific_corrections()`: Applies a given list of specific corrections to text, rather than using a full dictionary lookup.
  * `create_filtered_l2_dictionary()`: A utility function that uses `l2_filter.py` to generate a filtered L2 dictionary file from a given dictionary. *(Note: In the main service workflow, `core_logic.py` typically loads a pre-filtered dictionary path from settings).*

* **`l2_filter.py`**:
  * `L2CorrectionFilter`: A class that implements simple, non-contextual heuristic rules for validating L2 error-correction pairs. Rules include checks for pluralization changes and word length. This filter does **not** use SpaCy or complex linguistic analysis.
  * `filter_l2_entries()`: Applies the `L2CorrectionFilter` to a dictionary of L2 errors.
  * `create_filtered_l2_dictionary()`: Writes a filtered L2 dictionary to a file.

### 2. Core Spell Checking Algorithm Orchestration

Runtime orchestration now lives in the shared `SpellNormalizer` (defined in `libs/huleedu_nlp_shared/normalization/spell_normalizer.py`). The service constructs a singleton normalizer via dependency injection and reuses it for every request:

1. Loads the (typically pre-filtered) L2 error dictionary using `load_l2_errors()` from `l2_dictionary_loader.py` (at service startup).
2. Applies these L2 corrections to the input text using `apply_l2_corrections()` from `l2_dictionary_loader.py`.
3. Initializes and runs `pyspellchecker` on the L2-corrected text (respecting whitelist exclusions and adaptive edit distance).
4. Optionally logs detailed correction information via `correction_logger.py`.

### 3. Correction Logging

* **`correction_logger.py`**:
  * `log_essay_corrections()`: Provides detailed logging of the text at various stages: original, after initial L2 corrections, and after main spell checker corrections. It generates diffs to highlight changes. This is crucial for debugging and understanding the impact of each correction stage.

## Current Approach and Philosophy

* **Focus on L2 Dictionary Quality**: The primary strategy for preventing meaning-altering L2 corrections relies on the rigorous curation of the master L2 error dictionary (e.g., `nortvig_master_SWE_L2_corrections.txt`).
* **Conservative Filtering**: The `l2_filter.py` module applies high-precision, non-contextual rules. This ensures that the filtered L2 dictionary used in production is based on conservative heuristics.
* **Two-Stage Correction**: The process involves initial L2 corrections followed by a general spell checker (`pyspellchecker`).
* **Detailed Logging**: Comprehensive logging via `correction_logger.py` enables continuous analysis and refinement of both the L2 dictionary and the filtering rules.

## Key Files in this Module

* `__init__.py`: Package initializer.
* `l2_dictionary_loader.py`: Handles loading and application of L2 error corrections.
* `l2_filter.py`: Provides conservative filtering for L2 error-correction pairs.
* `correction_logger.py`: Utility for logging detailed correction information.

## Integration with Spell Checker Service

This `spell_logic` module provides the core algorithms and data handling capabilities that are orchestrated by the `SpellNormalizer` and the service's event processor. Configuration for dictionary paths, logging, and spell checker language is sourced from the service's main `config.py`.

---

This README should now better reflect the current structure and functionality of your `spell_logic` module.
