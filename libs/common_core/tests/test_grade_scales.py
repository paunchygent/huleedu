"""
Unit tests for grade scale registry.

Tests grade scale metadata, validation, and helper functions.
"""

from __future__ import annotations

import pytest
from common_core.grade_scales import (
    GRADE_SCALES,
    GradeScaleMetadata,
    get_grade_index,
    get_scale,
    get_uniform_priors,
    list_available_scales,
    validate_grade_for_scale,
)


class TestGradeScaleMetadata:
    """Tests for GradeScaleMetadata dataclass."""

    def test_valid_metadata_creation(self) -> None:
        """Test creating valid grade scale metadata."""
        metadata = GradeScaleMetadata(
            scale_id="test_scale",
            display_name="Test Scale",
            grades=["F", "E", "D"],
            population_priors={"F": 0.3, "E": 0.4, "D": 0.3},
            description="Test scale description",
            allows_below_lowest=True,
            below_lowest_grade="U",
        )

        assert metadata.scale_id == "test_scale"
        assert metadata.grades == ["F", "E", "D"]
        assert metadata.population_priors == {"F": 0.3, "E": 0.4, "D": 0.3}
        assert metadata.allows_below_lowest is True
        assert metadata.below_lowest_grade == "U"

    def test_metadata_without_priors(self) -> None:
        """Test metadata with None population priors."""
        metadata = GradeScaleMetadata(
            scale_id="test_scale",
            display_name="Test Scale",
            grades=["1", "2", "3"],
            population_priors=None,
            description="No priors",
            allows_below_lowest=False,
            below_lowest_grade=None,
        )

        assert metadata.population_priors is None

    def test_empty_scale_id_raises(self) -> None:
        """Test that empty scale_id raises ValueError."""
        with pytest.raises(ValueError, match="scale_id cannot be empty"):
            GradeScaleMetadata(
                scale_id="",
                display_name="Test",
                grades=["A"],
                population_priors=None,
                description="Test",
                allows_below_lowest=False,
                below_lowest_grade=None,
            )

    def test_empty_grades_raises(self) -> None:
        """Test that empty grades list raises ValueError."""
        with pytest.raises(ValueError, match="grades list cannot be empty"):
            GradeScaleMetadata(
                scale_id="test",
                display_name="Test",
                grades=[],
                population_priors=None,
                description="Test",
                allows_below_lowest=False,
                below_lowest_grade=None,
            )

    def test_duplicate_grades_raises(self) -> None:
        """Test that duplicate grades raise ValueError."""
        with pytest.raises(ValueError, match="grades must be unique"):
            GradeScaleMetadata(
                scale_id="test",
                display_name="Test",
                grades=["A", "B", "A"],
                population_priors=None,
                description="Test",
                allows_below_lowest=False,
                below_lowest_grade=None,
            )

    def test_priors_not_summing_to_one_raises(self) -> None:
        """Test that priors not summing to 1.0 raise ValueError."""
        with pytest.raises(ValueError, match="must sum to 1.0"):
            GradeScaleMetadata(
                scale_id="test",
                display_name="Test",
                grades=["A", "B"],
                population_priors={"A": 0.3, "B": 0.5},  # Sums to 0.8
                description="Test",
                allows_below_lowest=False,
                below_lowest_grade=None,
            )

    def test_priors_with_unknown_grades_raises(self) -> None:
        """Test that priors referencing unknown grades raise ValueError."""
        with pytest.raises(ValueError, match="reference unknown grades"):
            GradeScaleMetadata(
                scale_id="test",
                display_name="Test",
                grades=["A", "B"],
                population_priors={"A": 0.5, "B": 0.3, "C": 0.2},
                description="Test",
                allows_below_lowest=False,
                below_lowest_grade=None,
            )

    def test_allows_below_without_grade_raises(self) -> None:
        """Test that allows_below_lowest=True requires below_lowest_grade."""
        with pytest.raises(ValueError, match="below_lowest_grade must be specified"):
            GradeScaleMetadata(
                scale_id="test",
                display_name="Test",
                grades=["A", "B"],
                population_priors=None,
                description="Test",
                allows_below_lowest=True,
                below_lowest_grade=None,
            )

    def test_below_grade_without_allows_raises(self) -> None:
        """Test that below_lowest_grade requires allows_below_lowest=True."""
        with pytest.raises(ValueError, match="below_lowest_grade must be None"):
            GradeScaleMetadata(
                scale_id="test",
                display_name="Test",
                grades=["A", "B"],
                population_priors=None,
                description="Test",
                allows_below_lowest=False,
                below_lowest_grade="U",
            )


