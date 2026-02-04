"""spaCy pipeline utilities for the essay scoring research build.

This module centralizes spaCy model loading for both:

- The local research pipeline (`scripts.ml_training.essay_scoring.features.*`)
- The Hemma offload server (`scripts.ml_training.essay_scoring.offload.spacy_runtime`)

Keeping this in one place makes it easier to tune performance (e.g., disabling
unused pipeline components) while ensuring the same NLP semantics are used
across local and offloaded feature extraction.
"""

from __future__ import annotations

from collections.abc import Sequence

import spacy
import textdescriptives
from spacy.language import Language


def ensure_textdescriptives_readability(nlp: Language) -> None:
    """Ensure the TextDescriptives readability component is attached."""

    _ = textdescriptives.__version__
    if "textdescriptives/readability" not in nlp.pipe_names:
        nlp.add_pipe("textdescriptives/readability", last=True)


def load_spacy_model(
    model_name: str,
    *,
    enable_readability: bool = True,
    disable_components: Sequence[str] | None = None,
) -> Language:
    """Load a spaCy model for the essay scoring pipeline.

    Tier 1 requires TextDescriptives readability metrics; Tier 2 and Tier 3 do not.
    """

    nlp = spacy.load(model_name, disable=list(disable_components or ()))
    if enable_readability:
        ensure_textdescriptives_readability(nlp)
    return nlp
