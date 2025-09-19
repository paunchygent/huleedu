#!/usr/bin/env python3
"""Extract a small sample of IELTS data for testing normalization."""

import pandas as pd
from pathlib import Path

# Read full dataset
input_file = Path("data/cefr_ielts_datasets/IELTS-writing-task-2-evaluation/processed/train.parquet")
df = pd.read_parquet(input_file)

# Take first 5 rows for quick testing
sample_df = df.head(5)

# Save sample
output_file = Path("data/cefr_ielts_datasets/IELTS-writing-task-2-evaluation/processed/test_sample.parquet")
sample_df.to_parquet(output_file)

print(f"Created test sample with {len(sample_df)} essays")
print(f"Saved to: {output_file}")
print("\nFirst essay preview:")
print(sample_df.iloc[0]["essay"][:200] + "...")