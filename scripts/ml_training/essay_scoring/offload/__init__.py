"""Hemma offload helpers for the essay scoring research pipeline.

This package is intentionally scoped to research tooling (under `scripts/`) so we can:
- depend on heavy ML libraries (torch/transformers/spaCy) without impacting `typecheck-all`
- run as a standalone HTTP service on Hemma (Docker) behind an SSH tunnel
"""
