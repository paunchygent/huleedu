"""Unit tests for prompt template builder.

Rule 075 compliant: Uses @pytest.mark.parametrize for comprehensive coverage.

Tests cache-friendly prompt composition including:
- Hash stability for static blocks
- TTL mapping (5min vs 1hour)
- TTL ordering enforcement
- Block target assignment
- Content formatting
- Error handling
"""

import pytest

from services.cj_assessment_service.cj_core_logic.prompt_templates import (
    PromptTemplateBuilder,
)
from services.cj_assessment_service.models_api import EssayForComparison
from services.cj_assessment_service.models_prompt import (
    AnthropicCacheTTL,
    CacheableBlockTarget,
    PromptBlock,
    PromptBlockList,
)


class TestPromptBlockHashStability:
    """Test that static blocks generate consistent hashes for same input."""

    @pytest.mark.parametrize(
        "context",
        [
            # Standard full context
            {
                "student_prompt_text": "Write about summer",
                "assessment_instructions": "Assess clarity and structure",
                "judge_rubric_text": "Prioritize originality",
            },
            # Minimal context
            {"student_prompt_text": "Short prompt"},
            # Unicode content
            {
                "student_prompt_text": "Skriv om sommaren åäö",
                "assessment_instructions": "Bedöm tydlighet",
            },
        ],
        ids=["full_context", "minimal_context", "unicode_context"],
    )
    def test_same_context_produces_identical_hash(self, context: dict[str, str | None]) -> None:
        """Given identical assessment context, hashes should match consistently."""
        blocks1 = PromptTemplateBuilder.build_static_blocks(context)
        blocks2 = PromptTemplateBuilder.build_static_blocks(context)

        assert len(blocks1) == len(blocks2)
        if blocks1:  # Empty context returns empty list
            assert blocks1[0].content_hash == blocks2[0].content_hash

    @pytest.mark.parametrize(
        "context1,context2,should_match",
        [
            # Same content - should match
            (
                {"student_prompt_text": "Write about summer"},
                {"student_prompt_text": "Write about summer"},
                True,
            ),
            # Different content - should not match
            (
                {"student_prompt_text": "Write about summer"},
                {"student_prompt_text": "Write about winter"},
                False,
            ),
            # Additional field - should not match
            (
                {"student_prompt_text": "Test"},
                {"student_prompt_text": "Test", "assessment_instructions": "Extra"},
                False,
            ),
        ],
        ids=["identical", "different_content", "different_fields"],
    )
    def test_hash_changes_with_content(
        self,
        context1: dict[str, str | None],
        context2: dict[str, str | None],
        should_match: bool,
    ) -> None:
        """Hash should change when content changes."""
        blocks1 = PromptTemplateBuilder.build_static_blocks(context1)
        blocks2 = PromptTemplateBuilder.build_static_blocks(context2)

        if should_match:
            assert blocks1[0].content_hash == blocks2[0].content_hash
        else:
            assert blocks1[0].content_hash != blocks2[0].content_hash


class TestTTLMapping:
    """Test that TTL values are correctly mapped to Anthropic's allowed values."""

    @pytest.mark.parametrize(
        "use_extended_ttl,expected_ttl,expected_value",
        [
            # Default: 5 minutes
            (False, AnthropicCacheTTL.FIVE_MIN, "5m"),
            # Extended: 1 hour
            (True, AnthropicCacheTTL.ONE_HOUR, "1h"),
        ],
        ids=["default_5min", "extended_1hour"],
    )
    def test_static_block_ttl_mapping(
        self, use_extended_ttl: bool, expected_ttl: AnthropicCacheTTL, expected_value: str
    ) -> None:
        """Static blocks should use correct TTL based on configuration."""
        context: dict[str, str | None] = {"student_prompt_text": "Test prompt"}
        blocks = PromptTemplateBuilder.build_static_blocks(context, use_extended_ttl)

        assert len(blocks) == 1
        assert blocks[0].ttl == expected_ttl
        assert blocks[0].ttl.value == expected_value

    @pytest.mark.parametrize(
        "use_extended_ttl,expected_ttl",
        [(False, AnthropicCacheTTL.FIVE_MIN), (True, AnthropicCacheTTL.ONE_HOUR)],
        ids=["instructions_5min", "instructions_1hour"],
    )
    def test_response_instructions_ttl_mapping(
        self, use_extended_ttl: bool, expected_ttl: AnthropicCacheTTL
    ) -> None:
        """Response instructions should support both TTL options."""
        block = PromptTemplateBuilder.build_response_instructions_block(use_extended_ttl)

        assert block.ttl == expected_ttl
        assert block.cacheable is True


