#!/usr/bin/env python3
"""
Extract names from cross-verified database for spell checker whitelist.

This script processes the cross-verified-database.csv.gz file and extracts
unique person names to create a whitelist for the spell checker.
"""

import csv
import gzip
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def extract_names_from_database():
    """Extract unique names from the cross-verified database."""
    # Paths
    data_dir = Path(__file__).parent.parent / "data"
    input_file = data_dir / "cross-verified-database.csv.gz"
    output_file = data_dir / "whitelist" / "notable_people.txt"

    # Ensure output directory exists
    output_file.parent.mkdir(parents=True, exist_ok=True)

    names = set()
    row_count = 0

    logger.info(f"Processing {input_file}")

    with gzip.open(input_file, "rt", encoding="utf-8", errors="ignore") as f:
        reader = csv.DictReader(f)

        for row in reader:
            row_count += 1

            # Extract name field
            name = row.get("name", "").strip()
            if name:
                # Clean up the name
                # Replace underscores with spaces (Wikipedia format)
                name = name.replace("_", " ")

                # Add the full name
                names.add(name)

                # Also add individual parts (first name, last name)
                parts = name.split()
                for part in parts:
                    # Skip very short parts (likely initials or articles)
                    if len(part) > 2:
                        names.add(part)

            # Progress indicator
            if row_count % 10000 == 0:
                logger.info(f"Processed {row_count:,} rows, found {len(names):,} unique names")

    logger.info(f"Total rows processed: {row_count:,}")
    logger.info(f"Total unique names extracted: {len(names):,}")

    # Write to file
    logger.info(f"Writing names to {output_file}")
    with open(output_file, "w", encoding="utf-8") as f:
        for name in sorted(names):
            # Write each name on a new line
            f.write(f"{name}\n")

    logger.info(f"Successfully wrote {len(names):,} names to {output_file}")

    # Also create a lowercase version for case-insensitive matching
    lowercase_file = output_file.parent / "notable_people_lowercase.txt"
    logger.info(f"Creating lowercase version at {lowercase_file}")

    lowercase_names = {name.lower() for name in names}
    with open(lowercase_file, "w", encoding="utf-8") as f:
        for name in sorted(lowercase_names):
            f.write(f"{name}\n")

    logger.info(f"Successfully wrote {len(lowercase_names):,} lowercase names")

    return names


def create_combined_whitelist():
    """Combine multiple whitelist sources into a single file."""
    data_dir = Path(__file__).parent.parent / "data"
    whitelist_dir = data_dir / "whitelist"

    # Files to combine (add more as needed)
    source_files = [
        whitelist_dir / "notable_people_lowercase.txt",
        # Add Swedish names file here when available
        # Add common first names file here when available
    ]

    combined_names = set()

    for source_file in source_files:
        if source_file.exists():
            logger.info(f"Adding names from {source_file}")
            with open(source_file, "r", encoding="utf-8") as f:
                for line in f:
                    name = line.strip()
                    if name:
                        combined_names.add(name)
            logger.info(f"Added {len(combined_names):,} names so far")

    # Write combined whitelist
    combined_file = whitelist_dir / "combined_whitelist.txt"
    logger.info(f"Writing combined whitelist to {combined_file}")

    with open(combined_file, "w", encoding="utf-8") as f:
        for name in sorted(combined_names):
            f.write(f"{name}\n")

    logger.info(f"Total unique names in combined whitelist: {len(combined_names):,}")

    # Print some statistics
    logger.info("\nWhitelist Statistics:")
    logger.info(f"  Total entries: {len(combined_names):,}")
    logger.info(f"  Estimated memory usage: ~{len(combined_names) * 50 / 1024 / 1024:.1f} MB")

    # Sample some names for verification
    sample = list(sorted(combined_names))[:20]
    logger.info("\nFirst 20 entries (alphabetical):")
    for name in sample:
        logger.info(f"  - {name}")


if __name__ == "__main__":
    # Extract names from cross-verified database
    names = extract_names_from_database()

    # Create combined whitelist
    create_combined_whitelist()
