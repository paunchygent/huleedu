"""Lightweight server-side observability helpers for the Hemma offload service.

Goals:
- Avoid extra runtime dependencies (Prometheus client libs, psutil, etc.).
- Provide enough signal to tune throughput vs stability:
  - request counts + latency distribution
  - GPU availability + memory pressure
"""

from __future__ import annotations

import os
import time
from collections import Counter, deque
from dataclasses import dataclass, field
from typing import Any


def _percentile(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    if quantile <= 0:
        return float(min(values))
    if quantile >= 1:
        return float(max(values))
    sorted_values = sorted(values)
    position = (len(sorted_values) - 1) * quantile
    lower_index = int(position)
    upper_index = min(lower_index + 1, len(sorted_values) - 1)
    if lower_index == upper_index:
        return float(sorted_values[lower_index])
    weight = position - lower_index
    lower = sorted_values[lower_index]
    upper = sorted_values[upper_index]
    return float(lower + (upper - lower) * weight)


@dataclass(frozen=True)
class ServiceLabels:
    service: str
    environment: str
    version: str

    @staticmethod
    def from_env(*, service: str, version: str | None) -> "ServiceLabels":
        env = os.environ.get("HULEEDU_ENVIRONMENT") or os.environ.get("ENVIRONMENT") or "unknown"
        resolved_version = version or "unknown"
        return ServiceLabels(service=service, environment=env, version=resolved_version)


@dataclass
class EndpointStats:
    method: str
    endpoint: str
    in_flight: int = 0
    status_counts: Counter[int] = field(default_factory=Counter)
    durations_s: deque[float] = field(default_factory=lambda: deque(maxlen=20_000))
    total_duration_s: float = 0.0
    total_requests: int = 0
    total_items: int = 0

    def record_start(self) -> None:
        self.in_flight += 1

    def record_end(self, *, status: int, duration_s: float, items: int | None = None) -> None:
        self.in_flight = max(0, self.in_flight - 1)
        self.total_requests += 1
        self.status_counts[int(status)] += 1
        self.total_duration_s += float(duration_s)
        self.durations_s.append(float(duration_s))
        if items is not None:
            self.total_items += int(items)

    def snapshot(self) -> dict[str, object]:
        durations = list(self.durations_s)
        return {
            "method": self.method,
            "endpoint": self.endpoint,
            "in_flight": int(self.in_flight),
            "requests_total": int(self.total_requests),
            "items_total": int(self.total_items),
            "duration_seconds": {
                "sum": float(self.total_duration_s),
                "mean": float(self.total_duration_s / self.total_requests)
                if self.total_requests
                else 0.0,
                "p50": float(_percentile(durations, 0.50)),
                "p95": float(_percentile(durations, 0.95)),
                "p99": float(_percentile(durations, 0.99)),
            },
            "status_counts": {str(k): int(v) for k, v in sorted(self.status_counts.items())},
        }


@dataclass
class OffloadServerMetrics:
    started_monotonic: float = field(default_factory=time.monotonic)
    endpoints: dict[tuple[str, str], EndpointStats] = field(default_factory=dict)

    def get_endpoint(self, *, method: str, endpoint: str) -> EndpointStats:
        key = (method.upper(), endpoint)
        if key not in self.endpoints:
            self.endpoints[key] = EndpointStats(method=key[0], endpoint=key[1])
        return self.endpoints[key]

    def uptime_seconds(self) -> float:
        return float(time.monotonic() - self.started_monotonic)

    def snapshot(self) -> dict[str, object]:
        return {
            "uptime_seconds": float(self.uptime_seconds()),
            "endpoints": [
                stats.snapshot()
                for _, stats in sorted(self.endpoints.items(), key=lambda kv: kv[0])
            ],
        }


@dataclass
class GpuProbe:
    """Best-effort GPU probe.

    Prefer torch (available inside the offload container). We avoid host-level tools
    to keep the container image minimal.
    """

    ttl_seconds: float = 2.0
    _last_at: float = 0.0
    _last: dict[str, Any] = field(default_factory=dict)

    def snapshot(self) -> dict[str, Any]:
        now = time.monotonic()
        if self._last and (now - self._last_at) < self.ttl_seconds:
            return self._last

        snapshot: dict[str, Any] = {"torch": {"available": False}}
        try:
            import torch  # noqa: PLC0415
        except Exception as exc:  # noqa: BLE001
            snapshot["torch"] = {"available": False, "error": str(exc)}
            self._last = snapshot
            self._last_at = now
            return snapshot

        torch_available = bool(torch.cuda.is_available())
        device_count = int(torch.cuda.device_count()) if torch_available else 0
        devices: list[dict[str, Any]] = []
        for idx in range(device_count):
            device_info: dict[str, Any] = {"index": int(idx)}
            try:
                device_info["name"] = str(torch.cuda.get_device_name(idx))
            except Exception as exc:  # noqa: BLE001
                device_info["name_error"] = str(exc)
            try:
                props = torch.cuda.get_device_properties(idx)
                device_info["total_memory_bytes"] = int(getattr(props, "total_memory", 0))
            except Exception as exc:  # noqa: BLE001
                device_info["props_error"] = str(exc)
            try:
                free_b, total_b = torch.cuda.mem_get_info(idx)
                device_info["mem_free_bytes"] = int(free_b)
                device_info["mem_total_bytes"] = int(total_b)
            except Exception:
                pass
            try:
                device_info["torch_memory_allocated_bytes"] = int(torch.cuda.memory_allocated(idx))
                device_info["torch_memory_reserved_bytes"] = int(torch.cuda.memory_reserved(idx))
            except Exception:
                pass
            devices.append(device_info)

        snapshot["torch"] = {
            "available": torch_available,
            "device_count": device_count,
            "devices": devices,
        }

        self._last = snapshot
        self._last_at = now
        return snapshot


def _fmt_labels(labels: dict[str, str]) -> str:
    if not labels:
        return ""
    parts = [f'{k}="{v}"' for k, v in sorted(labels.items())]
    return "{" + ",".join(parts) + "}"


def build_prometheus_metrics_text(
    *,
    labels: ServiceLabels,
    metrics: OffloadServerMetrics,
    gpu: dict[str, Any],
) -> str:
    base = {
        "service": labels.service,
        "environment": labels.environment,
        "version": labels.version,
    }

    lines: list[str] = []
    lines.append(
        "huleedu_offload_build_info"
        + _fmt_labels(base | {"python": f"{os.sys.version_info.major}.{os.sys.version_info.minor}"})
        + " 1"
    )
    lines.append(
        "huleedu_offload_uptime_seconds" + _fmt_labels(base) + f" {metrics.uptime_seconds():.6f}"
    )

    torch_info = gpu.get("torch", {})
    torch_available = 1 if torch_info.get("available") else 0
    lines.append("huleedu_offload_gpu_available" + _fmt_labels(base) + f" {torch_available}")
    device_count = int(torch_info.get("device_count") or 0)
    lines.append("huleedu_offload_gpu_device_count" + _fmt_labels(base) + f" {int(device_count)}")

    for device in torch_info.get("devices", []):
        dev_labels = base | {"device": str(device.get("index", 0))}
        if "name" in device:
            lines.append(
                "huleedu_offload_gpu_name_info"
                + _fmt_labels(dev_labels | {"name": str(device["name"])})
                + " 1"
            )
        for key, metric_name in (
            ("total_memory_bytes", "huleedu_offload_gpu_total_memory_bytes"),
            ("mem_free_bytes", "huleedu_offload_gpu_free_memory_bytes"),
            ("mem_total_bytes", "huleedu_offload_gpu_mem_total_bytes"),
            ("torch_memory_allocated_bytes", "huleedu_offload_gpu_torch_memory_allocated_bytes"),
            ("torch_memory_reserved_bytes", "huleedu_offload_gpu_torch_memory_reserved_bytes"),
        ):
            if key in device:
                lines.append(metric_name + _fmt_labels(dev_labels) + f" {int(device[key])}")

    for (method, endpoint), stats in sorted(metrics.endpoints.items(), key=lambda kv: kv[0]):
        endpoint_labels = base | {"method": method, "endpoint": endpoint}
        snap = stats.snapshot()
        lines.append(
            "huleedu_offload_http_requests_in_flight"
            + _fmt_labels(endpoint_labels)
            + f" {int(snap['in_flight'])}"
        )
        lines.append(
            "huleedu_offload_http_requests_total"
            + _fmt_labels(endpoint_labels)
            + f" {int(snap['requests_total'])}"
        )
        lines.append(
            "huleedu_offload_items_total"
            + _fmt_labels(endpoint_labels)
            + f" {int(snap['items_total'])}"
        )

        duration = snap["duration_seconds"]
        lines.append(
            "huleedu_offload_http_request_duration_seconds_sum"
            + _fmt_labels(endpoint_labels)
            + f" {float(duration['sum']):.6f}"
        )
        lines.append(
            "huleedu_offload_http_request_duration_seconds_mean"
            + _fmt_labels(endpoint_labels)
            + f" {float(duration['mean']):.6f}"
        )
        for q in ("p50", "p95", "p99"):
            lines.append(
                "huleedu_offload_http_request_duration_seconds"
                + _fmt_labels(endpoint_labels | {"quantile": q})
                + f" {float(duration[q]):.6f}"
            )
        for status_code, count in snap["status_counts"].items():
            lines.append(
                "huleedu_offload_http_responses_total"
                + _fmt_labels(endpoint_labels | {"status_code": status_code})
                + f" {int(count)}"
            )

    return "\n".join(lines) + "\n"
