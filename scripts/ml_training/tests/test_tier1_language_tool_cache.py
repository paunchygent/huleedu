from __future__ import annotations

import threading
import time
from typing import Any

import scripts.ml_training.essay_scoring.features.tier1_error_readability as tier1_module
from scripts.ml_training.essay_scoring.features.tier1_error_readability import (
    Tier1FeatureExtractor,
)


def test_tier1_language_tool_cache_and_concurrency(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(tier1_module, "ensure_textdescriptives_readability", lambda _nlp: None)

    extractor = Tier1FeatureExtractor(
        nlp=object(),
        language_tool_url="http://127.0.0.1:18085",
        request_timeout_s=1.0,
        language_tool_cache_dir=tmp_path,
        language_tool_max_concurrency=3,
    )

    monkeypatch.setattr(
        extractor,
        "_compute_text_stats",
        lambda _cleaned: {
            "word_count": 100.0,
            "avg_sentence_length": 10.0,
            "ttr": 0.5,
            "avg_word_length": 4.0,
            "flesch_kincaid": 5.0,
            "smog": 8.0,
            "coleman_liau": 9.0,
            "ari": 7.0,
        },
    )

    lock = threading.Lock()
    active = 0
    max_active = 0
    calls: list[str] = []

    def _fake_fetch_remote(*, text: str, request_options: dict[str, Any]) -> dict[str, Any]:  # noqa: ARG001
        nonlocal active, max_active
        with lock:
            active += 1
            max_active = max(max_active, active)
            calls.append(text)
        time.sleep(0.05)
        with lock:
            active -= 1
        return {
            "errors": [
                {"category_id": "PUNCTUATION", "rule_id": "PUNCT_RULE"},
                {"category_id": "SPELLING", "rule_id": "SPELL_RULE"},
                {"category_id": "GRAMMAR", "rule_id": "GRAMMAR_RULE"},
            ]
        }

    monkeypatch.setattr(extractor, "_fetch_remote_language_tool_response", _fake_fetch_remote)

    texts = ["a", "bb", "ccc", "dddd", "eeeee", "ffffff"]
    first = extractor.extract_batch(texts)
    assert len(first) == len(texts)
    assert max_active > 1
    assert max_active <= 3
    assert len(calls) == len(texts)

    second = extractor.extract_batch(texts)
    assert len(second) == len(texts)
    assert len(calls) == len(texts)
