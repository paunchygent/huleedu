"""Command modules for the essay-scoring CLI.

Purpose:
    Provide SRP-oriented command registration modules so the root CLI file
    stays a thin orchestration entrypoint.

Relationships:
    - Imported by `scripts.ml_training.essay_scoring.cli`.
    - Each module exposes `register(app)` and owns one bounded command area.
"""
