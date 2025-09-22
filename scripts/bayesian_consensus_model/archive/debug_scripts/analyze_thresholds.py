"""Analyze the threshold calculation mechanism."""

import numpy as np

def analyze_empirical_thresholds():
    """Analyze how empirical thresholds work for JA24 case."""

    # JA24 has grades: B(4) and A(5)
    grades = np.array([5, 5, 5, 5, 5, 4, 4])  # 5 As, 2 Bs
    n_categories = 6  # F(0), E(1), D(2), C(3), B(4), A(5)

    print("EMPIRICAL THRESHOLD ANALYSIS FOR JA24")
    print("=" * 50)
    print(f"Input grades (numeric): {grades}")
    print(f"Min grade: {grades.min()} (B)")
    print(f"Max grade: {grades.max()} (A)")
    print(f"Mean grade: {grades.mean():.2f}")

    # Replicate the _get_empirical_thresholds logic
    min_grade = int(np.min(grades))  # 4 (B)
    max_grade = int(np.max(grades))  # 5 (A)

    print(f"\nThreshold calculation logic:")
    print(f"min_grade = {min_grade}, max_grade = {max_grade}")

    thresholds = []
    observed_range = max_grade - min_grade  # 1
    spacing = 2.0 / (observed_range + 1)  # 2.0 / 2 = 1.0

    print(f"observed_range = {observed_range}")
    print(f"spacing = {spacing}")

    for i in range(n_categories - 1):  # i = 0, 1, 2, 3, 4
        if i < min_grade:  # i < 4: i = 0, 1, 2, 3
            # Below observed range - use tight spacing
            val = -2.0 - (min_grade - i - 1) * 0.3
            logic = f"Below range: -2.0 - ({min_grade} - {i} - 1) * 0.3"
        elif i >= max_grade:  # i >= 5: never true since max i = 4
            # Above observed range - use tight spacing
            val = 1.0 + (i - max_grade + 1) * 0.3
            logic = f"Above range: 1.0 + ({i} - {max_grade} + 1) * 0.3"
        else:  # i = 4 (between min and max)
            # Within observed range - use wider spacing
            position = (i - min_grade + 1) / (observed_range + 1)
            val = -1.0 + position * 2.0
            logic = f"Within range: -1.0 + {position:.2f} * 2.0"

        thresholds.append(val)
        print(f"  Threshold {i}: {val:.2f} ({logic})")

    thresholds = np.array(thresholds)
    print(f"\nFinal thresholds: {thresholds}")

    # Show what grades each range maps to
    print("\nGrade ranges with thresholds:")
    extended = np.concatenate([[-np.inf], thresholds, [np.inf]])
    grades_list = ['F', 'E', 'D', 'C', 'B', 'A']
    for i, grade in enumerate(grades_list):
        print(f"  {grade}: ({extended[i]:6.2f}, {extended[i+1]:6.2f}]")

    # Test with an ability value of 0 (neutral)
    print("\nWith ability = 0 (neutral):")
    ability = 0
    for i, grade in enumerate(grades_list):
        in_range = extended[i] < ability <= extended[i+1]
        marker = " <-- Selected" if in_range else ""
        print(f"  {grade}: {in_range}{marker}")

    # The problem: the thresholds heavily favor lower grades for sparse data!
    print("\nPROBLEM IDENTIFIED:")
    print("The empirical thresholds push B and A thresholds to the positive side,")
    print("making lower grades (C, D, E) more likely for neutral abilities!")

if __name__ == "__main__":
    analyze_empirical_thresholds()