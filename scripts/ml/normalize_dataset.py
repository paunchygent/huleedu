#!/usr/bin/env python3
"""Normalize IELTS essays using the shared spell normalizer."""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

import pandas as pd  # type: ignore[import-untyped]
from huleedu_nlp_shared.feature_pipeline import FeaturePipeline
from huleedu_nlp_shared.feature_pipeline.extractors import NormalizationFeaturesExtractor
from huleedu_nlp_shared.normalization import FileWhitelist, SpellNormalizer
from huleedu_nlp_shared.normalization.protocols import SpellcheckerSettingsProtocol
from huleedu_service_libs.error_handling import (
    HuleEduError,
    raise_configuration_error,
    raise_processing_error,
    raise_resource_not_found,
    raise_unknown_error,
    raise_validation_error,
)

# Import L2 loader from service - need sys.path for scripts
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from services.spellchecker_service.spell_logic.l2_dictionary_loader import load_l2_errors


class CLISettings(SpellcheckerSettingsProtocol):
    """Minimal settings implementation for SpellNormalizer.

    This implementation provides conservative settings suitable for CLI
    batch processing operations without parallel processing complexity.
    """

    ENABLE_PARALLEL_PROCESSING: bool = False
    MAX_CONCURRENT_CORRECTIONS: int = 1
    SPELLCHECK_BATCH_SIZE: int = 100
    PARALLEL_TIMEOUT_SECONDS: float = 5.0
    PARALLEL_PROCESSING_MIN_WORDS: int = 1000
    ENABLE_CORRECTION_LOGGING: bool = False

    @property
    def effective_correction_log_dir(self) -> str:
        """Return the directory for correction logging.

        Returns:
            Path to the correction log directory.
        """
        return "/tmp/spell_corrections"


async def normalize_essay(
    text: str,
    pipeline: FeaturePipeline,
    essay_id: str | None = None,
) -> dict[str, Any]:
    """Normalize a single essay text using the shared feature pipeline.

    Args:
        text: The essay text to normalize.
        pipeline: Feature pipeline instance with SpellNormalizer dependency.
        essay_id: Optional essay identifier for tracing.

    Returns:
        Dictionary containing normalization results with keys:
        - corrected_text: The corrected text
        - total_corrections: Total number of corrections made
        - l2_corrections: Number of L2 dictionary corrections
        - spell_corrections: Number of spellchecker corrections
        - correction_density: Ratio of corrections to total words

    Raises:
        HuleEduError: If normalization fails.
    """
    try:
        pipeline_result = await pipeline.extract_features(
            raw_text=text,
            essay_id=essay_id,
        )
        context = pipeline_result.context
        metrics = context.spellcheck_metrics
        output: dict[str, Any] = {
            "corrected_text": context.normalized_text,
            "total_corrections": metrics.total_corrections,
            "l2_corrections": metrics.l2_dictionary_corrections,
            "spell_corrections": metrics.spellchecker_corrections,
            "correction_density": metrics.correction_density,
        }
        output.update(pipeline_result.features)
        return output
    except Exception as e:
        raise_processing_error(
            service="normalize_dataset",
            operation="normalize_essay",
            message=f"Failed to normalize essay: {e}",
            correlation_id=uuid4(),
        )


async def process_batch(
    essays: list[tuple[int, str]], pipeline: FeaturePipeline
) -> list[tuple[int, dict[str, Any]]]:
    """Process a batch of essays concurrently.

    Args:
        essays: List of (index, essay_text) tuples.
        normalizer: The spell normalizer instance.

    Returns:
        List of (index, result_dict) tuples.

    Raises:
        HuleEduError: If batch processing fails.
    """
    try:
        # Create concurrent tasks for the batch
        tasks = [normalize_essay(essay_text, pipeline) for _, essay_text in essays]

        # Process concurrently with timeout protection
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Check for any failures and re-raise as HuleEduError
        processed_results: list[tuple[int, dict[str, Any]]] = []
        for i, (idx, _) in enumerate(essays):
            result = results[i]
            if isinstance(result, Exception):
                raise_processing_error(
                    service="normalize_dataset",
                    operation="process_batch",
                    message=f"Failed to process essay {idx}: {result}",
                    correlation_id=uuid4(),
                )
            # result is guaranteed to be dict[str, Any] at this point
            processed_results.append((idx, result))  # type: ignore[arg-type]

        return processed_results
    except Exception as e:
        if isinstance(e, HuleEduError):
            raise
        raise_processing_error(
            service="normalize_dataset",
            operation="process_batch",
            message=f"Batch processing failed: {e}",
            correlation_id=uuid4(),
        )


