from __future__ import annotations

import asyncio
import json
import random
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Protocol
from uuid import uuid4

import aiohttp
from common_core import LLMProviderType

from scripts.prompt_cache_benchmark.fixtures import BenchmarkFixture
from scripts.prompt_cache_benchmark.limiter import DualBucketRateLimiter
from services.cj_assessment_service.cj_core_logic.prompt_templates import (
    PromptTemplateBuilder,
)
from services.cj_assessment_service.models_api import (
    CJLLMComparisonMetadata,
    ComparisonTask,
    EssayForComparison,
)
from services.cj_assessment_service.models_prompt import PromptBlockList
from services.llm_provider_service.exceptions import HuleEduError
from services.llm_provider_service.implementations.anthropic_provider_impl import (
    AnthropicProviderImpl,
)
from services.llm_provider_service.prompt_utils import compute_prompt_sha256


def _estimate_prompt_tokens(user_prompt: str) -> int:
    """Over-estimate input tokens to stay under Anthropic tier limits."""

    return max(int(len(user_prompt) / 3.3), 1)


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    idx = max(min(int(len(values) * pct), len(values) - 1), 0)
    return sorted(values)[idx]


@dataclass
class BenchmarkRequest:
    cache_key: str
    prompt_blocks: list[dict[str, Any]]
    user_prompt: str
    metadata: dict[str, Any]
    prompt_hash: str
    essay_a: EssayForComparison
    essay_b: EssayForComparison


@dataclass
class LLMCallResult:
    request: BenchmarkRequest
    status: str
    latency_ms: float
    cache_read_tokens: int
    cache_write_tokens: int
    total_prompt_tokens: int
    prompt_hash: str
    error: str | None = None
    status_code: int | None = None
    is_seed: bool = False


class LLMClientProtocol(Protocol):
    async def send(self, *, request: BenchmarkRequest) -> LLMCallResult: ...


class AnthropicLLMClient(LLMClientProtocol):
    """Thin wrapper around AnthropicProviderImpl for benchmarking."""

    def __init__(
        self,
        *,
        provider: AnthropicProviderImpl,
        model: str,
        rate_limiter: DualBucketRateLimiter,
    ) -> None:
        self.provider = provider
        self.model = model
        self.rate_limiter = rate_limiter

    async def send(self, *, request: BenchmarkRequest) -> LLMCallResult:
        tokens_estimate = _estimate_prompt_tokens(request.user_prompt)
        await self.rate_limiter.acquire(estimated_tokens=tokens_estimate)

        start = time.perf_counter()
        response = await self.provider.generate_comparison(
            user_prompt=request.user_prompt,
            prompt_blocks=request.prompt_blocks,
            correlation_id=uuid4(),
            model_override=self.model,
        )
        latency_ms = (time.perf_counter() - start) * 1000

        metadata = response.metadata or {}
        usage = metadata.get("usage") or {}
        cache_read = int(
            metadata.get("cache_read_input_tokens") or usage.get("cache_read_input_tokens") or 0
        )
        cache_write = int(
            metadata.get("cache_creation_input_tokens")
            or usage.get("cache_creation_input_tokens")
            or 0
        )

        prompt_tokens = int(usage.get("input_tokens") or 0)

        return LLMCallResult(
            request=request,
            status="success",
            latency_ms=latency_ms,
            cache_read_tokens=cache_read,
            cache_write_tokens=cache_write,
            total_prompt_tokens=prompt_tokens,
            prompt_hash=metadata.get("prompt_sha256") or request.prompt_hash,
        )


class PrometheusClient:
    """Optional Prometheus snapshot fetcher."""

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    async def query(self, session: aiohttp.ClientSession, query: str) -> dict[str, Any]:
        url = f"{self.base_url}/api/v1/query"
        async with session.get(url, params={"query": query}, timeout=10) as resp:
            resp.raise_for_status()
            payload = await resp.json()
            return {
                "query": query,
                "status": payload.get("status"),
                "data": payload.get("data"),
            }


@dataclass
class PerCacheKeyStats:
    cache_key: str
    hits: int
    misses: int
    bypass: int
    post_seed_miss_rate: float


