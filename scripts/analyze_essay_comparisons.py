#!/usr/bin/env python3
"""
Analyze essay comparison counts in session2_dynamic_assignments.csv
"""

import csv
from collections import defaultdict


def analyze_essay_comparisons(csv_file):
    # Count comparisons for each essay
    essay_counts = defaultdict(int)

    # Read the CSV file
    with open(csv_file, "r", encoding="utf-8") as file:
        reader = csv.DictReader(file)

        # Count essay_a_id and essay_b_id appearances
        for row in reader:
            essay_counts[row["essay_a_id"]] += 1
            essay_counts[row["essay_b_id"]] += 1

    # Sort by essay ID
    sorted_essays = sorted(essay_counts.items())

    # Calculate statistics
    total_comparisons = sum(essay_counts.values())
    unique_essays = len(essay_counts)
    avg_comparisons = total_comparisons / unique_essays

    print("Essay Comparison Analysis")
    print("=" * 50)
    print(f"Total comparisons: {total_comparisons}")
    print(f"Unique essays: {unique_essays}")
    print(f"Average comparisons per essay: {avg_comparisons:.2f}")
    print()

    print("Comparison count per essay:")
    print("-" * 30)
    for essay_id, count in sorted_essays:
        print(f"{essay_id}: {count}")

    print()

    # Show distribution
    count_distribution = defaultdict(int)
    for count in essay_counts.values():
        count_distribution[count] += 1

    print("Distribution of comparison counts:")
    print("-" * 35)
    for count in sorted(count_distribution.keys()):
        essays_with_count = count_distribution[count]
        print(f"{count} comparisons: {essays_with_count} essays")

    return essay_counts


if __name__ == "__main__":
    analyze_essay_comparisons("session2_dynamic_assignments.csv")
