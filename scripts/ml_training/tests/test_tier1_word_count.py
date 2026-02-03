from __future__ import annotations

from dataclasses import dataclass

from scripts.ml_training.essay_scoring.features.tier1_error_readability import Tier1FeatureExtractor


@dataclass(frozen=True)
class _FakeToken:
    text: str
    is_space: bool = False
    is_punct: bool = False


@dataclass(frozen=True)
class _FakeUnderscore:
    readability: dict[str, float]


class _FakeDoc:
    def __init__(self, tokens: list[_FakeToken], *, sentence_count: int) -> None:
        self._tokens = tokens
        self.sents = [object() for _ in range(sentence_count)]
        self._ = _FakeUnderscore(
            readability={
                "flesch_kincaid_grade": 7.0,
                "smog": 9.0,
                "coleman_liau_index": 8.0,
                "automated_readability_index": 6.0,
            }
        )

    def __iter__(self):
        return iter(self._tokens)


def test_tier1_word_count_excludes_punctuation_tokens() -> None:
    doc = _FakeDoc(
        tokens=[
            _FakeToken("Hello"),
            _FakeToken(",", is_punct=True),
            _FakeToken("world"),
            _FakeToken("!", is_punct=True),
        ],
        sentence_count=1,
    )
    stats = Tier1FeatureExtractor._compute_text_stats_from_doc(doc)
    assert stats["word_count"] == 2.0
    assert stats["avg_word_length"] == 5.0
    assert stats["avg_sentence_length"] == 2.0
