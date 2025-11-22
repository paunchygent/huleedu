"""Cache sandbox fixture with six short essays for prompt cache hit testing."""

from __future__ import annotations

from typing import Any

SANDBOX_STATIC_BLOCKS: list[dict[str, Any]] = [
    {
        "target": "user_content",
        "content": (
            "**Student Assignment:** Write a brief reflection on a recent learning experience.\n\n"
            "**Assessment Criteria:** Clarity, structure, and use of specific details."
        ),
        "cacheable": True,
        "ttl": "5m",
    },
    {
        "target": "user_content",
        "content": (
            "Using the context above, pick which essay is stronger. Respond with JSON "
            "fields `winner` ('Essay A' or 'Essay B'), `justification` (<=50 chars), "
            "and `confidence` (1-5)."
        ),
        "cacheable": True,
        "ttl": "5m",
    },
]

SANDBOX_ESSAYS: list[dict[str, str]] = [
    {"id": "essay-1", "text": "I struggled with calculus until I drew graphs by hand every day."},
    {"id": "essay-2", "text": "Group study helped me learn enzymes because we taught each other."},
    {
        "id": "essay-3",
        "text": "Building a small robot taught me patience and better debugging habits.",
    },
    {
        "id": "essay-4",
        "text": "A failed chemistry lab reminded me to write clearer procedures first.",
    },
    {"id": "essay-5", "text": "Journaling after lectures made me notice gaps in my understanding."},
    {
        "id": "essay-6",
        "text": "Teaching my sibling fractions forced me to simplify my explanations.",
    },
]

SANDBOX_PAIRS: list[tuple[int, int]] = [(0, 1), (2, 3), (4, 5)]


def build_prompt_blocks_for_pair(index_a: int, index_b: int) -> list[dict[str, Any]]:
    """Build prompt blocks for the specified essay indices using sandbox fixtures."""

    essay_a = SANDBOX_ESSAYS[index_a]
    essay_b = SANDBOX_ESSAYS[index_b]

    essay_blocks = [
        {
            "target": "user_content",
            "content": f"**Essay A (ID: {essay_a['id']}):**\n{essay_a['text']}",
            "cacheable": False,
        },
        {
            "target": "user_content",
            "content": f"**Essay B (ID: {essay_b['id']}):**\n{essay_b['text']}",
            "cacheable": False,
        },
    ]

    return [*SANDBOX_STATIC_BLOCKS, *essay_blocks]
