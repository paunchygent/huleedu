"""Data models shared between spell normalization consumers."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SpellNormalizationResult(BaseModel):
    """Metrics describing the output of the spell normalization pipeline."""

    corrected_text: str = Field(description="Text after all spellcheck operations")
    total_corrections: int = Field(description="Total number of corrections applied")
    l2_dictionary_corrections: int = Field(
        description="Number of L2 learner corrections"
    )
    spellchecker_corrections: int = Field(
        description="Number of corrections performed by PySpellChecker"
    )
    word_count: int = Field(description="Total word count in the processed text")
    correction_density: float = Field(
        description="Corrections per 100 words across all correction stages"
    )
