"""spaCy model loading for the Hemma offload server.

This module loads shared spaCy `Language` objects into the aiohttp app state so
request handlers can reuse them without repeated model loads. It delegates the
actual model loading/tuning to `scripts.ml_training.essay_scoring.features.spacy_pipeline`.
"""

from __future__ import annotations

from contextlib import contextmanager
from queue import Queue
from typing import Any

from aiohttp import web

from scripts.ml_training.essay_scoring.features.spacy_pipeline import load_spacy_model
from scripts.ml_training.essay_scoring.offload.http_state import (
    SPACY_NLP_FAST_KEY,
    SPACY_NLP_KEY,
    SPACY_POOL_KEY,
)
from scripts.ml_training.essay_scoring.offload.settings import settings


def load_spacy_models(*, app: web.Application, spacy_model: str) -> None:
    """Load spaCy models eagerly.

    This avoids cross-thread mutation of app state (the extract handler runs in a worker thread).
    """

    disable_components = ["ner", "lemmatizer", "attribute_ruler"]
    pool_size = max(1, int(settings.OFFLOAD_HTTP_MAX_WORKERS))

    # Keep a single set available for health checks / debugging (no pool acquisition).
    app[SPACY_NLP_KEY] = load_spacy_model(
        spacy_model,
        enable_readability=True,
        disable_components=disable_components,
    )
    app[SPACY_NLP_FAST_KEY] = load_spacy_model(
        spacy_model,
        enable_readability=False,
        disable_components=disable_components,
    )

    # spaCy Language objects are not safe to use concurrently across threads. When the offload
    # server is configured with multiple worker threads, use a pool of independent Language
    # instances to avoid contention and internal state corruption.
    pool: Queue[tuple[Any, Any]] = Queue(maxsize=pool_size)
    for _ in range(pool_size):
        pool.put(
            (
                load_spacy_model(
                    spacy_model,
                    enable_readability=True,
                    disable_components=disable_components,
                ),
                load_spacy_model(
                    spacy_model,
                    enable_readability=False,
                    disable_components=disable_components,
                ),
            )
        )
    app[SPACY_POOL_KEY] = pool


def get_spacy_models(app: web.Application) -> tuple[Any, Any]:
    return app[SPACY_NLP_KEY], app[SPACY_NLP_FAST_KEY]


@contextmanager
def acquire_spacy_models(app: web.Application) -> Any:
    """Acquire a dedicated (nlp, nlp_fast) pair for the current request."""

    pool: Queue[tuple[Any, Any]] = app[SPACY_POOL_KEY]
    pair = pool.get()
    try:
        yield pair
    finally:
        pool.put(pair)
