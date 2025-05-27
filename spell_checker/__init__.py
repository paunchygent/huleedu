"""
Spell Checker Module

This package provides advanced spell checking and L2 error correction functionality
for the essay assessment system. It includes tools for loading, filtering, and
applying spelling corrections with support for handling various linguistic patterns
common in second language learners' writing.

Main Components:
    - spell_check_pipeline.py: Main orchestrator for the spell checking pipeline
    - l2_dictionary_loader: Load and apply L2 corrections from dictionary files
    - l2_filter: Filter and validate corrections using linguistic analysis

Usage:
    The main entry point is through the `run_spellcheck` function which can be
    used to process essays with the full spell checking pipeline.
"""

from .l2_dictionary_loader import (apply_l2_corrections,
                                   create_filtered_l2_dictionary,
                                   create_word_boundaries_map, load_l2_errors)
from .l2_filter import L2CorrectionFilter, filter_l2_entries
# Import the main spell checking function
from .spell_check_pipeline import run_spellcheck

__all__ = [
    # Main function
    "run_spellcheck",
    # L2 Dictionary Loader
    "load_l2_errors",
    "apply_l2_corrections",
    "create_filtered_l2_dictionary",
    "create_word_boundaries_map",
    # L2 Filter
    "L2CorrectionFilter",
    "filter_l2_entries",
]
