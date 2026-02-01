"""Remote embedding client (Hemma via tunnel) with disk caching."""

from __future__ import annotations

import hashlib
import io
import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Iterable

import numpy as np

from scripts.ml_training.essay_scoring.config import EmbeddingConfig, OffloadConfig
from scripts.ml_training.essay_scoring.features.protocols import EmbeddingExtractorProtocol

_MAX_EMBEDDING_REQUEST_BYTES = 900_000


@dataclass(frozen=True)
class RemoteEmbeddingClient(EmbeddingExtractorProtocol):
    """Embedding extractor that calls a remote Hemma server.

    Response payload is expected to be a binary `.npy` float32 array.
    """

    base_url: str
    embedding_config: EmbeddingConfig
    offload_config: OffloadConfig

    def embed(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.empty((0, 0), dtype=np.float32)

        cache_dir = self.offload_config.embedding_cache_dir
        cache_dir.mkdir(parents=True, exist_ok=True)

        cached_rows: dict[int, np.ndarray] = {}
        missing_indices: list[int] = []
        missing_texts: list[str] = []

        for index, text in enumerate(texts):
            cache_path = cache_dir / f"{self._cache_key(text)}.npy"
            if cache_path.exists():
                cached_rows[index] = np.load(cache_path)
            else:
                missing_indices.append(index)
                missing_texts.append(text)

        fetched: np.ndarray | None = None
        if missing_texts:
            fetched = self._fetch_embeddings_batched(missing_texts)
            if fetched.shape[0] != len(missing_texts):
                raise RuntimeError(
                    "Offload embedding server returned unexpected row count "
                    f"expected={len(missing_texts)} got={fetched.shape[0]}"
                )
            for offset, original_index in enumerate(missing_indices):
                row = fetched[offset].astype(np.float32, copy=False)
                cache_path = cache_dir / f"{self._cache_key(texts[original_index])}.npy"
                np.save(cache_path, row, allow_pickle=False)
                cached_rows[original_index] = row

        dim = self._embedding_dim(cached_rows, fetched)
        output = np.zeros((len(texts), dim), dtype=np.float32)
        for index in range(len(texts)):
            output[index] = cached_rows[index]
        return output

    def _fetch_embeddings_batched(self, texts: list[str]) -> np.ndarray:
        arrays: list[np.ndarray] = []
        for chunk in self._iter_embedding_chunks(texts):
            arrays.append(self._fetch_embeddings(chunk))

        if not arrays:
            return np.empty((0, 0), dtype=np.float32)

        return np.vstack(arrays).astype(np.float32, copy=False)

    def _iter_embedding_chunks(self, texts: list[str]) -> Iterable[list[str]]:
        if not texts:
            return

        max_payload_bytes = _MAX_EMBEDDING_REQUEST_BYTES

        base_payload = {
            "texts": [],
            "model_name": self.embedding_config.model_name,
            "max_length": self.embedding_config.max_length,
        }
        base_bytes = len(
            json.dumps(base_payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        )

        chunk: list[str] = []
        chunk_interior_bytes = 0

        for text in texts:
            text_bytes = len(
                json.dumps(text, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
            )

            if base_bytes + text_bytes > max_payload_bytes:
                raise RuntimeError(
                    "Single text too large for embedding offload request "
                    f"bytes={base_bytes + text_bytes} limit={max_payload_bytes}"
                )

            candidate_interior_bytes = chunk_interior_bytes
            if chunk:
                candidate_interior_bytes += 1  # comma separator
            candidate_interior_bytes += text_bytes

            if base_bytes + candidate_interior_bytes > max_payload_bytes and chunk:
                yield chunk
                chunk = [text]
                chunk_interior_bytes = text_bytes
                continue

            chunk.append(text)
            chunk_interior_bytes = candidate_interior_bytes

        if chunk:
            yield chunk

    def _fetch_embeddings(self, texts: list[str]) -> np.ndarray:
        url = self.base_url.rstrip("/") + "/v1/embed"
        payload = {
            "texts": texts,
            "model_name": self.embedding_config.model_name,
            "max_length": self.embedding_config.max_length,
        }
        data = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(
                request, timeout=self.offload_config.request_timeout_s
            ) as resp:
                status = getattr(resp, "status", 200)
                body = resp.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"Embedding offload HTTP error status={exc.code} body={detail}"
            ) from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Embedding offload connection error: {exc}") from exc

        if status != 200:
            raise RuntimeError(f"Embedding offload returned status={status} bytes={len(body)}")

        array = np.load(io.BytesIO(body))
        return array.astype(np.float32, copy=False)

    def _cache_key(self, text: str) -> str:
        hasher = hashlib.sha256()
        hasher.update(self.embedding_config.model_name.encode("utf-8"))
        hasher.update(b"|")
        hasher.update(str(self.embedding_config.max_length).encode("utf-8"))
        hasher.update(b"|")
        hasher.update(text.encode("utf-8"))
        return hasher.hexdigest()

    @staticmethod
    def _embedding_dim(cached_rows: dict[int, np.ndarray], fetched: np.ndarray | None) -> int:
        if cached_rows:
            first = next(iter(cached_rows.values()))
            return int(first.shape[0])
        if fetched is not None and fetched.ndim == 2:
            return int(fetched.shape[1])
        return 0
