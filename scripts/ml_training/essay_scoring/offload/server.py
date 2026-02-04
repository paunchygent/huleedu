"""Hemma embedding offload HTTP server (research-scoped).

This module remains as the stable entrypoint (`python -m ...offload.server`) and
re-exports the aiohttp app wiring from `http_app.py`.
"""

from __future__ import annotations

from scripts.ml_training.essay_scoring.offload.http_app import create_app, main

__all__ = ["create_app", "main"]


if __name__ == "__main__":
    main()
