#!/usr/bin/env python3
"""Verify that enhanced whitelist preserves critical abbreviations."""

import pandas as pd
from pathlib import Path

# Load normalized output
normalized = pd.read_parquet("data/cefr_ielts_datasets/IELTS-writing-task-2-evaluation/processed/test_100_normalized_enhanced.parquet")

print("=== Verification of Abbreviation Preservation ===\n")

# Critical test cases
test_cases = [
    (0, "CVs", "First essay had 'CVs' which was incorrectly corrected to 'Cos' before"),
    (0, "CV", "Also check singular CV"),
    (5, "cv", "Essay 5 has lowercase 'cv'"),
    (63, "USA", "Essay 63 mentions USA (usage volume)"),
    (38, "EU", "Essay 38 mentions entrepreneurs (EU)"),
]

print("Checking specific essays for preservation:\n")

for essay_idx, term, description in test_cases:
    original = normalized.iloc[essay_idx]["essay"]
    corrected = normalized.iloc[essay_idx]["corrected_text"]

    # Check if term exists in both
    in_original = term in original or term.lower() in original.lower()
    in_corrected = term in corrected or term.lower() in corrected.lower()

    if in_original:
        if in_corrected:
            print(f"✅ Essay {essay_idx}: '{term}' PRESERVED")
            # Find context in corrected text
            pos = corrected.lower().find(term.lower())
            if pos != -1:
                context = corrected[max(0, pos-20):min(len(corrected), pos+len(term)+20)]
                print(f"   Context: ...{context}...")
        else:
            print(f"❌ Essay {essay_idx}: '{term}' was INCORRECTLY CORRECTED")
            # Try to find what it was changed to
            orig_words = original.split()
            corr_words = corrected.split()
            for o, c in zip(orig_words, corr_words):
                if term.lower() in o.lower() and term.lower() not in c.lower():
                    print(f"   Changed from '{o}' to '{c}'")
                    break
    else:
        print(f"⚠️ Essay {essay_idx}: '{term}' not found in original")

# Overall statistics comparison
print("\n=== Correction Statistics ===")
print(f"Total corrections: {normalized['total_corrections'].sum()}")
print(f"Average per essay: {normalized['total_corrections'].mean():.1f}")
print(f"L2 corrections: {normalized['l2_corrections'].sum()}")
print(f"Spell corrections: {normalized['spell_corrections'].sum()}")

# Find essays with the most reductions in corrections
print("\n=== Essays with Reduced Corrections ===")
# We'd need the old data to compare, but we can at least show which had few corrections
least_corrected = normalized.nsmallest(5, 'total_corrections')[['total_corrections', 'l2_corrections', 'spell_corrections']]
print("Essays with fewest corrections:")
for idx, row in least_corrected.iterrows():
    print(f"  Essay {idx}: {int(row['total_corrections'])} total ({int(row['l2_corrections'])} L2, {int(row['spell_corrections'])} spell)")

# Check for any remaining suspicious corrections
print("\n=== Checking for Suspicious Corrections ===")

suspicious_patterns = [
    ('CVs', 'Cos'),
    ('CV', 'TV'),
    ('USA', 'US'),
    ('UK', 'UP'),
    ('EU', 'en'),
    ('PhD', 'Phd'),
    ('MSc', 'Mac'),
]

for orig, bad_correction in suspicious_patterns:
    found = False
    for idx, row in normalized.iterrows():
        if bad_correction in row['corrected_text'] and bad_correction not in row['essay']:
            # Check if this might be our bad correction
            if orig in row['essay'] or orig.lower() in row['essay'].lower():
                print(f"⚠️ Essay {idx}: Possible bad correction '{orig}' → '{bad_correction}'")
                found = True
                break
    if not found:
        print(f"✅ No instances of '{orig}' → '{bad_correction}' found")