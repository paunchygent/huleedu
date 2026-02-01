from __future__ import annotations

import numpy as np

from scripts.ml_training.essay_scoring.features.utils import density_per_100_words
from scripts.ml_training.essay_scoring.training.qwk import clip_bands, round_to_half_band


def test_density_per_100_words() -> None:
    assert density_per_100_words(5, 200) == 2.5
    assert density_per_100_words(0, 100) == 0.0


def test_rounding_and_clipping() -> None:
    predictions = np.array([4.9, 5.1, 7.8])
    rounded = round_to_half_band(predictions)
    clipped = clip_bands(rounded)
    assert np.allclose(rounded, np.array([5.0, 5.0, 8.0]))
    assert np.allclose(clipped, np.array([5.0, 5.0, 7.5]))
