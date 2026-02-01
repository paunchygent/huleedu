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


def load_spacy_model(model_name: str) -> Language:
    """Load a spaCy model and attach TextDescriptives readability."""

    nlp = spacy.load(model_name)
    ensure_textdescriptives_readability(nlp)
    return nlp
