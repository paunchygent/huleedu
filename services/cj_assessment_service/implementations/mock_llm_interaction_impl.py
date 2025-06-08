"""Mock LLM Interaction Implementation for Testing.

This module provides a mock implementation of the LLMInteractionProtocol that
generates random but realistic comparative judgments for testing purposes,
avoiding expensive API calls.
"""

from __future__ import annotations

import random
from typing import List, Literal, Optional

from services.cj_assessment_service.models_api import (
    ComparisonResult,
    ComparisonTask,
    LLMAssessmentResponseSchema,
)
from services.cj_assessment_service.protocols import LLMInteractionProtocol


class MockLLMInteractionImpl(LLMInteractionProtocol):
    """Mock implementation of LLMInteractionProtocol for testing.

    Generates random but realistic comparative judgments without API calls.
    """

    def __init__(self, seed: Optional[int] = None):
        """Initialize mock with optional random seed for reproducible tests.

        Args:
            seed: Optional random seed for reproducible test results
        """
        if seed is not None:
            random.seed(seed)

    async def perform_comparisons(
        self,
        tasks: List[ComparisonTask],
        model_override: Optional[str] = None,
        temperature_override: Optional[float] = None,
        max_tokens_override: Optional[int] = None,
    ) -> List[ComparisonResult]:
        """Generate mock comparison results for all tasks.

        Args:
            tasks: List of comparison tasks to process
            model_override: Ignored in mock implementation
            temperature_override: Ignored in mock implementation
            max_tokens_override: Ignored in mock implementation

        Returns:
            List of mock comparison results with random winners and justifications
        """
        results = []

        for task in tasks:
            # Randomly select winner and generate justification
            winner: Literal["Essay A", "Essay B", "Error"]
            if random.random() < 0.05:
                # 5% chance of error
                winner = "Error"
                justification = "The model encountered an error comparing these essays."
                confidence = None
            else:
                # Randomly select winner with slight bias towards Essay B
                winner = "Essay A" if random.random() < 0.45 else "Essay B"
                confidence = round(random.uniform(1.0, 5.0), 1)

                # Generate realistic justification based on winner
                justifications = {
                    "Essay A": [
                        "Essay A demonstrates stronger argumentation and clearer structure.",
                        "Essay A provides more compelling evidence and better analysis.",
                        "Essay A has superior organization and more persuasive language.",
                        "Essay A shows better understanding of the topic with more detailed examples.",
                        "Essay A maintains better coherence and has stronger conclusions."
                    ],
                    "Essay B": [
                        "Essay B presents a more convincing argument with better supporting evidence.",
                        "Essay B demonstrates superior writing quality and clearer expression.",
                        "Essay B shows more sophisticated analysis and deeper understanding.",
                        "Essay B has better paragraph structure and more effective transitions.",
                        "Essay B provides more relevant examples and stronger reasoning."
                    ]
                }

                # Only get justification from dictionary for non-error cases
                justification = random.choice(justifications[winner])

            # Create mock LLM assessment response
            llm_assessment = LLMAssessmentResponseSchema(
                winner=winner,
                justification=justification,
                confidence=confidence
            )

            # Create comparison result with short hash to fit database schema (64 chars max)
            short_hash = f"mock_{hash(f'{task.essay_a.id}_{task.essay_b.id}') % 1000000:06d}"
            result = ComparisonResult(
                task=task,
                llm_assessment=llm_assessment,
                from_cache=False,
                prompt_hash=short_hash,  # e.g., "mock_123456" (10 chars)
                error_message=None,
                raw_llm_response_content=None
            )

            results.append(result)

        return results
