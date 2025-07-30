"""String similarity utilities for fuzzy matching.

This module provides helper functions for comparing strings using various
similarity algorithms from rapidfuzz.
"""

from __future__ import annotations

from rapidfuzz import fuzz
from rapidfuzz.distance import Levenshtein


def normalized_similarity(str1: str, str2: str) -> float:
    """Calculate normalized similarity between two strings.

    Uses token sort ratio which handles word order differences.

    Args:
        str1: First string to compare
        str2: Second string to compare

    Returns:
        Similarity score between 0.0 and 1.0
    """
    if not str1 or not str2:
        return 0.0

    # Use token_sort_ratio for better handling of name variations
    # e.g., "John Smith" vs "Smith, John"
    score = fuzz.token_sort_ratio(str1.lower(), str2.lower())
    return score / 100.0


def partial_similarity(str1: str, str2: str) -> float:
    """Calculate partial string similarity.

    Useful for finding if one string is contained within another.

    Args:
        str1: First string to compare
        str2: Second string to compare

    Returns:
        Similarity score between 0.0 and 1.0
    """
    if not str1 or not str2:
        return 0.0

    score = fuzz.partial_ratio(str1.lower(), str2.lower())
    return score / 100.0


def exact_match(str1: str, str2: str, case_sensitive: bool = False) -> bool:
    """Check if two strings are exactly equal.

    Args:
        str1: First string to compare
        str2: Second string to compare
        case_sensitive: Whether to consider case in comparison

    Returns:
        True if strings are exactly equal
    """
    if case_sensitive:
        return str1 == str2
    return str1.lower() == str2.lower()


def levenshtein_distance(str1: str, str2: str) -> int:
    """Calculate Levenshtein edit distance between two strings.

    Args:
        str1: First string to compare
        str2: Second string to compare

    Returns:
        Number of edits needed to transform str1 to str2
    """
    return int(Levenshtein.distance(str1, str2))


def similarity_with_threshold(
    str1: str,
    str2: str,
    threshold: float = 0.8,
    algorithm: str = "token_sort",
) -> tuple[bool, float]:
    """Check if similarity meets threshold and return score.

    Args:
        str1: First string to compare
        str2: Second string to compare
        threshold: Minimum similarity score (0.0 to 1.0)
        algorithm: Algorithm to use ("token_sort", "partial", "ratio")

    Returns:
        Tuple of (meets_threshold, similarity_score)
    """
    if not str1 or not str2:
        return False, 0.0

    if algorithm == "token_sort":
        score = fuzz.token_sort_ratio(str1.lower(), str2.lower()) / 100.0
    elif algorithm == "partial":
        score = fuzz.partial_ratio(str1.lower(), str2.lower()) / 100.0
    elif algorithm == "ratio":
        score = fuzz.ratio(str1.lower(), str2.lower()) / 100.0
    else:
        raise ValueError(f"Unknown algorithm: {algorithm}")

    return score >= threshold, score


def best_match_from_list(
    target: str,
    candidates: list[str],
    threshold: float = 0.0,
) -> tuple[str | None, float]:
    """Find the best matching string from a list of candidates.

    Args:
        target: String to match against
        candidates: List of candidate strings
        threshold: Minimum similarity score to consider a match

    Returns:
        Tuple of (best_match, similarity_score) or (None, 0.0) if no match
    """
    if not target or not candidates:
        return None, 0.0

    best_match = None
    best_score = 0.0

    for candidate in candidates:
        score = normalized_similarity(target, candidate)
        if score > best_score and score >= threshold:
            best_score = score
            best_match = candidate

    return best_match, best_score
