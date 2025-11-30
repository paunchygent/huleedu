"""Test data builders for ENG5 NP runner tests.

Fluent builder pattern for constructing test objects with customizable fields.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class BTSummaryBuilder:
    """Fluent builder for Bradley-Terry summary entries.

    Usage:
        entry = BTSummaryBuilder().with_essay_id("anchor_001").with_theta(2.5).build()
    """

    essay_id: str = "student::essay_001"
    theta: float = 0.0
    rank: int = 1

    def with_essay_id(self, essay_id: str) -> BTSummaryBuilder:
        """Set the essay ID."""
        self.essay_id = essay_id
        return self

    def with_theta(self, theta: float) -> BTSummaryBuilder:
        """Set the BT theta score."""
        self.theta = theta
        return self

    def with_rank(self, rank: int) -> BTSummaryBuilder:
        """Set the rank position."""
        self.rank = rank
        return self

    def build(self) -> dict[str, Any]:
        """Build the BT summary entry dictionary."""
        return {
            "essay_id": self.essay_id,
            "theta": self.theta,
            "rank": self.rank,
        }


@dataclass
class ComparisonRecordBuilder:
    """Fluent builder for LLM comparison records.

    Usage:
        record = (ComparisonRecordBuilder()
            .with_winner("anchor_a")
            .with_loser("anchor_b")
            .with_confidence(4.0)
            .build())
    """

    winner_id: str = "student::essay_a"
    loser_id: str = "student::essay_b"
    confidence: float = 3.0
    justification: str = "Winner demonstrates better quality."
    status: str = "succeeded"

    def with_winner(self, winner_id: str) -> ComparisonRecordBuilder:
        """Set the winner essay ID."""
        self.winner_id = winner_id
        return self

    def with_loser(self, loser_id: str) -> ComparisonRecordBuilder:
        """Set the loser essay ID."""
        self.loser_id = loser_id
        return self

    def with_confidence(self, confidence: float) -> ComparisonRecordBuilder:
        """Set the confidence score (1-5)."""
        self.confidence = confidence
        return self

    def with_justification(self, justification: str) -> ComparisonRecordBuilder:
        """Set the justification text."""
        self.justification = justification
        return self

    def build(self) -> dict[str, Any]:
        """Build the comparison record dictionary."""
        return {
            "winner_id": self.winner_id,
            "loser_id": self.loser_id,
            "confidence": self.confidence,
            "justification": self.justification,
            "status": self.status,
        }


@dataclass
class AnchorResultBuilder:
    """Fluent builder for AnchorResult test data.

    Usage:
        result = AnchorResultBuilder().with_anchor_id("anchor_001").with_wins(5).build()
    """

    anchor_id: str = "anchor_001"
    expected_grade: str = "A"
    bt_score: float = 0.0
    actual_rank: int = 1
    expected_rank: int = 1
    wins: int = 0
    losses: int = 0

    def with_anchor_id(self, anchor_id: str) -> AnchorResultBuilder:
        """Set the anchor ID."""
        self.anchor_id = anchor_id
        return self

    def with_expected_grade(self, grade: str) -> AnchorResultBuilder:
        """Set the expected expert grade."""
        self.expected_grade = grade
        return self

    def with_bt_score(self, score: float) -> AnchorResultBuilder:
        """Set the Bradley-Terry score."""
        self.bt_score = score
        return self

    def with_actual_rank(self, rank: int) -> AnchorResultBuilder:
        """Set the actual rank from BT scoring."""
        self.actual_rank = rank
        return self

    def with_expected_rank(self, rank: int) -> AnchorResultBuilder:
        """Set the expected rank from grades."""
        self.expected_rank = rank
        return self

    def with_wins(self, wins: int) -> AnchorResultBuilder:
        """Set the number of comparison wins."""
        self.wins = wins
        return self

    def with_losses(self, losses: int) -> AnchorResultBuilder:
        """Set the number of comparison losses."""
        self.losses = losses
        return self

    def build(self) -> dict[str, Any]:
        """Build the anchor result dictionary."""
        total = self.wins + self.losses
        win_rate = self.wins / total if total > 0 else 0.0
        return {
            "anchor_id": self.anchor_id,
            "expected_grade": self.expected_grade,
            "bt_score": self.bt_score,
            "actual_rank": self.actual_rank,
            "expected_rank": self.expected_rank,
            "wins": self.wins,
            "losses": self.losses,
            "win_rate": win_rate,
        }


def build_bt_summary_list(anchor_count: int = 12) -> list[dict[str, Any]]:
    """Build a list of BT summary entries with descending scores.

    Args:
        anchor_count: Number of anchors to generate

    Returns:
        List of BT summary dictionaries
    """
    entries = []
    for i in range(anchor_count):
        entry = (
            BTSummaryBuilder()
            .with_essay_id(f"student::anchor_{i + 1:03d}")
            .with_theta(3.0 - (i * 0.5))
            .with_rank(i + 1)
            .build()
        )
        entries.append(entry)
    return entries


def build_round_robin_comparisons(
    anchor_ids: list[str],
    winner_fn: callable = None,
) -> list[dict[str, Any]]:
    """Build round-robin comparison records.

    Args:
        anchor_ids: List of anchor IDs to compare
        winner_fn: Optional function(id_a, id_b) -> winner_id

    Returns:
        List of comparison records covering all pairs
    """
    comparisons = []
    for i, id_a in enumerate(anchor_ids):
        for id_b in anchor_ids[i + 1 :]:
            if winner_fn:
                winner = winner_fn(id_a, id_b)
            else:
                winner = id_a  # Default: first essay wins

            record = (
                ComparisonRecordBuilder()
                .with_winner(winner)
                .with_loser(id_b if winner == id_a else id_a)
                .with_confidence(3.5)
                .build()
            )
            comparisons.append(record)
    return comparisons
