"""Optimal graph-based matching strategy for comparative judgment waves.

Uses NetworkX's maximum weight matching (Blossom algorithm) to compute
maximum-weight perfect matchings where each essay appears in exactly one
comparison per wave.
"""

from __future__ import annotations

from collections.abc import Sequence
from math import exp
from random import Random

import networkx as nx
from huleedu_service_libs.logging_utils import create_service_logger

from services.cj_assessment_service.models_api import EssayForComparison

logger = create_service_logger("cj_assessment_service.optimal_graph_matching")


class OptimalGraphMatchingStrategy:
    """Graph-based optimal matching using Blossom algorithm.

    Implements PairMatchingStrategyProtocol for DI injection.

    Information gain heuristic:
    - Higher weight if both essays have low comparison_count (fairness)
    - Bonus if BT scores are close (more discriminative comparison)
    - Zero (excluded) if pair already compared
    """

    def __init__(
        self,
        weight_comparison_count: float = 1.0,
        weight_bt_proximity: float = 0.5,
    ) -> None:
        """Initialize strategy with configurable weights.

        Args:
            weight_comparison_count: Weight for comparison count fairness term
            weight_bt_proximity: Weight for BT score proximity term
        """
        self._weight_count = weight_comparison_count
        self._weight_proximity = weight_bt_proximity

    def compute_wave_pairs(
        self,
        essays: Sequence[EssayForComparison],
        existing_pairs: set[tuple[str, str]],
        comparison_counts: dict[str, int],
        randomization_seed: int | None = None,
    ) -> list[tuple[EssayForComparison, EssayForComparison]]:
        """Compute optimal matching where each essay appears in exactly one pair.

        Uses NetworkX's max_weight_matching (Blossom algorithm) to find a
        maximum-weight perfect matching on the essay graph.

        Args:
            essays: Essays to match (should be even count; use handle_odd_count first)
            existing_pairs: Set of (essay_a_id, essay_b_id) tuples already compared
            comparison_counts: Dict mapping essay_id -> comparison count
            randomization_seed: Seed for tie-breaking randomization

        Returns:
            List of (essay_a, essay_b) tuples representing the optimal matching.
            Each essay appears exactly once. Returns exactly len(essays)//2 pairs.
        """
        essays_list = list(essays)
        n = len(essays_list)
        if n < 2:
            return []

        # Build weighted graph
        graph = self._build_weighted_graph(
            essays=essays_list,
            existing_pairs=existing_pairs,
            comparison_counts=comparison_counts,
            randomization_seed=randomization_seed,
        )

        # Find maximum weight matching using Blossom algorithm
        # maxcardinality=True ensures we get the maximum number of pairs
        matching = nx.max_weight_matching(graph, maxcardinality=True)

        # Convert matching to list of essay pairs
        # matching returns frozenset of (node_i, node_j) pairs
        id_to_essay = {e.id: e for e in essays_list}
        matched_pairs: list[tuple[EssayForComparison, EssayForComparison]] = []

        for node_a, node_b in matching:
            essay_a = id_to_essay[node_a]
            essay_b = id_to_essay[node_b]
            matched_pairs.append((essay_a, essay_b))

        logger.info(
            "Computed optimal matching",
            extra={
                "n_essays": n,
                "n_pairs": len(matched_pairs),
                "n_existing_pairs": len(existing_pairs),
                "expected_pairs": n // 2,
            },
        )

        return matched_pairs

    def compute_wave_size(self, n_essays: int) -> int:
        """Return expected wave size for given essay count.

        Args:
            n_essays: Total number of essays in batch

        Returns:
            Number of pairs per wave (n_essays // 2)
        """
        return n_essays // 2

    def handle_odd_count(
        self,
        essays: Sequence[EssayForComparison],
        comparison_counts: dict[str, int],
    ) -> tuple[list[EssayForComparison], EssayForComparison | None]:
        """Remove essay with highest comparison count if count is odd.

        Args:
            essays: List of essays to filter
            comparison_counts: Dict mapping essay_id -> comparison count

        Returns:
            Tuple of (filtered_essays, excluded_essay or None)
        """
        essays_list = list(essays)
        if len(essays_list) % 2 == 0:
            return essays_list, None

        # Find essay with highest comparison count (lowest priority for new comparisons)
        essays_with_counts = [(e, comparison_counts.get(e.id, 0)) for e in essays_list]

        # Sort by comparison count descending, then by id for determinism
        essays_with_counts.sort(key=lambda x: (-x[1], x[0].id))

        excluded = essays_with_counts[0][0]
        filtered = [e for e, _ in essays_with_counts[1:]]

        logger.info(
            "Excluded lowest priority essay for odd count",
            extra={
                "excluded_essay_id": excluded.id,
                "excluded_comparison_count": comparison_counts.get(excluded.id, 0),
                "original_count": len(essays_list),
                "filtered_count": len(filtered),
            },
        )

        return filtered, excluded

    def _build_weighted_graph(
        self,
        essays: list[EssayForComparison],
        existing_pairs: set[tuple[str, str]],
        comparison_counts: dict[str, int],
        randomization_seed: int | None,
    ) -> nx.Graph:
        """Build weighted graph for maximum matching.

        Each essay is a node, edges represent potential comparisons with weights
        based on information gain heuristic.

        Args:
            essays: List of essays
            existing_pairs: Set of already-compared pairs to exclude
            comparison_counts: Dict mapping essay_id -> comparison count
            randomization_seed: Seed for tie-breaking jitter

        Returns:
            NetworkX Graph with weighted edges
        """
        graph = nx.Graph()

        # Add all essays as nodes
        for essay in essays:
            graph.add_node(essay.id)

        # Initialize RNG for tie-breaking
        rng = Random(randomization_seed)

        # Add weighted edges between all pairs (except existing ones)
        for i, essay_i in enumerate(essays):
            for j in range(i + 1, len(essays)):
                essay_j = essays[j]

                # Check if pair already exists - skip if so
                pair_key = tuple(sorted((essay_i.id, essay_j.id)))
                if pair_key in existing_pairs:
                    continue

                # Fairness score: prioritize essays with fewer comparisons
                count_i = comparison_counts.get(essay_i.id, 0)
                count_j = comparison_counts.get(essay_j.id, 0)
                fairness_score = 1.0 / (1.0 + count_i) + 1.0 / (1.0 + count_j)

                # BT proximity bonus: more discriminative when scores are close
                bt_i = essay_i.current_bt_score or 0.0
                bt_j = essay_j.current_bt_score or 0.0
                bt_diff = abs(bt_i - bt_j)
                proximity_bonus = exp(-bt_diff) if bt_diff < 2.0 else 0.0

                # Combined weight with small random jitter for tie-breaking
                jitter = rng.uniform(0, 0.001)
                weight = (
                    self._weight_count * fairness_score
                    + self._weight_proximity * proximity_bonus
                    + jitter
                )

                graph.add_edge(essay_i.id, essay_j.id, weight=weight)

        return graph
