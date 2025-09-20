#!/usr/bin/env python3
"""Test the enhanced whitelist on 100 essays to verify improvements."""

import pandas as pd
from pathlib import Path

# First, create a 100-essay test sample
input_file = Path("data/cefr_ielts_datasets/IELTS-writing-task-2-evaluation/processed/train.parquet")
df = pd.read_parquet(input_file)

# Take 100 essays
sample_df = df.head(100)

# Check for presence of our test terms in the original essays
test_terms = ['UK', 'USA', 'EU', 'UN', 'COVID', 'CVs', 'CV', 'PhD', 'MSc', 'BSc']
essays_with_terms = {}

print("=== Checking for test terms in 100 essays ===\n")
for term in test_terms:
    count = 0
    examples = []
    for idx, row in sample_df.iterrows():
        if term in row["essay"] or term.lower() in row["essay"].lower():
            count += 1
            if len(examples) < 2:  # Collect first 2 examples
                # Find the context
                essay = row["essay"]
                pos = essay.lower().find(term.lower())
                if pos != -1:
                    start = max(0, pos - 30)
                    end = min(len(essay), pos + len(term) + 30)
                    context = essay[start:end]
                    examples.append((idx, context))

    if count > 0:
        essays_with_terms[term] = {'count': count, 'examples': examples}
        print(f"{term}: Found in {count} essays")
        for idx, context in examples:
            print(f"  Essay {idx}: ...{context}...")

# Save sample for testing
sample_path = Path("data/cefr_ielts_datasets/IELTS-writing-task-2-evaluation/processed/test_100_essays.parquet")
sample_df.to_parquet(sample_path)

print(f"\nCreated test sample: {sample_path}")
print(f"Total essays: {len(sample_df)}")
print(f"Total words: {sum(len(essay.split()) for essay in sample_df['essay']):,}")

if not essays_with_terms:
    print("\n⚠️ WARNING: None of our test abbreviations found in this sample!")
    print("Searching for other abbreviations that might be affected...")

    # Check for any all-caps abbreviations
    import re
    abbr_pattern = re.compile(r'\b[A-Z]{2,6}\b')

    all_abbrs = set()
    for essay in sample_df['essay']:
        found = abbr_pattern.findall(essay)
        all_abbrs.update(found)

    if all_abbrs:
        print(f"Found these abbreviations: {sorted(all_abbrs)[:20]}")