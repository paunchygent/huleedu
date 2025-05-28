# Spell Checker Module for CJ Essay Assessment

## Overview

This module is designed to prepare student essays for AI-driven Comparative Judgement (CJ) assessment. Its primary objective is to perform accurate, deterministic spell correction while meticulously preserving other genuine linguistic errors (grammatical, syntactical, etc.) that are characteristic of L2 learner writing. This targeted approach helps AI judges focus on task fulfillment, content quality, and overall language proficiency, rather than being misled or distracted by basic spelling mistakes.

The spell checker employs a multi-stage process:

1.  **L2 Error Dictionary Generation (Conservative Filter)**: An up-to-date "production L2 dictionary" (`filtered_l2_dictionary.txt`) is created from a master list of L2 errors (`nortvig_master_SWE_L2_corrections.txt`). This generation uses a conservative filtering mechanism (`l2_filter.py`) which relies on high-precision, non-contextual rules (e.g., pluralization checks, length heuristics). SpaCy-based contextual validation for individual corrections has been removed due to unsuitability. This ensures the production dictionary is consistently based on the latest master list and is filtered conservatively.
2.  **Initial L2 Correction Application**: The production L2 dictionary (`filtered_l2_dictionary.txt`) is used to perform an initial wave of spelling corrections on the input essay.
3.  **Main Spell Checking**: The resulting "L2-corrected text" is then processed by a main rule-based spell checker (e.g., NorvigSweeting via Spark NLP).

The emphasis is on rule-based methods, curated dictionaries, and a simplified, robust filtering process to ensure deterministic and reliable output. The primary defense against meaning-altering L2 corrections is now the rigorous curation of the `nortvig_master_SWE_L2_corrections.txt` and the conservative, non-spaCy rules in `l2_filter.py`.

## Current Workflow and Interdependencies

The spell-checking process is orchestrated as follows:

1.  **Production L2 Dictionary Generation (`l2_filter.py` & `l2_dictionary_loader.py`)**:
    * At the start of processing (e.g., in `spell_check_pipeline.py`), the `nortvig_master_SWE_L2_corrections.txt` is loaded.
    * `l2_dictionary_loader.create_filtered_l2_dictionary()` (which calls `l2_filter.create_filtered_l2_dictionary`) processes this master list.
    * The `L2CorrectionFilter` class within `l2_filter.py` applies conservative, non-spaCy-based rules (e.g., for pluralizations, length checks) to validate pairs from the master list. SpaCy-dependent validation has been removed from this filter.
    * The filtering step now has **no spaCy dependency**, ensuring deterministic behavior even in minimal environments.
    * The output is `filtered_l2_dictionary.txt`, a conservatively filtered set of L2 error corrections.

2.  **L2 Correction Application (`l2_dictionary_loader.py`)**:
    * The `filtered_l2_dictionary.txt` (generated in step 1) is loaded by `l2_dictionary_loader.load_l2_errors()`.
    * `l2_dictionary_loader.apply_l2_corrections()` uses this dictionary to perform find-and-replace operations on the original essay text.
    * This step produces the "L2-corrected text" and a list detailing each specific correction made (`applied_l2_corrections`).

3.  **Main Spell Checking Orchestration (`spell_check_pipeline.py`)**:
    * This module (to be potentially renamed, e.g., `spell_check_orchestrator.py`) coordinates the pipeline.
    * `run_spellcheck()`:
        1.  Orchestrates steps 1 and 2 (L2 dictionary generation and application).
        2.  Initializes a Spark NLP session and defines a pipeline (DocumentAssembler, SentenceDetector, Tokenizer, and a chosen spell checker model like NorvigSweetingModel).
        3.  Feeds the **`L2-corrected text`** (output from step 2) directly into the Spark NLP pipeline. The contextual spaCy validation step has been removed.
        4.  Uses `utils.correction_logger_util.log_essay_corrections` to log the original text, the `L2-corrected text` (and the L2 changes that produced it), and the final Spark NLP spell-checked tokens.
        5.  Reconstructs the final corrected text from Spark NLP tokens.

4.  **Correction Logging (`utils/correction_logger_util.py`)**:
    * `log_essay_corrections()`: Logs the state of the essay at various stages (original, L2-corrected, Spark NLP corrected). This utility is vital for debugging and understanding the impact of the L2 dictionary and the main spell checker.

## Lessons Learned & Revised Approach

* **SpaCy Contextual Validation Removed**: The previous approach of using spaCy for contextual PoS/lemma validation of each L2 correction has been discontinued due to its unreliability and tendency to incorrectly reject valid spelling fixes in this specific application.
* **Focus on Dictionary Quality and Conservative Filtering**: The primary strategy for preventing meaning-altering L2 corrections now relies on:
    1.  **Rigorous Curation of `nortvig_master_SWE_L2_corrections.txt`**: Ensuring this master dictionary primarily contains pure spelling errors.
    2.  **Conservative, Non-SpaCy Rules in `l2_filter.py`**: This filter, used to generate `filtered_l2_dictionary.txt`, will employ high-precision rules that do not depend on complex contextual linguistic analysis by spaCy. Development of these rules will be an ongoing, expert-driven process.
* **Iterative Refinement**: The system's strength for improvement lies in detailed logging (`utils.correction_logger_util.py`), which enables continuous analysis of the L2 corrections applied (from `filtered_l2_dictionary.txt`) and the subsequent Spark NLP output. This feedback loop is crucial for:
    * Curating `nortvig_master_SWE_L2_corrections.txt`.
    * Refining the conservative rules in `l2_filter.py`.

## Key Focus for Ongoing Development

* **Simplifying `l2_filter.py`**: Initially, removing spaCy-dependent logic from `l2_filter.py` to make it a very lean, conservative filter based on existing non-spaCy rules (like pluralization and length checks).
* **Improving Curation of `nortvig_master_SWE_L2_corrections.txt`**: Establishing robust processes to ensure the quality and focus of this master L2 error list.
* **(Future, User-Led) Designing Advanced Non-SpaCy Rules for `l2_filter.py`**: Developing more sophisticated, high-precision filtering rules for `l2_filter.py` based on linguistic expertise, without relying on runtime spaCy PoS/lemma tagging for individual correction validation.
* **Streamlining `spell_check_pipeline.py`**: Ensuring the pipeline orchestrator correctly implements the simplified workflow.
* **Adapting `utils.correction_logger_util.py`**: Modifying the logger to accurately reflect the new two-stage correction process (Initial L2 corrections -> Spark NLP).

## Future Directions (Post-Testing and Integration)

* Integrate the `spell_checker` module into the larger application, including transitioning dictionary paths and other configurations to a central system.
* Consider renaming `spell_check_pipeline.py` (e.g., to `spell_check_orchestrator.py`).
* Develop comprehensive unit and integration tests for the simplified pipeline components.

## Module Initialization (`spell_checker/__init__.py`)

The `spell_checker` package exposes key components:
* `run_spellcheck` (from `spell_check_pipeline.py`)
* Functions from `l2_dictionary_loader` (e.g., `load_l2_errors`, `apply_l2_corrections`)
* Components from `l2_filter` (e.g., `L2CorrectionFilter`, `create_filtered_l2_dictionary`)

---

This revised `README.md` should now accurately reflect our current, simplified approach.