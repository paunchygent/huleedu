"""Remote combined feature extraction client (Hemma via tunnel) with disk caching."""

from __future__ import annotations

import hashlib
import io
import json
import logging
import socket
import time
import urllib.error
import urllib.request
import uuid
import zipfile
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np

from scripts.ml_training.essay_scoring.config import EmbeddingConfig, FeatureSet, OffloadConfig
from scripts.ml_training.essay_scoring.features.schema import (
    build_feature_schema,
    feature_names_for,
)
from scripts.ml_training.essay_scoring.logging_utils import ProgressWriter
from scripts.ml_training.essay_scoring.offload.extract_models import ExtractMeta
from scripts.ml_training.essay_scoring.offload.metrics import OffloadMetricsCollector

_MAX_EXTRACT_ITEMS = 64
_MAX_EXTRACT_REQUEST_BYTES = 900_000
_PROGRESS_LOG_EVERY_S = 15.0

logger = logging.getLogger(__name__)

_TIER1_SCHEMA_ALIASES: dict[str, str] = {
    "grammar_density": "grammar_errors_per_100_words",
    "spelling_density": "spelling_errors_per_100_words",
    "punctuation_density": "punctuation_errors_per_100_words",
}


@dataclass(frozen=True)
class RemoteExtractResult:
    embeddings: np.ndarray | None
    handcrafted: np.ndarray | None
    meta: ExtractMeta


