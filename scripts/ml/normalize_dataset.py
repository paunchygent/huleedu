#!/usr/bin/env python3
"""Normalize IELTS essays using the shared spell normalizer."""

import argparse
import asyncio
from pathlib import Path
import pandas as pd
from huleedu_nlp_shared.normalization import SpellNormalizer

# Import L2 loader from service (coupling acceptable for CLI tool)
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from services.spellchecker_service.spell_logic.l2_dictionary_loader import load_l2_errors


class SimpleWhitelist:
    """Minimal whitelist implementation for CLI usage."""

    def __init__(self, path: str):
        self.words = set()
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                word = line.strip().lower()
                if word:
                    self.words.add(word)

    def is_whitelisted(self, word: str) -> bool:
        return word.lower() in self.words


class CLISettings:
    """Minimal settings implementation for SpellNormalizer."""

    ENABLE_PARALLEL_PROCESSING = False
    MAX_CONCURRENT_CORRECTIONS = 1
    SPELLCHECK_BATCH_SIZE = 100
    PARALLEL_TIMEOUT_SECONDS = 5.0
    PARALLEL_PROCESSING_MIN_WORDS = 1000
    ENABLE_CORRECTION_LOGGING = False

    @property
    def effective_correction_log_dir(self) -> str:
        return "/tmp/spell_corrections"


async def normalize_essay(text: str, normalizer: SpellNormalizer) -> dict:
    """Normalize a single essay text."""
    result = await normalizer.normalize_text(text=text)
    return {
        "corrected_text": result.corrected_text,
        "total_corrections": result.total_corrections,
        "l2_corrections": result.l2_dictionary_corrections,
        "spell_corrections": result.spellchecker_corrections,
        "correction_density": result.correction_density,
    }


async def main():
    parser = argparse.ArgumentParser(description="Normalize essays using spell checker")
    parser.add_argument("--input", type=Path, required=True, help="Input parquet file")
    parser.add_argument("--output", type=Path, required=True, help="Output parquet file")
    parser.add_argument(
        "--l2-dict",
        type=Path,
        default=Path("services/spellchecker_service/data/l2_error_dict/filtered_l2_dictionary.txt"),
        help="Path to L2 dictionary"
    )
    parser.add_argument(
        "--whitelist",
        type=Path,
        default=Path("services/spellchecker_service/data/whitelist/combined_whitelist.txt"),
        help="Path to whitelist"
    )
    args = parser.parse_args()

    # Load resources
    print(f"Loading L2 dictionary from {args.l2_dict}")
    l2_errors = load_l2_errors(str(args.l2_dict), filter_entries=False)
    print(f"Loaded {len(l2_errors)} L2 corrections")

    print(f"Loading whitelist from {args.whitelist}")
    whitelist = SimpleWhitelist(str(args.whitelist))
    print(f"Loaded {len(whitelist.words)} whitelist entries")

    # Create normalizer
    normalizer = SpellNormalizer(
        l2_errors=l2_errors,
        whitelist=whitelist,
        parallel_processor=None,
        settings=CLISettings(),
    )

    # Process dataframe
    print(f"Reading {args.input}")
    df = pd.read_parquet(args.input)

    # Add normalized columns
    normalized_data = []
    for idx, row in df.iterrows():
        if idx % 100 == 0:
            print(f"Processing essay {idx}/{len(df)}")

        norm_result = await normalize_essay(row["essay"], normalizer)
        normalized_data.append(norm_result)

    # Add results to dataframe
    for key in normalized_data[0].keys():
        df[key] = [d[key] for d in normalized_data]

    # Save output
    print(f"Writing {args.output}")
    df.to_parquet(args.output)
    print(f"Done! Normalized {len(df)} essays")


if __name__ == "__main__":
    asyncio.run(main())