class TestRegistryScales:
    """Tests for the three registered grade scales."""

    def test_swedish_8_anchor_scale(self) -> None:
        """Test Swedish 8-anchor scale configuration."""
        scale = GRADE_SCALES["swedish_8_anchor"]

        assert scale.scale_id == "swedish_8_anchor"
        assert scale.display_name == "Swedish National Exam (8-anchor)"
        assert scale.grades == ["F", "E", "D", "D+", "C", "C+", "B", "A"]
        assert scale.population_priors is not None
        assert len(scale.population_priors) == 8
        assert sum(scale.population_priors.values()) == pytest.approx(1.0)
        assert scale.allows_below_lowest is False
        assert scale.below_lowest_grade is None

    def test_eng5_np_legacy_scale(self) -> None:
        """Test ENG5 NP Legacy 9-step scale configuration."""
        scale = GRADE_SCALES["eng5_np_legacy_9_step"]

        assert scale.scale_id == "eng5_np_legacy_9_step"
        assert scale.display_name == "ENG5 NP Legacy (9-step)"
        assert scale.grades == ["F+", "E-", "E+", "D-", "D+", "C-", "C+", "B", "A"]
        assert scale.population_priors is not None
        assert len(scale.population_priors) == 9

        # Uniform priors (1/9 each)
        for grade in scale.grades:
            assert scale.population_priors[grade] == pytest.approx(1.0 / 9.0)

        assert scale.allows_below_lowest is True
        assert scale.below_lowest_grade == "F"

    def test_eng5_np_national_scale(self) -> None:
        """Test ENG5 NP National 9-step scale configuration."""
        scale = GRADE_SCALES["eng5_np_national_9_step"]

        assert scale.scale_id == "eng5_np_national_9_step"
        assert scale.display_name == "ENG5 NP National (9-step)"
        assert scale.grades == ["1", "2", "3", "4", "5", "6", "7", "8", "9"]
        assert scale.population_priors is not None
        assert len(scale.population_priors) == 9

        # Uniform priors (1/9 each)
        for grade in scale.grades:
            assert scale.population_priors[grade] == pytest.approx(1.0 / 9.0)

        assert scale.allows_below_lowest is True
        assert scale.below_lowest_grade == "0"


class TestGetScale:
    """Tests for get_scale() function."""

    def test_get_swedish_scale(self) -> None:
        """Test retrieving Swedish scale."""
        scale = get_scale("swedish_8_anchor")
        assert scale.scale_id == "swedish_8_anchor"

    def test_get_eng5_legacy_scale(self) -> None:
        """Test retrieving ENG5 Legacy scale."""
        scale = get_scale("eng5_np_legacy_9_step")
        assert scale.scale_id == "eng5_np_legacy_9_step"

    def test_get_eng5_national_scale(self) -> None:
        """Test retrieving ENG5 National scale."""
        scale = get_scale("eng5_np_national_9_step")
        assert scale.scale_id == "eng5_np_national_9_step"

    def test_get_unknown_scale_raises(self) -> None:
        """Test that unknown scale_id raises ValueError."""
        with pytest.raises(ValueError, match="Unknown grade scale 'invalid_scale'"):
            get_scale("invalid_scale")

    def test_error_message_lists_available_scales(self) -> None:
        """Test that error message includes available scales."""
        with pytest.raises(ValueError, match="Available scales: eng5_np_legacy_9_step"):
            get_scale("invalid_scale")


class TestValidateGradeForScale:
    """Tests for validate_grade_for_scale() function."""

    @pytest.mark.parametrize(
        ("grade", "scale_id", "expected"),
        [
            # Swedish scale - valid grades
            ("F", "swedish_8_anchor", True),
            ("E", "swedish_8_anchor", True),
            ("A", "swedish_8_anchor", True),
            ("D+", "swedish_8_anchor", True),
            # Swedish scale - invalid grades
            ("U", "swedish_8_anchor", False),
            ("F+", "swedish_8_anchor", False),
            ("0", "swedish_8_anchor", False),
            # ENG5 Legacy - valid grades
            ("F+", "eng5_np_legacy_9_step", True),
            ("E-", "eng5_np_legacy_9_step", True),
            ("A", "eng5_np_legacy_9_step", True),
            ("F", "eng5_np_legacy_9_step", True),  # Below-lowest grade
            # ENG5 Legacy - invalid grades
            ("U", "eng5_np_legacy_9_step", False),
            ("D", "eng5_np_legacy_9_step", False),  # Not in scale
            ("0", "eng5_np_legacy_9_step", False),
            # ENG5 National - valid grades
            ("1", "eng5_np_national_9_step", True),
            ("5", "eng5_np_national_9_step", True),
            ("9", "eng5_np_national_9_step", True),
            ("0", "eng5_np_national_9_step", True),  # Below-lowest grade
            # ENG5 National - invalid grades
            ("10", "eng5_np_national_9_step", False),
            ("A", "eng5_np_national_9_step", False),
            ("F", "eng5_np_national_9_step", False),
        ],
    )
    def test_grade_validation(self, grade: str, scale_id: str, expected: bool) -> None:
        """Test grade validation for all scales."""
        result = validate_grade_for_scale(grade, scale_id)
        assert result == expected

    def test_validate_with_unknown_scale_raises(self) -> None:
        """Test validation with unknown scale raises ValueError."""
        with pytest.raises(ValueError, match="Unknown grade scale"):
            validate_grade_for_scale("A", "unknown_scale")


