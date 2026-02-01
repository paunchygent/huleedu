"""Embedding extraction for essay scoring using DeBERTa-v3-base."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import torch
from transformers import AutoModel, AutoTokenizer

from scripts.ml_training.essay_scoring.config import EmbeddingConfig


@dataclass
class DebertaEmbedder:
    """DeBERTa-v3-base embedding extractor with [CLS] pooling."""

    config: EmbeddingConfig

    def __post_init__(self) -> None:
        self._device = self._resolve_device(self.config.device)
        self._tokenizer = AutoTokenizer.from_pretrained(self.config.model_name)
        self._model = AutoModel.from_pretrained(self.config.model_name)
        self._model.to(self._device)
        self._model.eval()

    def embed(self, texts: list[str]) -> np.ndarray:
        """Embed texts using [CLS] pooling from the last hidden state."""

        if not texts:
            return np.empty((0, 0), dtype=float)

        batches = [
            texts[idx : idx + self.config.batch_size]
            for idx in range(0, len(texts), self.config.batch_size)
        ]
        embeddings: list[np.ndarray] = []

        for batch in batches:
            encoded = self._tokenizer(
                batch,
                padding=True,
                truncation=True,
                max_length=self.config.max_length,
                return_tensors="pt",
            )
            encoded = {key: value.to(self._device) for key, value in encoded.items()}
            with torch.no_grad():
                outputs = self._model(**encoded)
            cls_embeddings = outputs.last_hidden_state[:, 0, :].detach().cpu().numpy()
            embeddings.append(cls_embeddings)

        return np.vstack(embeddings)

    @staticmethod
    def _resolve_device(device_override: str | None) -> torch.device:
        """Resolve the torch device for embeddings."""

        if device_override:
            return torch.device(device_override)
        if torch.cuda.is_available():
            return torch.device("cuda")
        if torch.backends.mps.is_available():
            return torch.device("mps")
        return torch.device("cpu")