@dataclass(frozen=True)
class RemoteExtractClient:
    """Client for `POST /v1/extract` returning a zip bundle."""

    base_url: str
    embedding_config: EmbeddingConfig
    offload_config: OffloadConfig
    metrics: OffloadMetricsCollector | None = None
    progress: ProgressWriter | None = None

    def extract(
        self, texts: list[str], prompts: list[str], feature_set: FeatureSet
    ) -> RemoteExtractResult:
        extract_start = time.monotonic()
        if not texts:
            empty = np.empty((0, 0), dtype=np.float32)
            meta = self._load_expected_meta_or_fail()
            return RemoteExtractResult(
                embeddings=empty
                if feature_set in {FeatureSet.EMBEDDINGS, FeatureSet.COMBINED}
                else None,
                handcrafted=empty
                if feature_set in {FeatureSet.HANDCRAFTED, FeatureSet.COMBINED}
                else None,
                meta=meta,
            )

        if len(texts) != len(prompts):
            raise ValueError(
                "texts and prompts must have the same length "
                f"texts={len(texts)} prompts={len(prompts)}"
            )

        expected_meta = self._load_expected_meta_or_none()
        expected_fingerprint = expected_meta.server_fingerprint if expected_meta else None
        expected_schema_version = expected_meta.schema_version if expected_meta else None

        need_embeddings = feature_set in {FeatureSet.EMBEDDINGS, FeatureSet.COMBINED}
        need_handcrafted = feature_set in {FeatureSet.HANDCRAFTED, FeatureSet.COMBINED}

        embedding_cache_dir = self.offload_config.embedding_cache_dir
        embedding_cache_dir.mkdir(parents=True, exist_ok=True)

        handcrafted_cache_root = self.offload_config.handcrafted_cache_dir
        handcrafted_cache_root.mkdir(parents=True, exist_ok=True)

        logger.info(
            "Hemma extract start (feature_set=%s, records=%d, need_embeddings=%s, "
            "need_handcrafted=%s)",
            feature_set.value,
            len(texts),
            need_embeddings,
            need_handcrafted,
        )

        cached_embeddings: dict[int, np.ndarray] = {}
        cached_handcrafted: dict[int, np.ndarray] = {}
        missing_indices: list[int] = []
        missing_texts: list[str] = []
        missing_prompts: list[str] = []
        cache_hits_embedding = 0
        cache_misses_embedding = 0
        cache_hits_extract = 0
        cache_misses_extract = 0

        cache_scan_start = time.monotonic()

        for index, (text, prompt) in enumerate(zip(texts, prompts, strict=True)):
            embedding_ok = True
            handcrafted_ok = True

            if need_embeddings:
                emb_path = embedding_cache_dir / f"{self._embedding_cache_key(text)}.npy"
                if emb_path.exists():
                    try:
                        cached_embeddings[index] = np.load(emb_path)
                    except (OSError, ValueError):
                        embedding_ok = False
                        if self.metrics is not None:
                            self.metrics.record_cache_read_error(kind="embedding")
                            self.metrics.record_cache_miss(kind="embedding")
                        cache_misses_embedding += 1
                    else:
                        if self.metrics is not None:
                            self.metrics.record_cache_hit(kind="embedding")
                        cache_hits_embedding += 1
                else:
                    embedding_ok = False
                    if self.metrics is not None:
                        self.metrics.record_cache_miss(kind="embedding")
                    cache_misses_embedding += 1

            if need_handcrafted:
                if expected_fingerprint is None or expected_schema_version is None:
                    handcrafted_ok = False
                    if self.metrics is not None:
                        self.metrics.record_cache_miss(kind="extract")
                    cache_misses_extract += 1
                else:
                    hand_path = self._handcrafted_cache_path(
                        cache_root=handcrafted_cache_root,
                        server_fingerprint=expected_fingerprint,
                        schema_version=expected_schema_version,
                        text=text,
                        prompt=prompt,
                    )
                    if hand_path.exists():
                        try:
                            cached_handcrafted[index] = np.load(hand_path)
                        except (OSError, ValueError):
                            handcrafted_ok = False
                            if self.metrics is not None:
                                self.metrics.record_cache_read_error(kind="extract")
                                self.metrics.record_cache_miss(kind="extract")
                            cache_misses_extract += 1
                        else:
                            if self.metrics is not None:
                                self.metrics.record_cache_hit(kind="extract")
                            cache_hits_extract += 1
                    else:
                        handcrafted_ok = False
                        if self.metrics is not None:
                            self.metrics.record_cache_miss(kind="extract")
                        cache_misses_extract += 1

            if not embedding_ok or not handcrafted_ok:
                missing_indices.append(index)
                missing_texts.append(text)
                missing_prompts.append(prompt)

        cache_scan_elapsed = time.monotonic() - cache_scan_start
        ready_from_cache = len(texts) - len(missing_texts)
        logger.info(
            "Hemma extract cache scan complete (ready=%d/%d, missing=%d) in %.2fs "
            "(cache_hits: embedding=%d extract=%d; cache_misses: embedding=%d extract=%d)",
            ready_from_cache,
            len(texts),
            len(missing_texts),
            cache_scan_elapsed,
            cache_hits_embedding,
            cache_hits_extract,
            cache_misses_embedding,
            cache_misses_extract,
        )
        if self.progress is not None:
            self.progress.update(
                substage="offload.extract.cache_scan",
                processed=len(texts),
                total=len(texts),
                unit="records",
                details={
                    "ready_from_cache": int(ready_from_cache),
                    "missing": int(len(missing_texts)),
                    "cache_hits_embedding": int(cache_hits_embedding),
                    "cache_hits_extract": int(cache_hits_extract),
                    "cache_misses_embedding": int(cache_misses_embedding),
                    "cache_misses_extract": int(cache_misses_extract),
                    "elapsed_s": round(cache_scan_elapsed, 2),
                },
                force=True,
            )

        fetched_meta: ExtractMeta | None = None
        if missing_texts:
            logger.info(
                "Hemma extract fetching missing records from offload (missing=%d, "
                "max_batch_items=%d)",
                len(missing_texts),
                _MAX_EXTRACT_ITEMS,
            )
            fetched_embeddings, fetched_handcrafted, fetched_meta = self._fetch_batched(
                missing_texts,
                missing_prompts,
                feature_set,
                total_records=len(texts),
                ready_from_cache=ready_from_cache,
            )
            if fetched_meta is None:
                raise RuntimeError("Offload extract response missing meta.")

            if need_embeddings:
                if fetched_embeddings is None:
                    raise RuntimeError("Offload extract response missing embeddings.npy")
                if fetched_embeddings.shape[0] != len(missing_texts):
                    raise RuntimeError(
                        "Offload extract returned unexpected embedding row count "
                        f"expected={len(missing_texts)} got={fetched_embeddings.shape[0]}"
                    )
                for offset, original_index in enumerate(missing_indices):
                    row = fetched_embeddings[offset].astype(np.float32, copy=False)
                    emb_path = (
                        embedding_cache_dir
                        / f"{self._embedding_cache_key(texts[original_index])}.npy"
                    )
                    np.save(emb_path, row, allow_pickle=False)
                    cached_embeddings[original_index] = row
                    if self.metrics is not None:
                        self.metrics.record_cache_write(kind="embedding")

            if need_handcrafted:
                if fetched_handcrafted is None:
                    raise RuntimeError("Offload extract response missing handcrafted.npy")
                if fetched_handcrafted.shape[0] != len(missing_texts):
                    raise RuntimeError(
                        "Offload extract returned unexpected handcrafted row count "
                        f"expected={len(missing_texts)} got={fetched_handcrafted.shape[0]}"
                    )
                cache_dir = handcrafted_cache_root / fetched_meta.server_fingerprint
                cache_dir.mkdir(parents=True, exist_ok=True)
                for offset, original_index in enumerate(missing_indices):
                    row = fetched_handcrafted[offset].astype(np.float32, copy=False)
                    hand_path = self._handcrafted_cache_path(
                        cache_root=handcrafted_cache_root,
                        server_fingerprint=fetched_meta.server_fingerprint,
                        schema_version=fetched_meta.schema_version,
                        text=texts[original_index],
                        prompt=prompts[original_index],
                    )
                    hand_path.parent.mkdir(parents=True, exist_ok=True)
                    np.save(hand_path, row, allow_pickle=False)
                    cached_handcrafted[original_index] = row
                    if self.metrics is not None:
                        self.metrics.record_cache_write(kind="extract")

                self._persist_expected_meta(fetched_meta)

        meta = fetched_meta or expected_meta
        if meta is None:
            raise RuntimeError(
                "No cached meta.json found for Hemma backend. "
                "Run once with a reachable offload service to bootstrap the cache."
            )

        self._validate_meta_against_local_schema(meta)

        embeddings = None
        handcrafted = None

        if need_embeddings:
            dim = self._embedding_dim(cached_embeddings)
            embeddings = np.zeros((len(texts), dim), dtype=np.float32)
            for idx in range(len(texts)):
                embeddings[idx] = cached_embeddings[idx]

        if need_handcrafted:
            h = self._handcrafted_dim(meta)
            handcrafted = np.zeros((len(texts), h), dtype=np.float32)
            for idx in range(len(texts)):
                handcrafted[idx] = cached_handcrafted[idx]

        logger.info(
            "Hemma extract complete (feature_set=%s, records=%d, fetched=%d, cache_ready=%d) "
            "in %.2fs",
            feature_set.value,
            len(texts),
            len(missing_texts),
            ready_from_cache,
            time.monotonic() - extract_start,
        )

        return RemoteExtractResult(embeddings=embeddings, handcrafted=handcrafted, meta=meta)

    def _fetch_batched(
        self,
        texts: list[str],
        prompts: list[str],
        feature_set: FeatureSet,
        *,
        total_records: int,
        ready_from_cache: int,
    ) -> tuple[np.ndarray | None, np.ndarray | None, ExtractMeta | None]:
        all_embeddings: list[np.ndarray] = []
        all_handcrafted: list[np.ndarray] = []
        meta: ExtractMeta | None = None

        max_in_flight = max(1, int(self.offload_config.extract_max_in_flight_requests))

        fetch_start = time.monotonic()
        last_progress_log = fetch_start
        fetched_items = 0
        batch_count = 0

        chunk_iter = iter(self._iter_extract_chunks(texts, prompts))

        def _submit(
            pool: ThreadPoolExecutor, *, chunk_index: int
        ) -> tuple[Future[tuple[np.ndarray | None, np.ndarray | None, ExtractMeta | None]], int]:
            chunk_texts, chunk_prompts = next(chunk_iter)
            fut = pool.submit(self._fetch_once, chunk_texts, chunk_prompts, feature_set)
            return fut, len(chunk_texts)

        if max_in_flight == 1:
            for chunk_texts, chunk_prompts in self._iter_extract_chunks(texts, prompts):
                batch_count += 1
                chunk_start = time.monotonic()
                chunk_embeddings, chunk_handcrafted, chunk_meta = self._fetch_once(
                    chunk_texts, chunk_prompts, feature_set
                )
                chunk_elapsed = time.monotonic() - chunk_start
                if chunk_meta is None:
                    raise RuntimeError("Offload extract response missing meta.json")
                if meta is None:
                    meta = chunk_meta
                elif meta.server_fingerprint != chunk_meta.server_fingerprint:
                    raise RuntimeError(
                        "Offload server fingerprint changed within a single client fetch "
                        f"first={meta.server_fingerprint} next={chunk_meta.server_fingerprint}"
                    )

                if chunk_embeddings is not None:
                    all_embeddings.append(chunk_embeddings)
                if chunk_handcrafted is not None:
                    all_handcrafted.append(chunk_handcrafted)

                fetched_items += len(chunk_texts)
                ready_total = ready_from_cache + fetched_items
                now = time.monotonic()
                if now - last_progress_log >= _PROGRESS_LOG_EVERY_S or ready_total >= total_records:
                    elapsed = now - fetch_start
                    rate = fetched_items / elapsed if elapsed > 0 else 0.0
                    remaining = total_records - ready_total
                    eta = remaining / rate if rate > 0 else 0.0
                    logger.info(
                        "Hemma extract progress (ready=%d/%d, fetched=%d/%d, batches=%d, "
                        "last_batch=%d in %.2fs, %.2f items/s, ETA %.1fs)",
                        ready_total,
                        total_records,
                        fetched_items,
                        len(texts),
                        batch_count,
                        len(chunk_texts),
                        chunk_elapsed,
                        rate,
                        eta,
                    )
                    if self.progress is not None:
                        self.progress.update(
                            substage="offload.extract.fetch_missing",
                            processed=ready_total,
                            total=total_records,
                            unit="records",
                            details={
                                "ready_from_cache": int(ready_from_cache),
                                "fetched": int(fetched_items),
                                "missing_total": int(len(texts)),
                                "batches": int(batch_count),
                                "last_batch_items": int(len(chunk_texts)),
                                "last_batch_elapsed_s": round(chunk_elapsed, 2),
                            },
                        )
                    last_progress_log = now
        else:
            logger.info("Hemma extract using in-flight concurrency=%d", max_in_flight)

            in_flight: dict[
                Future[tuple[np.ndarray | None, np.ndarray | None, ExtractMeta | None]],
                tuple[int, int, float],
            ] = {}
            pending_by_index: dict[
                int, tuple[int, float, np.ndarray | None, np.ndarray | None, ExtractMeta | None]
            ] = {}

            next_chunk_index = 0
            next_to_flush = 0

            with ThreadPoolExecutor(max_workers=max_in_flight) as pool:
                while len(in_flight) < max_in_flight:
                    try:
                        fut, n_items = _submit(pool, chunk_index=next_chunk_index)
                    except StopIteration:
                        break
                    in_flight[fut] = (next_chunk_index, n_items, time.monotonic())
                    next_chunk_index += 1
                    batch_count += 1

                while in_flight:
                    done, _ = wait(in_flight.keys(), return_when=FIRST_COMPLETED)
                    for fut in done:
                        chunk_index, n_items, submitted_at = in_flight.pop(fut)
                        chunk_embeddings, chunk_handcrafted, chunk_meta = fut.result()
                        pending_by_index[chunk_index] = (
                            n_items,
                            time.monotonic() - submitted_at,
                            chunk_embeddings,
                            chunk_handcrafted,
                            chunk_meta,
                        )

                        try:
                            next_fut, next_n = _submit(pool, chunk_index=next_chunk_index)
                        except StopIteration:
                            pass
                        else:
                            in_flight[next_fut] = (next_chunk_index, next_n, time.monotonic())
                            next_chunk_index += 1
                            batch_count += 1

                    while next_to_flush in pending_by_index:
                        n_items, chunk_elapsed, chunk_embeddings, chunk_handcrafted, chunk_meta = (
                            pending_by_index.pop(next_to_flush)
                        )
                        if chunk_meta is None:
                            raise RuntimeError("Offload extract response missing meta.json")
                        if meta is None:
                            meta = chunk_meta
                        elif meta.server_fingerprint != chunk_meta.server_fingerprint:
                            raise RuntimeError(
                                "Offload server fingerprint changed within a single client fetch "
                                f"first={meta.server_fingerprint} "
                                f"next={chunk_meta.server_fingerprint}"
                            )

                        if chunk_embeddings is not None:
                            all_embeddings.append(chunk_embeddings)
                        if chunk_handcrafted is not None:
                            all_handcrafted.append(chunk_handcrafted)

                        fetched_items += n_items
                        ready_total = ready_from_cache + fetched_items
                        now = time.monotonic()
                        if (
                            now - last_progress_log >= _PROGRESS_LOG_EVERY_S
                            or ready_total >= total_records
                        ):
                            elapsed = now - fetch_start
                            rate = fetched_items / elapsed if elapsed > 0 else 0.0
                            remaining = total_records - ready_total
                            eta = remaining / rate if rate > 0 else 0.0
                            logger.info(
                                "Hemma extract progress (ready=%d/%d, fetched=%d/%d, batches=%d, "
                                "last_batch=%d in %.2fs, %.2f items/s, ETA %.1fs)",
                                ready_total,
                                total_records,
                                fetched_items,
                                len(texts),
                                batch_count,
                                n_items,
                                chunk_elapsed,
                                rate,
                                eta,
                            )
                            if self.progress is not None:
                                self.progress.update(
                                    substage="offload.extract.fetch_missing",
                                    processed=ready_total,
                                    total=total_records,
                                    unit="records",
                                    details={
                                        "ready_from_cache": int(ready_from_cache),
                                        "fetched": int(fetched_items),
                                        "missing_total": int(len(texts)),
                                        "batches": int(batch_count),
                                        "last_batch_items": int(n_items),
                                        "last_batch_elapsed_s": round(chunk_elapsed, 2),
                                    },
                                )
                            last_progress_log = now

                        next_to_flush += 1

        embeddings = None
        if all_embeddings:
            embeddings = np.vstack(all_embeddings).astype(np.float32, copy=False)
        handcrafted = None
        if all_handcrafted:
            handcrafted = np.vstack(all_handcrafted).astype(np.float32, copy=False)
        return embeddings, handcrafted, meta

    def _iter_extract_chunks(
        self, texts: list[str], prompts: list[str]
    ) -> Iterable[tuple[list[str], list[str]]]:
        if not texts:
            return
        if len(texts) != len(prompts):
            raise ValueError("texts and prompts must have the same length.")

        base_payload = {
            "texts": [],
            "prompts": [],
            "feature_set": "combined",
        }
        base_bytes = len(
            json.dumps(base_payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        )

        chunk_texts: list[str] = []
        chunk_prompts: list[str] = []
        chunk_interior_bytes = 0

        for text, prompt in zip(texts, prompts, strict=True):
            text_bytes = len(
                json.dumps(text, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
            )
            prompt_bytes = len(
                json.dumps(prompt, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
            )

            item_bytes = text_bytes + prompt_bytes + 2  # two commas/array separators (approx)
            if base_bytes + item_bytes > _MAX_EXTRACT_REQUEST_BYTES:
                raise RuntimeError(
                    "Single item too large for extract offload request "
                    f"bytes={base_bytes + item_bytes} limit={_MAX_EXTRACT_REQUEST_BYTES}"
                )

            candidate_bytes = chunk_interior_bytes + item_bytes
            candidate_items = len(chunk_texts) + 1

            if (
                candidate_items > _MAX_EXTRACT_ITEMS
                or base_bytes + candidate_bytes > _MAX_EXTRACT_REQUEST_BYTES
            ) and chunk_texts:
                yield chunk_texts, chunk_prompts
                chunk_texts = [text]
                chunk_prompts = [prompt]
                chunk_interior_bytes = item_bytes
                continue

            chunk_texts.append(text)
            chunk_prompts.append(prompt)
            chunk_interior_bytes = candidate_bytes

        if chunk_texts:
            yield chunk_texts, chunk_prompts

    def _fetch_once(
        self, texts: list[str], prompts: list[str], feature_set: FeatureSet
    ) -> tuple[np.ndarray | None, np.ndarray | None, ExtractMeta | None]:
        url = self.base_url.rstrip("/") + "/v1/extract"
        correlation_id = str(uuid.uuid4())
        payload = {
            "texts": texts,
            "prompts": prompts,
            "feature_set": feature_set.value,
        }
        data = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "X-Correlation-ID": correlation_id,
            },
            method="POST",
        )

        start = time.monotonic()
        try:
            with urllib.request.urlopen(
                request, timeout=self.offload_config.request_timeout_s
            ) as resp:
                status = getattr(resp, "status", 200)
                body = resp.read()
        except urllib.error.HTTPError as exc:
            elapsed = time.monotonic() - start
            if self.metrics is not None:
                self.metrics.record_request_error(
                    kind="extract", duration_s=elapsed, error_kind="http_error"
                )
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                "Extract offload HTTP error "
                f"correlation_id={correlation_id} status={exc.code} body={detail}"
            ) from exc
        except urllib.error.URLError as exc:
            elapsed = time.monotonic() - start
            is_timeout = isinstance(exc.reason, (TimeoutError, socket.timeout))
            if self.metrics is not None:
                self.metrics.record_request_error(
                    kind="extract",
                    duration_s=elapsed,
                    error_kind="timeout" if is_timeout else "connection_error",
                )
            raise RuntimeError(
                f"Extract offload connection error correlation_id={correlation_id}: {exc}"
            ) from exc
        except socket.timeout as exc:
            elapsed = time.monotonic() - start
            if self.metrics is not None:
                self.metrics.record_request_error(
                    kind="extract", duration_s=elapsed, error_kind="timeout"
                )
            raise RuntimeError(
                f"Extract offload timeout correlation_id={correlation_id}: {exc}"
            ) from exc

        if status != 200:
            elapsed = time.monotonic() - start
            if self.metrics is not None:
                self.metrics.record_request_error(
                    kind="extract", duration_s=elapsed, error_kind="http_error"
                )
            raise RuntimeError(
                "Extract offload returned non-200 response "
                f"status={status} correlation_id={correlation_id} bytes={len(body)}"
            )

        elapsed = time.monotonic() - start
        if self.metrics is not None:
            self.metrics.record_request_ok(
                kind="extract",
                duration_s=elapsed,
                request_bytes=len(data),
                response_bytes=len(body),
                texts_in_request=len(texts),
            )

        return self._decode_zip_bundle(body)

    def _decode_zip_bundle(
        self, body: bytes
    ) -> tuple[np.ndarray | None, np.ndarray | None, ExtractMeta | None]:
        with zipfile.ZipFile(io.BytesIO(body), "r") as zf:
            meta_bytes = zf.read("meta.json")
            meta = ExtractMeta.model_validate_json(meta_bytes.decode("utf-8"))

            embeddings = None
            handcrafted = None

            if "embeddings.npy" in zf.namelist():
                embeddings = np.load(io.BytesIO(zf.read("embeddings.npy"))).astype(
                    np.float32, copy=False
                )
            if "handcrafted.npy" in zf.namelist():
                handcrafted = np.load(io.BytesIO(zf.read("handcrafted.npy"))).astype(
                    np.float32, copy=False
                )

            return embeddings, handcrafted, meta

    def _embedding_cache_key(self, text: str) -> str:
        hasher = hashlib.sha256()
        hasher.update(self.embedding_config.model_name.encode("utf-8"))
        hasher.update(b"|")
        hasher.update(str(self.embedding_config.max_length).encode("utf-8"))
        hasher.update(b"|")
        hasher.update(b"cls|")
        hasher.update(text.encode("utf-8"))
        return hasher.hexdigest()

    @staticmethod
    def _handcrafted_cache_path(
        *,
        cache_root: Path,
        server_fingerprint: str,
        schema_version: int,
        text: str,
        prompt: str,
    ) -> Path:
        hasher = hashlib.sha256()
        hasher.update(str(schema_version).encode("utf-8"))
        hasher.update(b"|")
        hasher.update(text.encode("utf-8"))
        hasher.update(b"|")
        hasher.update(prompt.encode("utf-8"))
        digest = hasher.hexdigest()
        return cache_root / server_fingerprint / f"{digest}.npy"

    def _expected_meta_path(self) -> Path:
        return self.offload_config.handcrafted_cache_dir / "current_meta.json"

    def _load_expected_meta_or_none(self) -> ExtractMeta | None:
        path = self._expected_meta_path()
        if not path.exists():
            return None
        try:
            return ExtractMeta.model_validate_json(path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def _load_expected_meta_or_fail(self) -> ExtractMeta:
        meta = self._load_expected_meta_or_none()
        if meta is None:
            raise RuntimeError("Expected meta.json not found; cannot produce empty extract result.")
        return meta

    def _persist_expected_meta(self, meta: ExtractMeta) -> None:
        path = self._expected_meta_path()
        path.write_text(meta.model_dump_json(indent=2), encoding="utf-8")

    @staticmethod
    def _embedding_dim(cached_rows: dict[int, np.ndarray]) -> int:
        if not cached_rows:
            return 0
        first = next(iter(cached_rows.values()))
        return int(first.shape[0])

    @staticmethod
    def _handcrafted_dim(meta: ExtractMeta) -> int:
        return (
            len(meta.feature_schema.tier1)
            + len(meta.feature_schema.tier2)
            + len(meta.feature_schema.tier3)
        )

    @staticmethod
    def _normalize_schema_names(names: list[str]) -> list[str]:
        return [_TIER1_SCHEMA_ALIASES.get(name, name) for name in names]

    def _validate_meta_against_local_schema(self, meta: ExtractMeta) -> None:
        local_schema = build_feature_schema(meta.embedding.dim)
        meta_tier1 = self._normalize_schema_names(list(meta.feature_schema.tier1))
        local_tier1 = list(local_schema.tier1)
        if meta_tier1 != local_tier1:
            raise RuntimeError("Offload tier1 feature schema mismatch.")
        if list(meta.feature_schema.tier2) != list(local_schema.tier2):
            raise RuntimeError("Offload tier2 feature schema mismatch.")
        if list(meta.feature_schema.tier3) != list(local_schema.tier3):
            raise RuntimeError("Offload tier3 feature schema mismatch.")
        meta_combined = self._normalize_schema_names(list(meta.feature_schema.combined))
        local_combined = list(local_schema.combined)
        if meta_combined != local_combined:
            raise RuntimeError("Offload combined feature schema mismatch.")

        # Also validate we can map to the local training feature ordering helpers.
        combined_names = feature_names_for(FeatureSet.COMBINED, meta.embedding.dim)
        if combined_names != local_combined:
            raise RuntimeError("Local feature_names_for(COMBINED) does not match schema.")
