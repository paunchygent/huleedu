"""Domain service for calculating pipeline resource requirements."""

from dataclasses import dataclass
from typing import Any

from common_core.pipeline_models import PhaseName


@dataclass
class ResourceRequirements:
    """Resource requirements for pipeline execution."""

    cj_comparisons: int = 0
    ai_feedback_calls: int = 0

    def to_entitlement_checks(self) -> list[tuple[str, int]]:
        """Convert to entitlement check requests.

        Returns:
            List of (metric_name, quantity) tuples for entitlements service
        """
        checks = []
        if self.cj_comparisons > 0:
            checks.append(("cj_comparison", self.cj_comparisons))
        if self.ai_feedback_calls > 0:
            checks.append(("ai_feedback_generation", self.ai_feedback_calls))
        return checks

    @property
    def total_cost_units(self) -> int:
        """Calculate total resource units required."""
        return self.cj_comparisons + self.ai_feedback_calls

    def has_billable_resources(self) -> bool:
        """Check if this pipeline requires any billable resources."""
        return self.total_cost_units > 0


class PipelineCostStrategy:
    """Domain service for calculating pipeline resource requirements.

    Implements the business logic for resource-based pricing where credits
    map to actual LLM API calls, not arbitrary units like batches or essays.
    """

    def calculate_requirements(
        self,
        pipeline_steps: list[str],  # From BCS resolution
        essay_count: int,  # From batch data
        batch_context: Any = None,  # For future extensibility
    ) -> ResourceRequirements:
        """Calculate resource requirements for pipeline execution.

        Args:
            pipeline_steps: List of phase names from BCS pipeline resolution
            essay_count: Number of essays in the batch
            batch_context: Additional context for calculations (unused currently)

        Returns:
            ResourceRequirements with calculated resource needs
        """
        reqs = ResourceRequirements()

        for step in pipeline_steps:
            if step == PhaseName.CJ_ASSESSMENT.value:
                # Full pairwise comparisons - what CJ actually does
                # For n essays: n*(n-1)/2 comparisons
                reqs.cj_comparisons = essay_count * (essay_count - 1) // 2

            elif step == PhaseName.AI_FEEDBACK.value:
                # Linear: one API call per essay for AI feedback generation
                reqs.ai_feedback_calls = essay_count

            # spellcheck, nlp, batch_create = free internal processing (cost = 0)

        return reqs

    def calculate_cj_comparisons(self, essay_count: int) -> int:
        """Calculate number of pairwise comparisons for CJ assessment.

        Args:
            essay_count: Number of essays to compare

        Returns:
            Number of required comparisons (n*(n-1)/2)
        """
        if essay_count < 2:
            return 0
        return essay_count * (essay_count - 1) // 2

    def calculate_ai_feedback_calls(self, essay_count: int) -> int:
        """Calculate number of AI API calls needed for feedback generation.

        Args:
            essay_count: Number of essays needing feedback

        Returns:
            Number of API calls (linear: 1 per essay)
        """
        return max(0, essay_count)
