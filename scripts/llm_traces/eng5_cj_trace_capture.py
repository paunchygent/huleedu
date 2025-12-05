from __future__ import annotations

import argparse
import asyncio
import json
import os
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from statistics import mean
from typing import Iterable, Sequence, TypedDict
from uuid import uuid4

from aiokafka import AIOKafkaConsumer
from common_core.events.llm_provider_events import LLMComparisonResultV1


class ResponseTimeStats(TypedDict):
    """Aggregated response time statistics in milliseconds."""

    min_ms: float
    mean_ms: float
    p95_ms: float
    p99_ms: float


class TokenFieldStats(TypedDict):
    """Aggregated statistics for a single token field."""

    min: float
    mean: float
    max: float


class TokenUsageSummary(TypedDict):
    """Aggregated token usage statistics."""

    prompt_tokens: TokenFieldStats
    completion_tokens: TokenFieldStats
    total_tokens: TokenFieldStats


class LLMTraceSummary(TypedDict):
    """Compact, machine-readable summary of an LLM comparison trace."""

    scenario_id: str
    total_events: int
    success_count: int
    error_count: int
    winner_counts: dict[str, int]
    error_code_counts: dict[str, int]
    response_time_ms: ResponseTimeStats
    token_usage: TokenUsageSummary
    bt_se_summary: dict[str, float] | None
    bt_quality_flags: dict[str, bool] | None


def _compute_percentile(values: Sequence[int], percentile: float) -> float:
    """Compute an approximate percentile for a small list of integers."""

    if not values:
        return 0.0

    if percentile <= 0:
        return float(min(values))
    if percentile >= 100:
        return float(max(values))

    sorted_values = sorted(values)
    # Simple percentile index: nearest-rank method
    k = (len(sorted_values) - 1) * (percentile / 100.0)
    lower = int(k)
    upper = min(lower + 1, len(sorted_values) - 1)
    weight = k - lower
    return float(sorted_values[lower] * (1.0 - weight) + sorted_values[upper] * weight)


def _compute_token_field_stats(values: Sequence[int]) -> TokenFieldStats:
    if not values:
        return TokenFieldStats(min=0.0, mean=0.0, max=0.0)

    return TokenFieldStats(
        min=float(min(values)),
        mean=float(mean(values)),
        max=float(max(values)),
    )


def compute_llm_trace_summary(
    callbacks: Sequence[LLMComparisonResultV1],
    *,
    scenario_id: str,
) -> LLMTraceSummary:
    """Compute aggregate metrics for a sequence of LLM comparison callbacks."""

    total_events = len(callbacks)
    success_count = sum(1 for c in callbacks if c.is_success)
    error_count = total_events - success_count

    winner_counter: Counter[str] = Counter()
    error_code_counter: Counter[str] = Counter()
    response_times: list[int] = []
    prompt_tokens: list[int] = []
    completion_tokens: list[int] = []
    total_tokens: list[int] = []

    for callback in callbacks:
        if callback.is_success:
            winner_counter[str(callback.winner.value)] += 1  # type: ignore[union-attr]
        else:
            winner_counter["error"] += 1

        if callback.error_detail is not None:
            error_code_counter[str(callback.error_detail.error_code)] += 1

        response_times.append(callback.response_time_ms)
        prompt_tokens.append(callback.token_usage.prompt_tokens)
        completion_tokens.append(callback.token_usage.completion_tokens)
        total_tokens.append(callback.token_usage.total_tokens)

    response_time_stats: ResponseTimeStats = {
        "min_ms": float(min(response_times)) if response_times else 0.0,
        "mean_ms": float(mean(response_times)) if response_times else 0.0,
        "p95_ms": _compute_percentile(response_times, 95.0),
        "p99_ms": _compute_percentile(response_times, 99.0),
    }

    token_usage_summary: TokenUsageSummary = {
        "prompt_tokens": _compute_token_field_stats(prompt_tokens),
        "completion_tokens": _compute_token_field_stats(completion_tokens),
        "total_tokens": _compute_token_field_stats(total_tokens),
    }

    return {
        "scenario_id": scenario_id,
        "total_events": total_events,
        "success_count": success_count,
        "error_count": error_count,
        "winner_counts": dict(winner_counter),
        "error_code_counts": dict(error_code_counter),
        "response_time_ms": response_time_stats,
        "token_usage": token_usage_summary,
        # CJ/BT diagnostics are populated in CJ service; for this harness
        # we record placeholders that future phases can fill using CJ metadata.
        "bt_se_summary": None,
        "bt_quality_flags": None,
    }


@dataclass
class TraceCaptureConfig:
    """Configuration for a single trace capture run."""

    scenario_id: str
    bos_batch_id: str
    callback_topic: str
    bootstrap_servers: str
    expected_count: int
    timeout_seconds: int
    output_dir: Path


