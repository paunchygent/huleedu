"""ENG5 runner optional post-run database extraction (R5).

This wraps the existing CJ DB diagnostics script so execute runs can optionally
capture a snapshot of the batch state/results after successful completion.
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Eng5DbExtractionResult:
    batch_identifier: str
    output_path: Path
    output_format: str
    exit_code: int
    error: str | None = None


def run_eng5_db_extraction(
    *,
    batch_identifier: str,
    output_dir: Path,
    output_format: str = "text",
) -> Eng5DbExtractionResult:
    """Run CJ DB extraction and write output under *output_dir*.

    Note: this relies on the same env vars as the underlying script:
    HULEEDU_DB_HOST, HULEEDU_CJ_DB_PORT/HULEEDU_DB_PORT, HULEEDU_DB_USER,
    HULEEDU_DB_PASSWORD.
    """
    from scripts.cj_assessment_service.diagnostics import extract_cj_results

    if output_format not in {"text", "json"}:
        raise ValueError("output_format must be 'text' or 'json'")

    output_dir.mkdir(parents=True, exist_ok=True)
    suffix = "json" if output_format == "json" else "txt"
    output_path = output_dir / f"cj_results_{batch_identifier}.{suffix}"

    args = argparse.Namespace(
        batch_identifier=batch_identifier,
        format=output_format,
        output=output_path,
    )

    try:
        exit_code = int(asyncio.run(extract_cj_results.main_async(args)))
        return Eng5DbExtractionResult(
            batch_identifier=batch_identifier,
            output_path=output_path,
            output_format=output_format,
            exit_code=exit_code,
        )
    except Exception as exc:  # noqa: BLE001
        return Eng5DbExtractionResult(
            batch_identifier=batch_identifier,
            output_path=output_path,
            output_format=output_format,
            exit_code=1,
            error=f"{exc.__class__.__name__}: {exc}",
        )
