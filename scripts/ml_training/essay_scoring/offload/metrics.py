"""Offload performance metrics for Hemma remote calls.

These metrics are used to tune throughput (essays/sec) vs latency/stability.
They are intentionally lightweight and dependency-free (stdlib only).
"""

from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock


def _percentile(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    if quantile <= 0:
        return float(min(values))
    if quantile >= 1:
        return float(max(values))

    sorted_values = sorted(values)
    position = (len(sorted_values) - 1) * quantile
    lower_index = int(math.floor(position))
    upper_index = int(math.ceil(position))
    if lower_index == upper_index:
        return float(sorted_values[lower_index])
    weight = position - lower_index
    lower = sorted_values[lower_index]
    upper = sorted_values[upper_index]
    return float(lower + (upper - lower) * weight)


@dataclass
class CacheMetrics:
    hits: int = 0
    misses: int = 0
    writes: int = 0
    read_errors: int = 0
    decode_errors: int = 0

    def hit_rate(self) -> float:
        total = self.hits + self.misses
        if total <= 0:
            return 0.0
        return float(self.hits / total)

    def to_dict(self) -> dict[str, object]:
        return {
            "hits": int(self.hits),
            "misses": int(self.misses),
            "writes": int(self.writes),
            "read_errors": int(self.read_errors),
            "decode_errors": int(self.decode_errors),
            "hit_rate": float(self.hit_rate()),
        }


@dataclass
class RequestMetrics:
    durations_s: list[float] = field(default_factory=list)
    request_bytes: list[int] = field(default_factory=list)
    response_bytes: list[int] = field(default_factory=list)
    texts_per_request: list[int] = field(default_factory=list)

    total_requests: int = 0
    ok_requests: int = 0
    error_requests: int = 0
    timeout_requests: int = 0
    http_error_requests: int = 0
    connection_error_requests: int = 0

    def record_ok(
        self,
        *,
        duration_s: float,
        request_bytes: int,
        response_bytes: int,
        texts_in_request: int,
    ) -> None:
        self.total_requests += 1
        self.ok_requests += 1
        self.durations_s.append(float(duration_s))
        self.request_bytes.append(int(request_bytes))
        self.response_bytes.append(int(response_bytes))
        self.texts_per_request.append(int(texts_in_request))

    def record_error(self, *, duration_s: float, kind: str) -> None:
        self.total_requests += 1
        self.error_requests += 1
        self.durations_s.append(float(duration_s))
        if kind == "timeout":
            self.timeout_requests += 1
        elif kind == "http_error":
            self.http_error_requests += 1
        elif kind == "connection_error":
            self.connection_error_requests += 1

    def to_summary_dict(self) -> dict[str, object]:
        durations = list(self.durations_s)
        return {
            "requests_total": int(self.total_requests),
            "requests_ok": int(self.ok_requests),
            "requests_error": int(self.error_requests),
            "requests_timeout": int(self.timeout_requests),
            "requests_http_error": int(self.http_error_requests),
            "requests_connection_error": int(self.connection_error_requests),
            "latency_s": {
                "p50": float(_percentile(durations, 0.50)),
                "p95": float(_percentile(durations, 0.95)),
                "p99": float(_percentile(durations, 0.99)),
                "mean": float(sum(durations) / len(durations)) if durations else 0.0,
            },
            "payload_bytes": {
                "request_mean": float(sum(self.request_bytes) / len(self.request_bytes))
                if self.request_bytes
                else 0.0,
                "response_mean": float(sum(self.response_bytes) / len(self.response_bytes))
                if self.response_bytes
                else 0.0,
            },
            "texts_per_request": {
                "mean": float(sum(self.texts_per_request) / len(self.texts_per_request))
                if self.texts_per_request
                else 0.0,
                "total": int(sum(self.texts_per_request)),
            },
        }


@dataclass
class OffloadMetricsCollector:
    """Thread-safe collector for offload request + cache metrics."""

    embedding_cache: CacheMetrics = field(default_factory=CacheMetrics)
    language_tool_cache: CacheMetrics = field(default_factory=CacheMetrics)
    extract_cache: CacheMetrics = field(default_factory=CacheMetrics)
    embedding_requests: RequestMetrics = field(default_factory=RequestMetrics)
    language_tool_requests: RequestMetrics = field(default_factory=RequestMetrics)
    extract_requests: RequestMetrics = field(default_factory=RequestMetrics)

    _lock: Lock = field(default_factory=Lock, init=False, repr=False)

    def record_cache_hit(self, *, kind: str) -> None:
        with self._lock:
            self._cache(kind).hits += 1

    def record_cache_miss(self, *, kind: str) -> None:
        with self._lock:
            self._cache(kind).misses += 1

    def record_cache_write(self, *, kind: str) -> None:
        with self._lock:
            self._cache(kind).writes += 1

    def record_cache_read_error(self, *, kind: str) -> None:
        with self._lock:
            self._cache(kind).read_errors += 1

    def record_cache_decode_error(self, *, kind: str) -> None:
        with self._lock:
            self._cache(kind).decode_errors += 1

    def record_request_ok(
        self,
        *,
        kind: str,
        duration_s: float,
        request_bytes: int,
        response_bytes: int,
        texts_in_request: int,
    ) -> None:
        with self._lock:
            self._requests(kind).record_ok(
                duration_s=duration_s,
                request_bytes=request_bytes,
                response_bytes=response_bytes,
                texts_in_request=texts_in_request,
            )

    def record_request_error(self, *, kind: str, duration_s: float, error_kind: str) -> None:
        with self._lock:
            self._requests(kind).record_error(duration_s=duration_s, kind=error_kind)

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            return {
                "schema_version": 1,
                "embedding": {
                    "cache": self.embedding_cache.to_dict(),
                    "requests": self.embedding_requests.to_summary_dict(),
                },
                "language_tool": {
                    "cache": self.language_tool_cache.to_dict(),
                    "requests": self.language_tool_requests.to_summary_dict(),
                },
                "extract": {
                    "cache": self.extract_cache.to_dict(),
                    "requests": self.extract_requests.to_summary_dict(),
                },
            }

    def _cache(self, kind: str) -> CacheMetrics:
        if kind == "embedding":
            return self.embedding_cache
        if kind == "language_tool":
            return self.language_tool_cache
        if kind == "extract":
            return self.extract_cache
        raise ValueError(f"Unknown cache kind: {kind}")

    def _requests(self, kind: str) -> RequestMetrics:
        if kind == "embedding":
            return self.embedding_requests
        if kind == "language_tool":
            return self.language_tool_requests
        if kind == "extract":
            return self.extract_requests
        raise ValueError(f"Unknown request kind: {kind}")


@dataclass(frozen=True)
class ExtractionBenchmark:
    """High-level benchmark summary for essays/sec."""

    mode: str
    records_processed: int
    elapsed_s: float

    def essays_per_second(self) -> float:
        if self.elapsed_s <= 0:
            return 0.0
        return float(self.records_processed / self.elapsed_s)

    def to_dict(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "records_processed": int(self.records_processed),
            "elapsed_s": float(self.elapsed_s),
            "essays_per_second": float(self.essays_per_second()),
        }


def persist_offload_metrics(
    *,
    output_path: Path,
    metrics: OffloadMetricsCollector | None,
    benchmarks: list[ExtractionBenchmark] | None = None,
) -> None:
    """Write offload metrics to disk as JSON."""

    payload: dict[str, object] = {
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    if benchmarks:
        payload["benchmarks"] = [benchmark.to_dict() for benchmark in benchmarks]
    payload["offload"] = metrics.snapshot() if metrics is not None else {"schema_version": 1}

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
