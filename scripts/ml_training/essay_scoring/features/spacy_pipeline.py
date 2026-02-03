"""Shared spaCy pipeline loader for the essay scoring research build."""

from __future__ import annotations

import spacy
import textdescriptives
from spacy.language import Language


def ensure_textdescriptives_readability(nlp: Language) -> None:
    """Ensure the TextDescriptives readability component is attached."""

    _ = textdescriptives.__version__
    if "textdescriptives/readability" not in nlp.pipe_names:
        nlp.add_pipe("textdescriptives/readability", last=True)


def load_spacy_model(model_name: str, *, enable_readability: bool = True) -> Language:
    """Load a spaCy model for the essay scoring pipeline.

    Tier 1 requires TextDescriptives readability metrics; Tier 2 and Tier 3 do not.
    """

    nlp = spacy.load(model_name)
    if enable_readability:
        ensure_textdescriptives_readability(nlp)
    return nlp
