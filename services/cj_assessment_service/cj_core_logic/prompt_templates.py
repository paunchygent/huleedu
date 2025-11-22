"""Prompt template builder for cache-friendly prompt composition.

This module implements template-based prompt composition that separates
static (cacheable) content from dynamic (essay-specific) content to maximize
Anthropic prompt cache reuse during CJ backfilling operations.

Architecture:
- Static blocks: Assessment context (student prompt, instructions, rubric)
- Dynamic blocks: Essay pairs (vary per comparison)
- Response instructions: Standardized footer (service-level constant)

The template builder produces PromptBlock instances that the LLM Provider Service
transforms into Anthropic-specific API format with cache_control annotations.
"""

from services.cj_assessment_service.models_api import EssayForComparison
from services.cj_assessment_service.models_prompt import (
    AnthropicCacheTTL,
    CacheableBlockTarget,
    PromptBlock,
    PromptBlockList,
)

# Service-level constant: Standardized response instructions
# This text is identical across all CJ comparisons, making it ideal for caching
_RESPONSE_INSTRUCTIONS = (
    "Using the Student Assignment, Assessment Criteria, and Judge Instructions above, "
    "determine which essay better fulfills the requirements. Respond with JSON indicating "
    "the `winner` ('Essay A' or 'Essay B'), a brief `justification`, and a `confidence` "
    "rating from 1-5 (5 = very confident). Provide a decisive judgment."
)