@dataclass
class BenchmarkResult:
    fixture: str
    timestamp: str
    seeds: int
    total_requests: int
    hits: int
    misses: int
    bypass: int
    hit_rate: float
    post_seed_miss_rate: float
    ttl_violations: int
    rate_limit_errors: int
    tokens_read: int
    tokens_written: int
    latency_p50_ms: float
    latency_p95_ms: float
    per_cache_key: list[PerCacheKeyStats]
    promql_snapshots: list[dict[str, Any]]
    results: list[LLMCallResult]

    def to_json(self) -> dict[str, Any]:
        return {
            "fixture": self.fixture,
            "timestamp": self.timestamp,
            "seeds": self.seeds,
            "total_requests": self.total_requests,
            "hits": self.hits,
            "misses": self.misses,
            "bypass": self.bypass,
            "hit_rate": self.hit_rate,
            "post_seed_miss_rate": self.post_seed_miss_rate,
            "ttl_violations": self.ttl_violations,
            "rate_limit_errors": self.rate_limit_errors,
            "tokens": {"read": self.tokens_read, "write": self.tokens_written},
            "latency_ms": {"p50": self.latency_p50_ms, "p95": self.latency_p95_ms},
            "per_cache_key": [asdict(item) for item in self.per_cache_key],
            "promql_snapshots": self.promql_snapshots,
            "requests": [
                {
                    "cache_key": r.request.cache_key,
                    "essay_a": r.request.essay_a.id,
                    "essay_b": r.request.essay_b.id,
                    "status": r.status,
                    "latency_ms": r.latency_ms,
                    "cache_read_tokens": r.cache_read_tokens,
                    "cache_write_tokens": r.cache_write_tokens,
                    "total_prompt_tokens": r.total_prompt_tokens,
                    "prompt_hash": r.prompt_hash,
                    "error": r.error,
                    "status_code": r.status_code,
                    "is_seed": r.is_seed,
                }
                for r in self.results
            ],
        }


