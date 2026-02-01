"""Whitebox essay scoring research pipeline."""

from __future__ import annotations

import warnings

# Third-party deps (notably SWIG-based extensions like `sentencepiece`) can emit noisy
# DeprecationWarnings on newer Python versions. These warnings are not actionable within
# this repo and obscure research logs, so we filter them narrowly by message.
warnings.filterwarnings(
    "ignore",
    message=r".*builtin type SwigPyPacked has no __module__ attribute.*",
    category=DeprecationWarning,
)
warnings.filterwarnings(
    "ignore",
    message=r".*builtin type SwigPyObject has no __module__ attribute.*",
    category=DeprecationWarning,
)
warnings.filterwarnings(
    "ignore",
    message=r".*builtin type swigvarlink has no __module__ attribute.*",
    category=DeprecationWarning,
)