class PromptTemplateBuilder:
    """Builder for cache-friendly CJ comparison prompts.

    Static Methods:
        build_static_blocks: Create cacheable blocks from assessment context
        render_dynamic_essays: Create non-cacheable essay blocks
        assemble_full_prompt: Combine static + dynamic blocks with TTL ordering
    """

    @staticmethod
    def build_static_blocks(
        assessment_context: dict[str, str | None],
        use_extended_ttl: bool = False,
    ) -> list[PromptBlock]:
        """Build cacheable static blocks from assessment context.

        Creates prompt blocks for assignment-level content that remains stable
        across all comparisons within the same assignment. These blocks are
        marked as cacheable and will be sent with cache_control to Anthropic.

        Args:
            assessment_context: Dictionary with keys:
                - student_prompt_text: Original student assignment prompt
                - assessment_instructions: Teacher-provided assessment criteria
                - judge_rubric_text: Detailed evaluation rubric
            use_extended_ttl: If True, use 1h TTL; otherwise use 5m (default)

        Returns:
            List of PromptBlock instances representing static content.
            Empty if all context fields are None.

        Note:
            Blocks are returned in order that supports TTL requirements
            (all 1h before all 5m, though typically all use same TTL).
        """
        blocks = []
        ttl = AnthropicCacheTTL.ONE_HOUR if use_extended_ttl else AnthropicCacheTTL.FIVE_MIN

        # Build assignment context as a single cacheable block
        context_parts = []

        if assessment_context.get("student_prompt_text"):
            context_parts.append(
                f"**Student Assignment:**\n{assessment_context['student_prompt_text']}"
            )

        if assessment_context.get("assessment_instructions"):
            context_parts.append(
                f"**Assessment Criteria:**\n{assessment_context['assessment_instructions']}"
            )

        if assessment_context.get("judge_rubric_text"):
            context_parts.append(
                f"**Judge Instructions:**\n{assessment_context['judge_rubric_text']}"
            )

        # Only create block if we have actual content
        if context_parts:
            context_text = "\n\n".join(context_parts)
            blocks.append(
                PromptBlock(
                    target=CacheableBlockTarget.USER_CONTENT,
                    content=context_text,
                    cacheable=True,
                    ttl=ttl,
                )
            )

        return blocks

    @staticmethod
    def render_dynamic_essays(
        essay_a: EssayForComparison,
        essay_b: EssayForComparison,
    ) -> list[PromptBlock]:
        """Build non-cacheable essay blocks.

        Creates prompt blocks for essay content that varies with each comparison.
        These blocks are NOT marked as cacheable since essay pairs change per request.

        Args:
            essay_a: First essay for comparison
            essay_b: Second essay for comparison

        Returns:
            List of 2 PromptBlock instances (Essay A, Essay B)
        """
        return [
            PromptBlock(
                target=CacheableBlockTarget.USER_CONTENT,
                content=f"**Essay A (ID: {essay_a.id}):**\n{essay_a.text_content}",
                cacheable=False,
            ),
            PromptBlock(
                target=CacheableBlockTarget.USER_CONTENT,
                content=f"**Essay B (ID: {essay_b.id}):**\n{essay_b.text_content}",
                cacheable=False,
            ),
        ]

    @staticmethod
    def build_response_instructions_block(use_extended_ttl: bool = False) -> PromptBlock:
        """Build response instructions block.

        Creates a cacheable block with standardized response instructions.
        This is a service-level constant that never varies.

        Args:
            use_extended_ttl: If True, use 1h TTL; otherwise use 5m (default)

        Returns:
            PromptBlock with response instructions
        """
        ttl = AnthropicCacheTTL.ONE_HOUR if use_extended_ttl else AnthropicCacheTTL.FIVE_MIN
        return PromptBlock(
            target=CacheableBlockTarget.USER_CONTENT,
            content=_RESPONSE_INSTRUCTIONS,
            cacheable=True,
            ttl=ttl,
        )

    @staticmethod
    def assemble_full_prompt(
        assessment_context: dict[str, str | None],
        essay_a: EssayForComparison,
        essay_b: EssayForComparison,
        use_extended_ttl: bool = False,
    ) -> PromptBlockList:
        """Assemble complete prompt with static and dynamic blocks.

        This is the primary entry point for generating a comparison prompt.
        It combines cacheable static content with dynamic essay content,
        ensuring proper TTL ordering (1h before 5m if mixed).

        Args:
            assessment_context: Assignment-level context (student prompt, instructions, rubric)
            essay_a: First essay for comparison
            essay_b: Second essay for comparison
            use_extended_ttl: If True, use 1h TTL for static blocks; otherwise 5m

        Returns:
            PromptBlockList with all blocks in correct TTL order

        Raises:
            ValueError: If TTL ordering validation fails

        Example:
            >>> context = {
            ...     "student_prompt_text": "Write about summer",
            ...     "assessment_instructions": "Assess clarity",
            ...     "judge_rubric_text": "Prioritize coherence"
            ... }
            >>> essay_a = EssayForComparison(id="a1", text_content="Summer was fun.")
            >>> essay_b = EssayForComparison(id="b1", text_content="I went swimming.")
            >>> prompt_list = PromptTemplateBuilder.assemble_full_prompt(context, essay_a, essay_b)
            >>> len(prompt_list.blocks)
            4  # assessment context, essay A, essay B, response instructions
        """
        blocks = []

        # Add static assessment context (cacheable, TTL based on use_extended_ttl)
        static_blocks = PromptTemplateBuilder.build_static_blocks(
            assessment_context, use_extended_ttl
        )
        blocks.extend(static_blocks)

        # Add dynamic essays (non-cacheable)
        essay_blocks = PromptTemplateBuilder.render_dynamic_essays(essay_a, essay_b)
        blocks.extend(essay_blocks)

        # Add response instructions (cacheable, same TTL as static blocks)
        instructions_block = PromptTemplateBuilder.build_response_instructions_block(
            use_extended_ttl
        )
        blocks.append(instructions_block)

        # Create PromptBlockList and validate TTL ordering
        prompt_list = PromptBlockList(blocks=blocks)
        is_valid, error_msg = prompt_list.validate_ttl_ordering()
        if not is_valid:
            msg = f"TTL ordering violation: {error_msg}"
            raise ValueError(msg)

        return prompt_list