class TestListAvailableScales:
    """Tests for list_available_scales() function."""

    def test_list_scales_returns_all_three(self) -> None:
        """Test that all three scales are listed."""
        scales = list_available_scales()

        assert len(scales) == 3
        assert "swedish_8_anchor" in scales
        assert "eng5_np_legacy_9_step" in scales
        assert "eng5_np_national_9_step" in scales

    def test_list_scales_is_sorted(self) -> None:
        """Test that scales are returned in sorted order."""
        scales = list_available_scales()
        assert scales == sorted(scales)


class TestGetGradeIndex:
    """Tests for get_grade_index() function."""

    @pytest.mark.parametrize(
        ("grade", "scale_id", "expected_index"),
        [
            # Swedish scale
            ("F", "swedish_8_anchor", 0),
            ("E", "swedish_8_anchor", 1),
            ("A", "swedish_8_anchor", 7),
            ("D+", "swedish_8_anchor", 3),
            # ENG5 Legacy
            ("F+", "eng5_np_legacy_9_step", 0),
            ("E-", "eng5_np_legacy_9_step", 1),
            ("A", "eng5_np_legacy_9_step", 8),
            ("F", "eng5_np_legacy_9_step", -1),  # Below-lowest
            # ENG5 National
            ("1", "eng5_np_national_9_step", 0),
            ("5", "eng5_np_national_9_step", 4),
            ("9", "eng5_np_national_9_step", 8),
            ("0", "eng5_np_national_9_step", -1),  # Below-lowest
        ],
    )
    def test_grade_index(self, grade: str, scale_id: str, expected_index: int) -> None:
        """Test grade index calculation."""
        index = get_grade_index(grade, scale_id)
        assert index == expected_index

    def test_invalid_grade_raises(self) -> None:
        """Test that invalid grade raises ValueError."""
        with pytest.raises(ValueError, match="not valid for scale"):
            get_grade_index("X", "swedish_8_anchor")

    def test_unknown_scale_raises(self) -> None:
        """Test that unknown scale raises ValueError."""
        with pytest.raises(ValueError, match="Unknown grade scale"):
            get_grade_index("A", "unknown_scale")


class TestGetUniformPriors:
    """Tests for get_uniform_priors() function."""

    def test_swedish_uniform_priors(self) -> None:
        """Test generating uniform priors for Swedish scale."""
        priors = get_uniform_priors("swedish_8_anchor")

        assert len(priors) == 8
        assert all(v == pytest.approx(1.0 / 8.0) for v in priors.values())
        assert sum(priors.values()) == pytest.approx(1.0)
        assert set(priors.keys()) == {"F", "E", "D", "D+", "C", "C+", "B", "A"}

    def test_eng5_legacy_uniform_priors(self) -> None:
        """Test generating uniform priors for ENG5 Legacy scale."""
        priors = get_uniform_priors("eng5_np_legacy_9_step")

        assert len(priors) == 9
        assert all(v == pytest.approx(1.0 / 9.0) for v in priors.values())
        assert sum(priors.values()) == pytest.approx(1.0)

    def test_eng5_national_uniform_priors(self) -> None:
        """Test generating uniform priors for ENG5 National scale."""
        priors = get_uniform_priors("eng5_np_national_9_step")

        assert len(priors) == 9
        assert all(v == pytest.approx(1.0 / 9.0) for v in priors.values())
        assert sum(priors.values()) == pytest.approx(1.0)

    def test_unknown_scale_raises(self) -> None:
        """Test that unknown scale raises ValueError."""
        with pytest.raises(ValueError, match="Unknown grade scale"):
            get_uniform_priors("unknown_scale")