class TestTTLOrdering:
    """Test TTL ordering enforcement (1h must precede 5m)."""

    @pytest.mark.parametrize(
        "use_extended_ttl",
        [False, True],
        ids=["all_5min", "all_1hour"],
    )
    def test_uniform_ttl_passes_validation(self, use_extended_ttl: bool) -> None:
        """All blocks with same TTL should pass validation."""
        context: dict[str, str | None] = {"student_prompt_text": "Test"}
        essay_a = EssayForComparison(id="a", text_content="Text A")
        essay_b = EssayForComparison(id="b", text_content="Text B")

        prompt_list = PromptTemplateBuilder.assemble_full_prompt(
            context, essay_a, essay_b, use_extended_ttl
        )

        is_valid, error_msg = prompt_list.validate_ttl_ordering()
        assert is_valid
        assert error_msg is None

    def test_mixed_ttl_ordering_validation(self) -> None:
        """1h TTL blocks before 5m TTL blocks should pass validation."""
        blocks = [
            PromptBlock(
                target=CacheableBlockTarget.USER_CONTENT,
                content="Static 1h",
                cacheable=True,
                ttl=AnthropicCacheTTL.ONE_HOUR,
            ),
            PromptBlock(
                target=CacheableBlockTarget.USER_CONTENT,
                content="Dynamic",
                cacheable=False,
            ),
            PromptBlock(
                target=CacheableBlockTarget.USER_CONTENT,
                content="Static 5m",
                cacheable=True,
                ttl=AnthropicCacheTTL.FIVE_MIN,
            ),
        ]

        prompt_list = PromptBlockList(blocks=blocks)
        is_valid, error_msg = prompt_list.validate_ttl_ordering()
        assert is_valid
        assert error_msg is None


class TestEssayBlocks:
    """Test essay block generation."""

    @pytest.mark.parametrize(
        "essay_a_id,essay_a_text,essay_b_id,essay_b_text",
        [
            # Standard IDs and text
            ("essay-a", "Summer was fun.", "essay-b", "I went swimming."),
            # Long IDs
            ("a" * 50, "Text A", "b" * 50, "Text B"),
            # Unicode content
            ("id-1", "Sommaren var rolig åäö", "id-2", "Jag badade öäå"),
            # Empty essays (edge case)
            ("empty-a", "", "empty-b", ""),
        ],
        ids=["standard", "long_ids", "unicode_text", "empty_essays"],
    )
    def test_essay_block_structure(
        self,
        essay_a_id: str,
        essay_a_text: str,
        essay_b_id: str,
        essay_b_text: str,
    ) -> None:
        """Essay blocks should include IDs and content, never be cacheable."""
        essay_a = EssayForComparison(id=essay_a_id, text_content=essay_a_text)
        essay_b = EssayForComparison(id=essay_b_id, text_content=essay_b_text)

        blocks = PromptTemplateBuilder.render_dynamic_essays(essay_a, essay_b)

        # Always 2 blocks
        assert len(blocks) == 2

        # Never cacheable
        assert blocks[0].cacheable is False
        assert blocks[1].cacheable is False

        # IDs present in content
        assert essay_a_id in blocks[0].content
        assert essay_b_id in blocks[1].content

        # Text content present
        assert essay_a_text in blocks[0].content
        assert essay_b_text in blocks[1].content


class TestBlockTargetAssignment:
    """Test that blocks are assigned to correct targets."""

    @pytest.mark.parametrize(
        "builder_method,expected_target",
        [
            ("build_static_blocks", CacheableBlockTarget.USER_CONTENT),
            ("build_response_instructions_block", CacheableBlockTarget.USER_CONTENT),
        ],
        ids=["static_blocks", "response_instructions"],
    )
    def test_block_targets(
        self, builder_method: str, expected_target: CacheableBlockTarget
    ) -> None:
        """All blocks should target USER_CONTENT."""
        if builder_method == "build_static_blocks":
            context: dict[str, str | None] = {"student_prompt_text": "Test"}
            blocks = PromptTemplateBuilder.build_static_blocks(context)
            if blocks:  # May be empty for empty context
                assert blocks[0].target == expected_target
        else:
            block = PromptTemplateBuilder.build_response_instructions_block()
            assert block.target == expected_target