async def collect_callbacks_for_batch(config: TraceCaptureConfig) -> list[LLMComparisonResultV1]:
    """Collect LLMComparisonResultV1 callbacks for a specific BOS batch."""

    consumer = AIOKafkaConsumer(
        config.callback_topic,
        bootstrap_servers=config.bootstrap_servers,
        group_id=f"eng5_cj_trace_capture_{uuid4().hex[:8]}",
        auto_offset_reset="earliest",
        enable_auto_commit=False,
    )

    callbacks: list[LLMComparisonResultV1] = []
    loop = asyncio.get_running_loop()
    deadline = loop.time() + config.timeout_seconds

    try:
        await consumer.start()

        while loop.time() < deadline:
            if config.expected_count > 0 and len(callbacks) >= config.expected_count:
                break

            msg_batch = await consumer.getmany(timeout_ms=1000, max_records=50)
            if not msg_batch:
                continue

            for _topic_partition, messages in msg_batch.items():
                for message in messages:
                    raw_value = message.value
                    if isinstance(raw_value, bytes):
                        raw_value = raw_value.decode("utf-8")

                    try:
                        envelope = json.loads(raw_value)
                    except json.JSONDecodeError:
                        continue

                    if envelope.get("event_type") != "LLMComparisonResultV1":
                        continue

                    data = envelope.get("data")
                    if not isinstance(data, dict):
                        continue

                    metadata = data.get("request_metadata") or {}
                    if metadata.get("bos_batch_id") != config.bos_batch_id:
                        continue

                    try:
                        callbacks.append(LLMComparisonResultV1.model_validate(data))
                    except Exception:
                        # Ignore malformed events; schema validation is covered elsewhere
                        continue

        return callbacks
    finally:
        await consumer.stop()


def write_callbacks_jsonl(callbacks: Iterable[LLMComparisonResultV1], output_path: Path) -> None:
    """Write callbacks as JSONL (one LLMComparisonResultV1 per line)."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        for callback in callbacks:
            data = callback.model_dump(mode="json")
            json_line = json.dumps(data, ensure_ascii=False)
            f.write(json_line + "\n")


def write_summary_json(summary: LLMTraceSummary, output_path: Path) -> None:
    """Write the aggregated summary as pretty-printed JSON."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2, sort_keys=True)


def _parse_args(argv: Sequence[str] | None = None) -> TraceCaptureConfig:
    parser = argparse.ArgumentParser(
        description=(
            "Capture ENG5/CJ LLMComparisonResultV1 callbacks for a single BOS batch, "
            "persist them as fixtures, and compute a metrics summary."
        )
    )

    parser.add_argument(
        "--scenario-id",
        required=True,
        help="Stable identifier for this scenario (used in output directory and summary).",
    )
    parser.add_argument(
        "--bos-batch-id",
        required=True,
        help="BOS batch id used to filter callbacks (from request_metadata.bos_batch_id).",
    )
    parser.add_argument(
        "--callback-topic",
        default="llm.provider.callback.v1",
        help="Kafka topic where LLMComparisonResultV1 callbacks are published.",
    )
    parser.add_argument(
        "--bootstrap-servers",
        default=os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9093"),
        help="Kafka bootstrap servers (env KAFKA_BOOTSTRAP_SERVERS overrides default).",
    )
    parser.add_argument(
        "--expected-count",
        type=int,
        default=0,
        help=(
            "Optional expected number of callbacks for this batch. "
            "If > 0, collection stops once this many callbacks are seen."
        ),
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=120,
        help="Maximum time in seconds to wait for callbacks before stopping.",
    )
    parser.add_argument(
        "--output-dir",
        default="tests/data/llm_traces",
        help="Base directory for writing fixtures (scenario_id is appended).",
    )

    args = parser.parse_args(argv)

    output_dir = Path(args.output_dir).expanduser().resolve() / args.scenario_id

    return TraceCaptureConfig(
        scenario_id=args.scenario_id,
        bos_batch_id=args.bos_batch_id,
        callback_topic=args.callback_topic,
        bootstrap_servers=args.bootstrap_servers,
        expected_count=args.expected_count,
        timeout_seconds=args.timeout_seconds,
        output_dir=output_dir,
    )


async def _run_async(config: TraceCaptureConfig) -> None:
    start = datetime.utcnow()
    callbacks = await collect_callbacks_for_batch(config)

    callbacks_path = config.output_dir / "llm_callbacks.jsonl"
    summary_path = config.output_dir / "summary.json"

    write_callbacks_jsonl(callbacks, callbacks_path)

    summary = compute_llm_trace_summary(
        callbacks,
        scenario_id=config.scenario_id,
    )
    write_summary_json(summary, summary_path)

    end = datetime.utcnow()
    duration = (end - start).total_seconds()

    print(f"[eng5_cj_trace_capture] Scenario: {config.scenario_id}")
    print(f"  BOS batch id: {config.bos_batch_id}")
    print(f"  Collected callbacks: {len(callbacks)}")
    print(f"  Output directory: {config.output_dir}")
    print(f"  Duration: {duration:.1f}s")


def main(argv: Sequence[str] | None = None) -> None:
    """Entry point for CLI usage."""

    config = _parse_args(argv)
    asyncio.run(_run_async(config))


if __name__ == "__main__":
    main()