class BenchmarkRunner:
    def __init__(
        self,
        *,
        fixture: BenchmarkFixture,
        llm_client: LLMClientProtocol,
        jitter_range_ms: tuple[int, int] = (50, 150),
        concurrency: int = 3,
        use_extended_ttl: bool = False,
    ) -> None:
        self.fixture = fixture
        self.llm_client = llm_client
        self.jitter_range_ms = jitter_range_ms
        self.concurrency = max(concurrency, 1)
        self.use_extended_ttl = use_extended_ttl

    def _build_requests(self) -> list[BenchmarkRequest]:
        requests: list[BenchmarkRequest] = []

        for anchor, essay in self.fixture.comparisons():
            prompt_blocks_model: PromptBlockList = PromptTemplateBuilder.assemble_full_prompt(
                self.fixture.assessment_context,
                essay_a=anchor,
                essay_b=essay,
                use_extended_ttl=self.use_extended_ttl,
            )
            prompt_blocks = prompt_blocks_model.to_api_dict_list()
            user_prompt = PromptTemplateBuilder.render_prompt_text(prompt_blocks_model)
            prompt_hash = compute_prompt_sha256(
                provider=LLMProviderType.ANTHROPIC,
                user_prompt=user_prompt,
                prompt_blocks=prompt_blocks,
            )

            cacheable_hashes = sorted(
                block["content_hash"] for block in prompt_blocks if block.get("cacheable")
            )
            cache_key = "|".join(cacheable_hashes) if cacheable_hashes else "uncacheable"

            metadata = CJLLMComparisonMetadata.from_comparison_task(
                ComparisonTask(
                    essay_a=anchor,
                    essay_b=essay,
                    prompt=user_prompt,
                    prompt_blocks=prompt_blocks_model,
                ),
                bos_batch_id=self.fixture.assignment_id,
            ).to_request_metadata(
                {
                    "assignment_id": self.fixture.assignment_id,
                    "cj_source": "prompt_cache_benchmark",
                    "cj_request_type": "benchmark",
                }
            )

            requests.append(
                BenchmarkRequest(
                    cache_key=cache_key,
                    prompt_blocks=prompt_blocks,
                    user_prompt=user_prompt,
                    metadata=metadata,
                    prompt_hash=prompt_hash,
                    essay_a=anchor,
                    essay_b=essay,
                )
            )

        return requests

    @staticmethod
    def _select_seeds(
        requests: Iterable[BenchmarkRequest],
    ) -> tuple[list[BenchmarkRequest], list[BenchmarkRequest]]:
        seeds: list[BenchmarkRequest] = []
        remainder: list[BenchmarkRequest] = []
        seen: set[str] = set()

        for req in requests:
            if req.cache_key not in seen:
                seeds.append(req)
                seen.add(req.cache_key)
            else:
                remainder.append(req)
        return seeds, remainder

    async def _execute(self, request: BenchmarkRequest, *, is_seed: bool) -> LLMCallResult:
        try:
            result = await self.llm_client.send(request=request)
            result.is_seed = is_seed
            return result
        except ValueError as exc:
            return LLMCallResult(
                request=request,
                status="ttl_violation",
                latency_ms=0.0,
                cache_read_tokens=0,
                cache_write_tokens=0,
                total_prompt_tokens=0,
                prompt_hash=request.prompt_hash,
                error=str(exc),
                is_seed=is_seed,
            )
        except HuleEduError as exc:
            code = getattr(exc.error_detail, "error_code", None)
            status_code = getattr(exc.error_detail, "http_status_code", None)
            error_code = code.name if code else "unknown"
            return LLMCallResult(
                request=request,
                status=error_code.lower(),
                latency_ms=0.0,
                cache_read_tokens=0,
                cache_write_tokens=0,
                total_prompt_tokens=0,
                prompt_hash=request.prompt_hash,
                error=str(exc),
                status_code=status_code,
                is_seed=is_seed,
            )

    async def run(
        self,
        *,
        prom_client: PrometheusClient | None = None,
        session: aiohttp.ClientSession | None = None,
    ) -> BenchmarkResult:
        requests = self._build_requests()
        seeds, remainder = self._select_seeds(requests)
        all_results: list[LLMCallResult] = []

        # Seed phase (serialized + jitter)
        for req in seeds:
            all_results.append(await self._execute(req, is_seed=True))
            sleep_ms = random.randint(*self.jitter_range_ms)
            await asyncio.sleep(sleep_ms / 1000.0)

        # Main phase with limited concurrency
        semaphore = asyncio.Semaphore(self.concurrency)

        async def _run(req: BenchmarkRequest) -> None:
            async with semaphore:
                all_results.append(await self._execute(req, is_seed=False))

        await asyncio.gather(*[_run(req) for req in remainder])

        promql_snapshots: list[dict[str, Any]] = []
        if prom_client and session:
            queries = [
                (
                    "sum(rate(llm_provider_cache_scope_total"
                    '{scope="assignment",result="hit"}[5m])) '
                    '/ sum(rate(llm_provider_cache_scope_total{scope="assignment"}[5m]))'
                ),
                'sum(rate(llm_provider_prompt_cache_tokens_total{direction="read"}[5m]))',
                "increase(llm_provider_prompt_ttl_violations_total[1h])",
                'sum(rate(llm_provider_api_errors_total{error_type="rate_limit"}[5m]))',
            ]
            for q in queries:
                try:
                    promql_snapshots.append(await prom_client.query(session, q))
                except Exception as exc:  # noqa: BLE001
                    promql_snapshots.append({"query": q, "error": str(exc)})

        return self._summarize(all_results, seeds=len(seeds), promql_snapshots=promql_snapshots)

    def _summarize(
        self, results: list[LLMCallResult], *, seeds: int, promql_snapshots: list[dict[str, Any]]
    ) -> BenchmarkResult:
        hits = sum(1 for r in results if r.cache_read_tokens > 0)
        misses = sum(1 for r in results if r.cache_write_tokens > 0)
        bypass = sum(
            1
            for r in results
            if r.cache_read_tokens == 0 and r.cache_write_tokens == 0 and r.status == "success"
        )
        ttl_violations = sum(1 for r in results if r.status == "ttl_violation")
        rate_limit_errors = sum(1 for r in results if r.status in {"rate_limit", "quota_exceeded"})

        per_key: list[PerCacheKeyStats] = []
        post_seed_total = 0
        post_seed_misses = 0

        for key in {r.request.cache_key for r in results}:
            key_results = [r for r in results if r.request.cache_key == key]
            key_hits = sum(1 for r in key_results if r.cache_read_tokens > 0)
            key_misses = sum(1 for r in key_results if r.cache_write_tokens > 0)
            key_bypass = sum(
                1
                for r in key_results
                if r.cache_read_tokens == 0 and r.cache_write_tokens == 0 and r.status == "success"
            )
            remainder = key_results[1:] if key_results else []
            remainder_misses = sum(1 for r in remainder if r.cache_write_tokens > 0)
            remainder_total = len(remainder)
            post_seed_total += remainder_total
            post_seed_misses += remainder_misses
            per_key.append(
                PerCacheKeyStats(
                    cache_key=key,
                    hits=key_hits,
                    misses=key_misses,
                    bypass=key_bypass,
                    post_seed_miss_rate=remainder_misses / max(remainder_total, 1),
                )
            )

        post_seed_miss_rate = post_seed_misses / max(post_seed_total, 1)

        hit_rate = hits / max(hits + misses, 1)
        tokens_read = sum(r.cache_read_tokens for r in results)
        tokens_written = sum(r.cache_write_tokens for r in results)
        latencies = [r.latency_ms for r in results if r.status == "success"]

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

        return BenchmarkResult(
            fixture=self.fixture.name,
            timestamp=timestamp,
            seeds=seeds,
            total_requests=len(results),
            hits=hits,
            misses=misses,
            bypass=bypass,
            hit_rate=hit_rate,
            post_seed_miss_rate=post_seed_miss_rate,
            ttl_violations=ttl_violations,
            rate_limit_errors=rate_limit_errors,
            tokens_read=tokens_read,
            tokens_written=tokens_written,
            latency_p50_ms=_percentile(latencies, 0.5),
            latency_p95_ms=_percentile(latencies, 0.95),
            per_cache_key=per_key,
            promql_snapshots=promql_snapshots,
            results=results,
        )


