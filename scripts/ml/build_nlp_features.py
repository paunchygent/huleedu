#!/usr/bin/env python3
"""Build NLP feature matrix using the shared feature pipeline."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any
from uuid import uuid4

import pandas as pd  # type: ignore[import-untyped]
from huleedu_nlp_shared.feature_pipeline import FeaturePipeline
from huleedu_nlp_shared.feature_pipeline.extractors import NormalizationFeaturesExtractor
from huleedu_nlp_shared.normalization import FileWhitelist, SpellNormalizer
from huleedu_service_libs.error_handling import (
    HuleEduError,
    raise_configuration_error,
    raise_processing_error,
    raise_resource_not_found,
    raise_unknown_error,
    raise_validation_error,
)

from scripts.ml.normalize_dataset import CLISettings  # type: ignore[import-not-found]

# Ensure repository root is on path for service imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from services.spellchecker_service.spell_logic.l2_dictionary_loader import load_l2_errors


async def _extract_features(
    text: str,
    pipeline: FeaturePipeline,
    essay_id: str | None = None,
) -> dict[str, Any]:
    """Run feature pipeline for a single essay."""

    try:
        pipeline_result = await pipeline.extract_features(
            raw_text=text,
            essay_id=essay_id,
        )
    except Exception as e:
        raise_processing_error(
            service="build_nlp_features",
            operation="extract_features",
            message=f"Failed to extract features: {e}",
            correlation_id=uuid4(),
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


async def _process_batch(
    essays: list[tuple[int, str]], pipeline: FeaturePipeline
) -> list[tuple[int, dict[str, Any]]]:
    """Concurrent feature extraction for a batch of essays."""

    try:
        tasks = [_extract_features(essay_text, pipeline) for _, essay_text in essays]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        processed: list[tuple[int, dict[str, Any]]] = []
        for i, (idx, _) in enumerate(essays):
            result = results[i]
            if isinstance(result, Exception):
                raise_processing_error(
                    service="build_nlp_features",
                    operation="process_batch",
                    message=f"Failed to process essay {idx}: {result}",
                    correlation_id=uuid4(),
                )
            processed.append((idx, result))  # type: ignore[arg-type]

        return processed
    except Exception as e:
        if isinstance(e, HuleEduError):
            raise
        raise_processing_error(
            service="build_nlp_features",
            operation="process_batch",
            message=f"Batch processing failed: {e}",
            correlation_id=uuid4(),
        )


async def main() -> None:
    """CLI entrypoint for building feature matrix from essays."""
    parser = argparse.ArgumentParser(description="Build NLP feature matrix")
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
        if not args.input.exists():
            raise_resource_not_found(
                service="build_nlp_features",
                operation="validate_input",
                resource_type="input_file",
                resource_id=str(args.input),
                correlation_id=uuid4(),
            )

        if not args.l2_dict.exists():
            raise_resource_not_found(
                service="build_nlp_features",
                operation="validate_l2_dict",
                resource_type="l2_dictionary",
                resource_id=str(args.l2_dict),
                correlation_id=uuid4(),
            )

        if not args.whitelist.exists():
            raise_resource_not_found(
                service="build_nlp_features",
                operation="validate_whitelist",
                resource_type="whitelist_file",
                resource_id=str(args.whitelist),
                correlation_id=uuid4(),
            )

        print(f"Reading {args.input}")
        df = pd.read_parquet(args.input)

        if "essay" not in df.columns:
            raise_validation_error(
                service="build_nlp_features",
                operation="validate_dataframe",
                field="essay",
                message="Input dataframe must contain 'essay' column",
                correlation_id=uuid4(),
            )

        print(f"Loading L2 dictionary from {args.l2_dict}")
        l2_errors = load_l2_errors(str(args.l2_dict), filter_entries=False)
        print(f"Loaded {len(l2_errors)} L2 corrections")

        print(f"Loading whitelist from {args.whitelist}")
        try:
            whitelist = FileWhitelist(args.whitelist)
        except FileNotFoundError:
            raise_resource_not_found(
                service="build_nlp_features",
                operation="load_whitelist",
                resource_type="whitelist_file",
                resource_id=str(args.whitelist),
                correlation_id=uuid4(),
            )
        except Exception as e:
            raise_configuration_error(
                service="build_nlp_features",
                operation="load_whitelist",
                config_key="whitelist_file",
                message=f"Failed to load whitelist: {e}",
                correlation_id=uuid4(),
            )
        print(f"Loaded {whitelist.size:,} whitelist entries")

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

        essays = [(idx, row["essay"]) for idx, row in df.iterrows()]

        print(f"Generating features for {len(essays)} essays with batch size {args.batch_size}")

        all_results: dict[int, dict[str, Any]] = {}
        for i in range(0, len(essays), args.batch_size):
            batch = essays[i : i + args.batch_size]
            batch_results = await _process_batch(batch, pipeline)
            for idx, result in batch_results:
                all_results[idx] = result

        feature_records: list[dict[str, Any]] = []
        for idx in df.index:
            feature_record = {"essay_index": idx}
            if "essay_id" in df.columns:
                feature_record["essay_id"] = df.at[idx, "essay_id"]
            feature_record.update(all_results[idx])
            feature_records.append(feature_record)

        feature_df = pd.DataFrame(feature_records)
        feature_df.to_parquet(args.output, index=False)
        print(f"Wrote features to {args.output}")

    except HuleEduError:
        raise
    except Exception as e:
        raise_unknown_error(
            service="build_nlp_features",
            operation="main",
            message=f"Unexpected error: {e}",
            correlation_id=uuid4(),
        )


if __name__ == "__main__":
    asyncio.run(main())
