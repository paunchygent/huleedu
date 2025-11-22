"""Prompt block models for cache-friendly prompt composition.

This module defines the data structures used by the PromptTemplateBuilder
to create multi-block prompts with selective caching for Anthropic's
prompt caching API.
"""

import hashlib
from enum import StrEnum

from pydantic import BaseModel, Field


class CacheableBlockTarget(StrEnum):
    """Target location for prompt block in Anthropic API request.

    SYSTEM: Placed in the system array (service-level instructions)
    USER_CONTENT: Placed in messages[0].content array (user prompt blocks)
    """

    SYSTEM = "system"
    USER_CONTENT = "user_content"


class AnthropicCacheTTL(StrEnum):
    """Valid Anthropic cache TTL values.

    Anthropic's prompt caching API only supports two TTL durations:
    - "5m": 5-minute cache (default), write cost 1.25x base input
    - "1h": 1-hour cache (extended), write cost 2x base input

    Cache reads: 0.1x base input cost (90% savings)

    Reference: https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching
    """

    FIVE_MIN = "5m"
    ONE_HOUR = "1h"


class PromptBlock(BaseModel):
    """Single prompt block with optional caching metadata.

    Represents a segment of the prompt that can be independently cached
    by Anthropic's prompt caching system.

    Attributes:
        target: Where this block will be placed in the API request
        content: The actual text content of this block
        cacheable: Whether to mark this block with cache_control
        ttl: Cache duration (only "5m" or "1h" allowed by Anthropic)
        content_hash: SHA256 hash for internal deduplication tracking
            (not sent to API, used for fragmentation monitoring)
    """

    target: CacheableBlockTarget
    content: str
    cacheable: bool = False
    ttl: AnthropicCacheTTL = AnthropicCacheTTL.FIVE_MIN
    content_hash: str | None = Field(
        default=None, description="SHA256 hash for deduplication tracking"
    )

    def compute_hash(self) -> str:
        """Compute SHA256 hash of content for cache key tracking.

        Returns:
            Hexadecimal SHA256 hash of content
        """
        return hashlib.sha256(self.content.encode("utf-8")).hexdigest()

    def model_post_init(self, __context: object) -> None:
        """Compute content hash if not provided."""
        if self.content_hash is None:
            self.content_hash = self.compute_hash()


class PromptBlockList(BaseModel):
    """Collection of prompt blocks with TTL ordering validation.

    Ensures blocks are ordered correctly for Anthropic's requirement:
    "Cache entries with longer TTL must appear before shorter TTLs."

    Attributes:
        blocks: List of prompt blocks in TTL-descending order
    """

    blocks: list[PromptBlock]

    def validate_ttl_ordering(self) -> tuple[bool, str | None]:
        """Validate that 1h TTL blocks precede 5m TTL blocks.

        Returns:
            (is_valid, error_message)
        """
        seen_five_min = False
        for i, block in enumerate(self.blocks):
            if not block.cacheable:
                continue

            if block.ttl == AnthropicCacheTTL.FIVE_MIN:
                seen_five_min = True
            elif block.ttl == AnthropicCacheTTL.ONE_HOUR and seen_five_min:
                return (
                    False,
                    f"Block {i} has 1h TTL but appears after 5m TTL block (1h must precede 5m)",
                )

        return (True, None)

    def to_api_dict_list(self) -> list[dict]:
        """Convert to dictionary format for LLM Provider API.

        Returns:
            List of dicts suitable for LLMComparisonRequest.prompt_blocks
        """
        return [
            {
                "target": block.target.value,
                "content": block.content,
                "cacheable": block.cacheable,
                "ttl": block.ttl.value,
                "content_hash": block.content_hash,
            }
            for block in self.blocks
        ]
