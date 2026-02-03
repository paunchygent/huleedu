from __future__ import annotations

import json

from scripts.ml_training.essay_scoring.offload.metrics import (
    ExtractionBenchmark,
    OffloadMetricsCollector,
    persist_offload_metrics,
)


def test_persist_offload_metrics_writes_json_with_benchmarks(tmp_path) -> None:
    metrics = OffloadMetricsCollector()
    metrics.record_cache_miss(kind="embedding")
    metrics.record_cache_write(kind="embedding")
    metrics.record_request_ok(
        kind="embedding",
        duration_s=0.25,
        request_bytes=123,
        response_bytes=456,
        texts_in_request=2,
    )

    benchmarks = [
        ExtractionBenchmark(mode="feature_extraction_total", records_processed=10, elapsed_s=2.0)
    ]
    out_path = tmp_path / "offload_metrics.json"
    persist_offload_metrics(output_path=out_path, metrics=metrics, benchmarks=benchmarks)

    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["offload"]["schema_version"] == 1
    assert payload["offload"]["embedding"]["cache"]["misses"] == 1
    assert payload["offload"]["embedding"]["cache"]["writes"] == 1
    assert payload["offload"]["embedding"]["requests"]["requests_ok"] == 1

    benches = payload["benchmarks"]
    assert len(benches) == 1
    assert benches[0]["records_processed"] == 10
    assert benches[0]["elapsed_s"] == 2.0
    assert benches[0]["essays_per_second"] == 5.0
