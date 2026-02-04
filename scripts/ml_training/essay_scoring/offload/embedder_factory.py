"""Factory for building the offload embedding extractor."""

from __future__ import annotations

from scripts.ml_training.essay_scoring.config import EmbeddingConfig
from scripts.ml_training.essay_scoring.features.embeddings import DebertaEmbedder
from scripts.ml_training.essay_scoring.offload.settings import settings


def build_embedder() -> DebertaEmbedder:
    return DebertaEmbedder(
        EmbeddingConfig(
            model_name=settings.OFFLOAD_EMBEDDING_MODEL_NAME,
            max_length=settings.OFFLOAD_EMBEDDING_MAX_LENGTH,
            batch_size=settings.OFFLOAD_EMBEDDING_BATCH_SIZE,
            device=settings.OFFLOAD_TORCH_DEVICE,
        )
    )
