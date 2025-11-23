from __future__ import annotations

import asyncio
from pathlib import Path

import aiohttp
import typer

from scripts.prompt_cache_benchmark.fixtures import get_fixture
from scripts.prompt_cache_benchmark.limiter import DualBucketRateLimiter
from scripts.prompt_cache_benchmark.loader import load_fixture_from_json
from scripts.prompt_cache_benchmark.runner import (
    AnthropicLLMClient,
    BenchmarkRunner,
    PrometheusClient,
    write_artifacts,
)
from services.llm_provider_service.config import Settings
from services.llm_provider_service.implementations.anthropic_provider_impl import (
    AnthropicProviderImpl,
)
from services.llm_provider_service.implementations.retry_manager_impl import (
    RetryManagerImpl,
)

app = typer.Typer(
    help=(
        "CJ prompt cache warm-up benchmark runner. "
        "Do NOT wrap this command in external timeouts; allow it to finish so artefacts persist."
    )
)


async def _run_benchmark(
    *,
    fixture_name: str,
    model: str,
    request_limit: int,
    token_limit: int,
    jitter_min_ms: int,
    jitter_max_ms: int,
    concurrency: int,
    extended_ttl: bool,
    output_dir: Path,
    prom_url: str | None,
    grafana_url: str | None,
    fixture_path: Path | None,
    redact_output: bool,
) -> None:
    fixture = load_fixture_from_json(fixture_path) if fixture_path else get_fixture(fixture_name)
    settings = Settings(
        ENABLE_PROMPT_CACHING=True,
        PROMPT_CACHE_TTL_SECONDS=3600,
        USE_EXTENDED_TTL_FOR_SERVICE_CONSTANTS=extended_ttl,
    )

    if not settings.ANTHROPIC_API_KEY.get_secret_value():
        typer.echo("ANTHROPIC_API_KEY not configured; export it to run the benchmark.", err=True)
        raise typer.Exit(code=1)

    limiter = DualBucketRateLimiter(
        requests_per_minute=request_limit,
        tokens_per_minute=token_limit,
    )

    prom_client = PrometheusClient(prom_url) if prom_url else None

    async with aiohttp.ClientSession() as session:
        retry_manager = RetryManagerImpl(settings)
        provider = AnthropicProviderImpl(
            session=session, settings=settings, retry_manager=retry_manager
        )
        llm_client = AnthropicLLMClient(provider=provider, model=model, rate_limiter=limiter)

        runner = BenchmarkRunner(
            fixture=fixture,
            llm_client=llm_client,
            jitter_range_ms=(jitter_min_ms, jitter_max_ms),
            concurrency=concurrency,
            use_extended_ttl=extended_ttl,
        )

        result = await runner.run(prom_client=prom_client, session=session if prom_client else None)
        json_path, md_path = write_artifacts(
            result,
            output_dir=output_dir,
            grafana_base_url=grafana_url,
            redact_output=redact_output,
        )
        typer.echo(f"Benchmark complete. Artefacts written:\n- {json_path}\n- {md_path}")


@app.command()
def run(
    fixture: str = typer.Option(
        "smoke",
        "--fixture",
        "-f",
        help="Fixture to run (smoke|full).",
        case_sensitive=False,
    ),
    model: str = typer.Option(
        "claude-haiku-4-5-20251001", "--model", "-m", help="Anthropic model id"
    ),
    request_limit: int = typer.Option(50, "--rpm", help="Request budget per minute"),
    token_limit: int = typer.Option(30000, "--tpm", help="Token budget per minute"),
    jitter_min_ms: int = typer.Option(50, "--jitter-min", help="Minimum jitter between seeds (ms)"),
    jitter_max_ms: int = typer.Option(
        150, "--jitter-max", help="Maximum jitter between seeds (ms)"
    ),
    concurrency: int = typer.Option(
        3, "--concurrency", "-c", help="Main run concurrency after warm-up"
    ),
    extended_ttl: bool = typer.Option(
        False, "--extended-ttl", help="Use 1h TTL for cacheable blocks"
    ),
    output_dir: Path = typer.Option(
        Path(".claude/work/reports/benchmarks"),
        "--output-dir",
        "-o",
        help="Output directory for artefacts",
    ),
    prom_url: str | None = typer.Option(
        None,
        "--prom-url",
        help="Prometheus base URL for optional snapshots (e.g., http://localhost:9090)",
    ),
    grafana_url: str | None = typer.Option(
        None, "--grafana-url", help="Grafana base URL for dashboard links"
    ),
    fixture_path: Path | None = typer.Option(
        None,
        "--fixture-path",
        "-p",
        help="Path to JSON fixture (anchors/students + prompts). Overrides built-in fixtures.",
    ),
    redact_output: bool = typer.Option(
        True,
        "--redact-output/--no-redact-output",
        help="Redact essay/prompt text in artefacts (default redacted).",
    ),
) -> None:
    """Run the prompt cache benchmark."""

    if jitter_min_ms < 0 or jitter_max_ms < jitter_min_ms:
        typer.echo("Invalid jitter range.", err=True)
        raise typer.Exit(code=1)

    asyncio.run(
        _run_benchmark(
            fixture_name=fixture,
            model=model,
            request_limit=request_limit,
            token_limit=token_limit,
            jitter_min_ms=jitter_min_ms,
            jitter_max_ms=jitter_max_ms,
            concurrency=concurrency,
            extended_ttl=extended_ttl,
            output_dir=output_dir,
            prom_url=prom_url,
            grafana_url=grafana_url,
            fixture_path=fixture_path,
            redact_output=redact_output,
        )
    )


if __name__ == "__main__":
    app()
