"""spaCy model loading and access for the offload server."""

from __future__ import annotations

from typing import Any

from aiohttp import web

from scripts.ml_training.essay_scoring.features.spacy_pipeline import load_spacy_model
from scripts.ml_training.essay_scoring.offload.http_state import SPACY_NLP_FAST_KEY, SPACY_NLP_KEY


def load_spacy_models(*, app: web.Application, spacy_model: str) -> None:
    """Load spaCy models eagerly.

    This avoids cross-thread mutation of app state (the extract handler runs in a worker thread).
    """

    app[SPACY_NLP_KEY] = load_spacy_model(spacy_model, enable_readability=True)
    app[SPACY_NLP_FAST_KEY] = load_spacy_model(spacy_model, enable_readability=False)


def get_spacy_models(app: web.Application) -> tuple[Any, Any]:
    return app[SPACY_NLP_KEY], app[SPACY_NLP_FAST_KEY]