async def main() -> None:
    """Main CLI function for normalizing essays.

    Processes IELTS essays using the shared spell normalizer with
    concurrent batch processing for improved performance.

    Raises:
        HuleEduError: If the normalization process fails.
    """
    parser = argparse.ArgumentParser(description="Normalize essays using spell checker")
    parser.add_argument("--input", type=Path, required=True, help="Input parquet file")
    parser.add_argument("--output", type=Path, required=True, help="Output parquet file")
    parser.add_argument(
        "--l2-dict",
        type=Path,
        default=Path("services/spellchecker_service/data/l2_error_dict/filtered_l2_dictionary.txt"),
        help="Path to L2 dictionary",
    )
    parser.add_argument(
        "--whitelist",
        type=Path,
        default=Path("services/spellchecker_service/data/whitelist/combined_whitelist.txt"),
        help="Path to whitelist",
    )
    parser.add_argument(
        "--batch-size", type=int, default=10, help="Number of essays to process concurrently"
    )
    args = parser.parse_args()

    try:
        # Validate input arguments
        if not args.input.exists():
            raise_resource_not_found(
                service="normalize_dataset",
                operation="validate_input",
                resource_type="input_file",
                resource_id=str(args.input),
                correlation_id=uuid4(),
            )

        if not args.l2_dict.exists():
            raise_resource_not_found(
                service="normalize_dataset",
                operation="validate_l2_dict",
                resource_type="l2_dictionary",
                resource_id=str(args.l2_dict),
                correlation_id=uuid4(),
            )

        if not args.whitelist.exists():
            raise_resource_not_found(
                service="normalize_dataset",
                operation="validate_whitelist",
                resource_type="whitelist_file",
                resource_id=str(args.whitelist),
                correlation_id=uuid4(),
            )

        # Load resources
        print(f"Loading L2 dictionary from {args.l2_dict}")
        l2_errors = load_l2_errors(str(args.l2_dict), filter_entries=False)
        print(f"Loaded {len(l2_errors)} L2 corrections")

        print(f"Loading whitelist from {args.whitelist}")
        try:
            whitelist = FileWhitelist(args.whitelist)
        except FileNotFoundError:
            raise_resource_not_found(
                service="normalize_dataset",
                operation="load_whitelist",
                resource_type="whitelist_file",
                resource_id=str(args.whitelist),
                correlation_id=uuid4(),
            )
        except Exception as e:
            raise_configuration_error(
                service="normalize_dataset",
                operation="load_whitelist",
                config_key="whitelist_file",
                message=f"Failed to load whitelist: {e}",
                correlation_id=uuid4(),
            )
        print(f"Loaded {whitelist.size:,} whitelist entries")

        # Create normalizer
        normalizer = SpellNormalizer(
            l2_errors=l2_errors,
            whitelist=whitelist,
            parallel_processor=None,
            settings=CLISettings(),
        )

        pipeline = FeaturePipeline(
            spell_normalizer=normalizer,
            language_tool_client=None,
            nlp_analyzer=None,
            extractors=[NormalizationFeaturesExtractor()],
        )

        # Process dataframe
        print(f"Reading {args.input}")
        df = pd.read_parquet(args.input)

        if "essay" not in df.columns:
            raise_validation_error(
                service="normalize_dataset",
                operation="validate_dataframe",
                field="essay",
                message="Input dataframe must contain 'essay' column",
                correlation_id=uuid4(),
            )

        print(f"Processing {len(df)} essays with batch size {args.batch_size}")

        # Prepare essays for batch processing
        essays = [(idx, row["essay"]) for idx, row in df.iterrows()]

        # Process in batches concurrently
        all_results: dict[int, dict[str, Any]] = {}
        start_time = time.time()

        for i in range(0, len(essays), args.batch_size):
            batch = essays[i : i + args.batch_size]
            batch_end = min(i + args.batch_size, len(essays))

            print(f"Processing batch {i // args.batch_size + 1}: essays {i}-{batch_end - 1}")

            batch_results = await process_batch(batch, pipeline)
            for idx, result in batch_results:
                all_results[idx] = result

        # Add results to dataframe in index order
        if all_results:
            result_keys = list(next(iter(all_results.values())).keys())
            for key in result_keys:
                df[key] = [all_results[idx][key] for idx in df.index]

        # Calculate statistics before saving
        elapsed_time = time.time() - start_time
        total_corrections = (
            df["total_corrections"].sum() if "total_corrections" in df.columns else 0
        )
        total_l2 = df["l2_corrections"].sum() if "l2_corrections" in df.columns else 0
        total_spell = df["spell_corrections"].sum() if "spell_corrections" in df.columns else 0
        avg_density = df["correction_density"].mean() if "correction_density" in df.columns else 0.0

        # Save output
        print(f"\nWriting {args.output}")
        df.to_parquet(args.output)

        # Print comprehensive statistics
        print(f"\n{'=' * 60}")
        print("NORMALIZATION COMPLETE")
        print(f"{'=' * 60}")
        print(f"Essays processed: {len(df)}")
        print(f"Total corrections: {total_corrections}")
        print(f"  - L2 dictionary: {total_l2} ({total_l2 / max(total_corrections, 1) * 100:.1f}%)")
        spell_pct = total_spell / max(total_corrections, 1) * 100
        print(f"  - Spellchecker: {total_spell} ({spell_pct:.1f}%)")
        print(f"Average corrections per essay: {total_corrections / max(len(df), 1):.1f}")
        print(f"Average correction density: {avg_density:.2f} per 100 words")
        essays_per_sec = len(df) / max(elapsed_time, 0.1)
        print(f"Processing time: {elapsed_time:.1f} seconds ({essays_per_sec:.1f} essays/sec)")
        print(f"{'=' * 60}")

    except HuleEduError:
        # Re-raise HuleEdu errors as-is
        raise
    except Exception as e:
        # Wrap unexpected errors
        raise_unknown_error(
            service="normalize_dataset",
            operation="main",
            message=f"Unexpected error: {e}",
            correlation_id=uuid4(),
        )


if __name__ == "__main__":
    asyncio.run(main())