def write_artifacts(
    result: BenchmarkResult,
    output_dir: Path,
    grafana_base_url: str | None = None,
    redact_output: bool = True,
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{result.timestamp}-prompt-cache-warmup"
    json_path = output_dir / f"{stem}.json"
    md_path = output_dir / f"{stem}.md"

    json_payload = result.to_json()
    if not redact_output:
        json_payload["assessment_context"] = (
            result.results[0].request.metadata.get("assessment_context") if result.results else {}
        )
        for idx, request_entry in enumerate(json_payload["requests"]):
            call_result = result.results[idx]
            request_entry["essay_a_text"] = call_result.request.essay_a.text_content
            request_entry["essay_b_text"] = call_result.request.essay_b.text_content
            request_entry["user_prompt"] = call_result.request.user_prompt
            request_entry["prompt_blocks"] = call_result.request.prompt_blocks

    with json_path.open("w", encoding="utf-8") as fp:
        json.dump(json_payload, fp, indent=2)

    grafana_link = (
        f"{grafana_base_url.rstrip('/')}/d/huleedu-llm-prompt-cache"
        if grafana_base_url
        else "set GRAFANA_BASE_URL to populate"
    )

    with md_path.open("w", encoding="utf-8") as fp:
        fp.write(f"# Prompt Cache Warmup Benchmark ({result.fixture})\n\n")
        fp.write(f"- Timestamp: {result.timestamp}\n")
        fp.write(f"- Requests: {result.total_requests} (seeds: {result.seeds})\n")
        fp.write(f"- Hit rate (post-warm): {result.hit_rate:.2%}\n")
        fp.write(f"- Post-seed miss rate: {result.post_seed_miss_rate:.2%}\n")
        fp.write(f"- Tokens saved (read): {result.tokens_read}\n")
        fp.write(f"- Tokens written (seed cost): {result.tokens_written}\n")
        fp.write(f"- TTL violations: {result.ttl_violations}\n")
        fp.write(f"- 429/rate-limit errors: {result.rate_limit_errors}\n")
        fp.write(
            f"- Latency p50/p95 (ms): {result.latency_p50_ms:.1f} / {result.latency_p95_ms:.1f}\n"
        )
        fp.write(f"- Artefact redaction: {'redacted' if redact_output else 'unredacted'}\n")
        fp.write(f"- Grafana dashboard: {grafana_link}\n")
        fp.write(f"- JSON artefact: {json_path}\n\n")

        fp.write("## Cache Hashes\n")
        for item in result.per_cache_key:
            fp.write(
                f"- {item.cache_key}: hits={item.hits}, misses={item.misses}, "
                f"post-seed-miss-rate={item.post_seed_miss_rate:.2%}\n"
            )

    return json_path, md_path