class TestAssessmentContextFormatting:
    """Test that assessment context is formatted correctly."""

    @pytest.mark.parametrize(
        "context,expected_headers,not_expected_headers",
        [
            # All fields present
            (
                {
                    "student_prompt_text": "Write about summer",
                    "assessment_instructions": "Assess clarity",
                    "judge_rubric_text": "Prioritize coherence",
                },
                ["Student Assignment", "Assessment Criteria", "Judge Instructions"],
                [],
            ),
            # Only student prompt
            (
                {
                    "student_prompt_text": "Write about summer",
                    "assessment_instructions": None,
                    "judge_rubric_text": None,
                },
                ["Student Assignment"],
                ["Assessment Criteria", "Judge Instructions"],
            ),
            # Only instructions
            (
                {
                    "student_prompt_text": None,
                    "assessment_instructions": "Assess clarity",
                    "judge_rubric_text": None,
                },
                ["Assessment Criteria"],
                ["Student Assignment", "Judge Instructions"],
            ),
        ],
        ids=["all_fields", "only_student_prompt", "only_instructions"],
    )
    def test_context_field_inclusion(
        self,
        context: dict[str, str | None],
        expected_headers: list[str],
        not_expected_headers: list[str],
    ) -> None:
        """Only provided context fields should appear in output."""
        blocks = PromptTemplateBuilder.build_static_blocks(context)

        if not blocks:
            # Empty context
            assert not expected_headers
            return

        content = blocks[0].content

        for header in expected_headers:
            assert header in content, f"Expected header '{header}' not found"

        for header in not_expected_headers:
            assert header not in content, f"Unexpected header '{header}' found"

    @pytest.mark.parametrize(
        "context,expected_separator",
        [
            (
                {
                    "student_prompt_text": "Prompt 1",
                    "assessment_instructions": "Instructions 1",
                },
                "\n\n",
            ),
            (
                {
                    "student_prompt_text": "P1",
                    "assessment_instructions": "I1",
                    "judge_rubric_text": "R1",
                },
                "\n\n",
            ),
        ],
        ids=["two_fields", "three_fields"],
    )
    def test_section_separation(
        self, context: dict[str, str | None], expected_separator: str
    ) -> None:
        """Sections should be separated by double newline."""
        blocks = PromptTemplateBuilder.build_static_blocks(context)
        content = blocks[0].content

        assert expected_separator in content


class TestEmptyContextHandling:
    """Test behavior when context fields are empty or None."""

    @pytest.mark.parametrize(
        "context,expected_block_count",
        [
            # All None - empty list
            (
                {
                    "student_prompt_text": None,
                    "assessment_instructions": None,
                    "judge_rubric_text": None,
                },
                0,
            ),
            # One field - one block
            ({"student_prompt_text": "Test"}, 1),
            # Empty string treated as None
            (
                {
                    "student_prompt_text": "",
                    "assessment_instructions": None,
                    "judge_rubric_text": None,
                },
                0,
            ),
        ],
        ids=["all_none", "one_field", "empty_string"],
    )
    def test_empty_context_block_count(
        self, context: dict[str, str | None], expected_block_count: int
    ) -> None:
        """Empty context should return appropriate number of blocks."""
        blocks = PromptTemplateBuilder.build_static_blocks(context)
        assert len(blocks) == expected_block_count

    def test_full_prompt_with_empty_context(self) -> None:
        """Full prompt with empty context should still include essays and instructions."""
        context: dict[str, str | None] = {
            "student_prompt_text": None,
            "assessment_instructions": None,
            "judge_rubric_text": None,
        }
        essay_a = EssayForComparison(id="a", text_content="Text A")
        essay_b = EssayForComparison(id="b", text_content="Text B")

        prompt_list = PromptTemplateBuilder.assemble_full_prompt(context, essay_a, essay_b)

        # Should have: 0 static context + 2 essays + 1 response instructions = 3 blocks
        assert len(prompt_list.blocks) == 3


