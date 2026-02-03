from __future__ import annotations

import spacy

import scripts.ml_training.essay_scoring.features.spacy_pipeline as spacy_pipeline_module
from scripts.ml_training.essay_scoring.features.spacy_pipeline import (
    ensure_textdescriptives_readability,
    load_spacy_model,
)


def test_ensure_textdescriptives_readability_is_idempotent() -> None:
    nlp = spacy.blank("en")
    assert "textdescriptives/readability" not in nlp.pipe_names

    ensure_textdescriptives_readability(nlp)
    assert "textdescriptives/readability" in nlp.pipe_names

    ensure_textdescriptives_readability(nlp)
    assert nlp.pipe_names.count("textdescriptives/readability") == 1


def test_load_spacy_model_calls_spacy_load_and_optionally_enables_readability(monkeypatch) -> None:
    def _fake_load(_name: str):  # noqa: ANN001
        return spacy.blank("en")

    monkeypatch.setattr(spacy_pipeline_module.spacy, "load", _fake_load)

    nlp = load_spacy_model("fake", enable_readability=True)
    assert "textdescriptives/readability" in nlp.pipe_names

    nlp2 = load_spacy_model("fake", enable_readability=False)
    assert "textdescriptives/readability" not in nlp2.pipe_names