class TestContentHashComputation:
    """Test SHA256 hash computation for blocks."""

    @pytest.mark.parametrize(
        "context",
        [
            {"student_prompt_text": "Test"},
            {"student_prompt_text": "Different content"},
            {
                "student_prompt_text": "Test",
                "assessment_instructions": "Instructions",
            },
        ],
        ids=["simple", "different_text", "multiple_fields"],
    )
    def test_hash_computed_automatically(self, context: dict[str, str | None]) -> None:
        """Hash should be computed automatically for all contexts."""
        blocks = PromptTemplateBuilder.build_static_blocks(context)

        assert blocks[0].content_hash is not None
        assert len(blocks[0].content_hash) == 64  # SHA256 hex = 64 chars

    def test_hash_deterministic(self) -> None:
        """Same content should produce same hash consistently."""
        context: dict[str, str | None] = {"student_prompt_text": "Test"}
        blocks1 = PromptTemplateBuilder.build_static_blocks(context)
        blocks2 = PromptTemplateBuilder.build_static_blocks(context)

        assert blocks1[0].content_hash == blocks2[0].content_hash


class TestBlockOrdering:
    """Test that blocks are assembled in correct order."""

    @pytest.mark.parametrize(
        "has_static_context",
        [True, False],
        ids=["with_static_context", "without_static_context"],
    )
    def test_full_prompt_block_order(self, has_static_context: bool) -> None:
        """Blocks should be ordered correctly regardless of context presence."""
        if has_static_context:
            context: dict[str, str | None] = {"student_prompt_text": "Prompt"}
            expected_block_count = 4  # static + essay_a + essay_b + instructions
        else:
            context = {
                "student_prompt_text": None,
                "assessment_instructions": None,
                "judge_rubric_text": None,
            }
            expected_block_count = 3  # essay_a + essay_b + instructions

        essay_a = EssayForComparison(id="a", text_content="Text A")
        essay_b = EssayForComparison(id="b", text_content="Text B")

        prompt_list = PromptTemplateBuilder.assemble_full_prompt(context, essay_a, essay_b)

        assert len(prompt_list.blocks) == expected_block_count

        # Last block is always response instructions
        assert "determine which essay" in prompt_list.blocks[-1].content


class TestExtendedTTLFlagPropagation:
    """Test that use_extended_ttl flag propagates correctly."""

    @pytest.mark.parametrize(
        "use_extended_ttl,expected_ttl",
        [
            (False, AnthropicCacheTTL.FIVE_MIN),
            (True, AnthropicCacheTTL.ONE_HOUR),
        ],
        ids=["default_5min", "extended_1hour"],
    )
    def test_extended_ttl_propagation(
        self, use_extended_ttl: bool, expected_ttl: AnthropicCacheTTL
    ) -> None:
        """TTL flag should propagate to all cacheable blocks."""
        context: dict[str, str | None] = {"student_prompt_text": "Test"}
        essay_a = EssayForComparison(id="a", text_content="Text A")
        essay_b = EssayForComparison(id="b", text_content="Text B")

        prompt_list = PromptTemplateBuilder.assemble_full_prompt(
            context, essay_a, essay_b, use_extended_ttl
        )

        # Find all cacheable blocks
        cacheable_blocks = [b for b in prompt_list.blocks if b.cacheable]

        # All cacheable blocks should have expected TTL
        assert all(b.ttl == expected_ttl for b in cacheable_blocks)
        assert len(cacheable_blocks) == 2  # static context + response instructions


class TestToApiDictList:
    """Test conversion of PromptBlockList to API dictionary format."""

    @pytest.mark.parametrize(
        "use_extended_ttl",
        [False, True],
        ids=["ttl_5min", "ttl_1hour"],
    )
    def test_api_dict_structure_and_values(self, use_extended_ttl: bool) -> None:
        """Converted blocks should have correct structure and preserve values."""
        context: dict[str, str | None] = {"student_prompt_text": "Test"}
        essay_a = EssayForComparison(id="a", text_content="Text A")
        essay_b = EssayForComparison(id="b", text_content="Text B")

        prompt_list = PromptTemplateBuilder.assemble_full_prompt(
            context, essay_a, essay_b, use_extended_ttl
        )
        api_dicts = prompt_list.to_api_dict_list()

        # Correct count
        assert len(api_dicts) == 4

        # All have required keys
        for block_dict in api_dicts:
            assert "target" in block_dict
            assert "content" in block_dict
            assert "cacheable" in block_dict
            assert "ttl" in block_dict
            assert "content_hash" in block_dict

        # Static blocks cacheable with correct TTL
        expected_ttl_value = "1h" if use_extended_ttl else "5m"
        assert api_dicts[0]["cacheable"] is True
        assert api_dicts[0]["ttl"] == expected_ttl_value

        # Essay blocks not cacheable
        assert api_dicts[1]["cacheable"] is False
        assert api_dicts[2]["cacheable"] is False

        # Response instructions cacheable
        assert api_dicts[3]["cacheable"] is True
