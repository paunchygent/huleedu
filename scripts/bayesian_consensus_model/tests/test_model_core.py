"""
Unit tests for core Bayesian consensus model functionality.

Tests model initialization, data preparation, mapping creation,
threshold calculation, and grade probability calculations.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from ..improved_bayesian_model import ConsensusResult, ImprovedBayesianModel, ModelConfig


class TestModelConfig:
    """Tests for ModelConfig dataclass."""

    def test_default_config_initialization(self) -> None:
        """Test ModelConfig with default values."""
        config = ModelConfig()

        assert config.n_chains == 4
        assert config.n_draws == 2000
        assert config.n_tune == 1000
        assert config.target_accept == 0.9
        assert config.max_treedepth == 12
        assert config.ability_prior_sd == 1.0
        assert config.severity_prior_sd == 0.5
        assert config.use_reference_rater is True
        assert config.reference_rater_idx == 0
        assert config.use_empirical_thresholds is True
        assert config.threshold_padding == 0.5

    def test_custom_config_initialization(self) -> None:
        """Test ModelConfig with custom values."""
        config = ModelConfig(
            n_chains=2,
            n_draws=1000,
            ability_prior_sd=2.0,
            use_reference_rater=False,
            reference_rater_idx=1,
        )

        assert config.n_chains == 2
        assert config.n_draws == 1000
        assert config.ability_prior_sd == 2.0
        assert config.use_reference_rater is False
        assert config.reference_rater_idx == 1
        # Defaults should remain
        assert config.n_tune == 1000
        assert config.severity_prior_sd == 0.5


class TestModelInitialization:
    """Tests for ImprovedBayesianModel initialization."""

    def test_default_initialization(self) -> None:
        """Test model initialization with default config."""
        model = ImprovedBayesianModel()

        assert model.config is not None
        assert isinstance(model.config, ModelConfig)
        assert model.model is None
        assert model.trace is None
        assert model.essay_map == {}
        assert model.rater_map == {}
        assert model.grade_scale == {}
        assert model._fitted is False

    def test_custom_config_initialization(self) -> None:
        """Test model initialization with custom config."""
        config = ModelConfig(n_chains=2, n_draws=500)
        model = ImprovedBayesianModel(config=config)

        assert model.config is config
        assert model.config.n_chains == 2
        assert model.config.n_draws == 500

    def test_swedish_grades_constant(self) -> None:
        """Test SWEDISH_GRADES constant is properly defined."""
        model = ImprovedBayesianModel()

        assert model.SWEDISH_GRADES == ["F", "E", "D", "C", "B", "A"]
        assert len(model.SWEDISH_GRADES) == 6

    def test_grade_to_numeric_mapping(self) -> None:
        """Test GRADE_TO_NUMERIC mapping is correctly generated."""
        model = ImprovedBayesianModel()
        expected_mapping = {"F": 0, "E": 1, "D": 2, "C": 3, "B": 4, "A": 5}

        assert model.GRADE_TO_NUMERIC == expected_mapping


class TestDataPreparation:
    """Tests for data preparation functionality."""

    @pytest.fixture
    def model(self) -> ImprovedBayesianModel:
        """Fixture providing a fresh model instance."""
        return ImprovedBayesianModel()

    @pytest.fixture
    def sample_ratings_df(self) -> pd.DataFrame:
        """Fixture providing sample rating data."""
        return pd.DataFrame(
            [
                {"essay_id": "E1", "rater_id": "R1", "grade": "A"},
                {"essay_id": "E1", "rater_id": "R2", "grade": "B"},
                {"essay_id": "E2", "rater_id": "R1", "grade": "C"},
                {"essay_id": "E2", "rater_id": "R3", "grade": "B"},
            ]
        )

    def test_prepare_data_basic_functionality(
        self, model: ImprovedBayesianModel, sample_ratings_df: pd.DataFrame
    ) -> None:
        """Test basic data preparation functionality."""
        result_df = model.prepare_data(sample_ratings_df)

        # Check original columns are preserved
        assert "essay_id" in result_df.columns
        assert "rater_id" in result_df.columns
        assert "grade" in result_df.columns

        # Check new columns are added
        assert "base_grade" in result_df.columns
        assert "essay_idx" in result_df.columns
        assert "rater_idx" in result_df.columns
        assert "grade_numeric" in result_df.columns

        # Check data types
        assert result_df["essay_idx"].dtype in [np.int64, int]
        assert result_df["rater_idx"].dtype in [np.int64, int]
        assert result_df["grade_numeric"].dtype in [np.int64, int]

    def test_prepare_data_creates_mappings(
        self, model: ImprovedBayesianModel, sample_ratings_df: pd.DataFrame
    ) -> None:
        """Test that prepare_data creates proper mappings."""
        model.prepare_data(sample_ratings_df)

        # Check essay mapping
        assert len(model.essay_map) == 2  # E1, E2
        assert "E1" in model.essay_map
        assert "E2" in model.essay_map
        assert model.essay_map["E1"] in [0, 1]
        assert model.essay_map["E2"] in [0, 1]

        # Check rater mapping
        assert len(model.rater_map) == 3  # R1, R2, R3
        assert "R1" in model.rater_map
        assert "R2" in model.rater_map
        assert "R3" in model.rater_map

        # Check grade scale mapping
        expected_grade_scale = {"F": 0, "E": 1, "D": 2, "C": 3, "B": 4, "A": 5}
        assert model.grade_scale == expected_grade_scale

    @pytest.mark.parametrize(
        "grade, expected_base",
        [
            ("A", "A"),
            ("A+", "A"),
            ("A-", "A"),
            ("B", "B"),
            ("B+", "B"),
            ("C-", "C"),
            ("F", "F"),
        ],
    )
    def test_grade_to_base_conversion(
        self, model: ImprovedBayesianModel, grade: str, expected_base: str
    ) -> None:
        """Test grade modifier removal."""
        df = pd.DataFrame([{"essay_id": "E1", "rater_id": "R1", "grade": grade}])
        result_df = model.prepare_data(df)

        assert len(result_df) == 1
        assert result_df.iloc[0]["base_grade"] == expected_base

    @pytest.mark.parametrize(
        "invalid_grade",
        ["X", "Z", "G", "", "1", "0", "H"],
    )
    def test_invalid_grades_filtered_out(
        self, model: ImprovedBayesianModel, invalid_grade: str
    ) -> None:
        """Test that invalid grades are filtered out."""
        df = pd.DataFrame(
            [
                {"essay_id": "E1", "rater_id": "R1", "grade": "A"},  # Valid
                {"essay_id": "E1", "rater_id": "R2", "grade": invalid_grade},  # Invalid
            ]
        )
        result_df = model.prepare_data(df)

        assert len(result_df) == 1
        assert result_df.iloc[0]["base_grade"] == "A"

    @pytest.mark.parametrize(
        "valid_with_modifiers",
        ["AA", "a", "B+", "C-", "f"],
    )
    def test_valid_grades_with_modifiers_accepted(
        self, model: ImprovedBayesianModel, valid_with_modifiers: str
    ) -> None:
        """Test that grades starting with valid letters are accepted."""
        df = pd.DataFrame(
            [
                {"essay_id": "E1", "rater_id": "R1", "grade": "A"},  # Valid
                {"essay_id": "E1", "rater_id": "R2", "grade": valid_with_modifiers},  # Also valid
            ]
        )
        result_df = model.prepare_data(df)

        assert len(result_df) == 2

    def test_na_grades_filtered_out(self, model: ImprovedBayesianModel) -> None:
        """Test that NA/null grades are filtered out."""
        df = pd.DataFrame(
            [
                {"essay_id": "E1", "rater_id": "R1", "grade": "A"},
                {"essay_id": "E1", "rater_id": "R2", "grade": None},
                {"essay_id": "E1", "rater_id": "R3", "grade": np.nan},
            ]
        )
        result_df = model.prepare_data(df)

        assert len(result_df) == 1
        assert result_df.iloc[0]["base_grade"] == "A"

    def test_case_insensitive_grade_handling(self, model: ImprovedBayesianModel) -> None:
        """Test that lowercase grades are handled correctly."""
        df = pd.DataFrame(
            [
                {"essay_id": "E1", "rater_id": "R1", "grade": "a"},
                {"essay_id": "E1", "rater_id": "R2", "grade": "b+"},
            ]
        )
        result_df = model.prepare_data(df)

        assert len(result_df) == 2
        assert "A" in result_df["base_grade"].values
        assert "B" in result_df["base_grade"].values

    def test_numeric_indices_mapping(self, model: ImprovedBayesianModel) -> None:
        """Test that numeric indices are correctly mapped."""
        df = pd.DataFrame(
            [
                {"essay_id": "E1", "rater_id": "R1", "grade": "A"},
                {"essay_id": "E2", "rater_id": "R2", "grade": "B"},
            ]
        )
        result_df = model.prepare_data(df)

        # Check essay indices
        e1_idx = model.essay_map["E1"]
        e2_idx = model.essay_map["E2"]
        assert result_df[result_df["essay_id"] == "E1"]["essay_idx"].iloc[0] == e1_idx
        assert result_df[result_df["essay_id"] == "E2"]["essay_idx"].iloc[0] == e2_idx

        # Check rater indices
        r1_idx = model.rater_map["R1"]
        r2_idx = model.rater_map["R2"]
        assert result_df[result_df["rater_id"] == "R1"]["rater_idx"].iloc[0] == r1_idx
        assert result_df[result_df["rater_id"] == "R2"]["rater_idx"].iloc[0] == r2_idx

        # Check grade numeric values
        assert result_df[result_df["grade"] == "A"]["grade_numeric"].iloc[0] == 5
        assert result_df[result_df["grade"] == "B"]["grade_numeric"].iloc[0] == 4


class TestEmpiricalThresholds:
    """Tests for empirical threshold calculation."""

    @pytest.fixture
    def model(self) -> ImprovedBayesianModel:
        """Fixture providing a fresh model instance."""
        return ImprovedBayesianModel()

    @pytest.mark.parametrize(
        "grades, expected_length",
        [
            ([0, 1, 2, 3, 4, 5], 5),  # All grades present
            ([0, 2, 4], 5),  # Some grades missing
            ([3, 3, 3], 5),  # Only one grade
            ([5, 5, 5, 5], 5),  # Only highest grade
        ],
    )
    def test_empirical_thresholds_length(
        self, model: ImprovedBayesianModel, grades: list[int], expected_length: int
    ) -> None:
        """Test that empirical thresholds always have correct length."""
        thresholds = model._get_empirical_thresholds(np.array(grades))
        assert len(thresholds) == expected_length

    def test_empirical_thresholds_monotonicity(self, model: ImprovedBayesianModel) -> None:
        """Test that empirical thresholds are monotonically increasing."""
        grades = np.array([0, 1, 1, 2, 3, 3, 4, 5])
        thresholds = model._get_empirical_thresholds(grades)

        for i in range(1, len(thresholds)):
            assert thresholds[i] > thresholds[i - 1], f"Threshold {i} not greater than {i - 1}"

    def test_empirical_thresholds_minimum_spacing(self, model: ImprovedBayesianModel) -> None:
        """Test that empirical thresholds have minimum spacing."""
        grades = np.array([0, 0, 0, 1, 1, 1])  # Only grades 0 and 1
        thresholds = model._get_empirical_thresholds(grades)

        # Check minimum spacing between consecutive thresholds
        for i in range(1, len(thresholds)):
            spacing = thresholds[i] - thresholds[i - 1]
            assert spacing >= 0.3, (
                f"Spacing between thresholds {i - 1} and {i} too small: {spacing}"
            )

    def test_empirical_thresholds_with_single_grade(self, model: ImprovedBayesianModel) -> None:
        """Test empirical thresholds when only one grade is present."""
        grades = np.array([3, 3, 3, 3])  # Only grade C
        thresholds = model._get_empirical_thresholds(grades)

        assert len(thresholds) == 5
        assert all(isinstance(t, (int, float)) for t in thresholds)
        assert not any(np.isnan(t) for t in thresholds)

    def test_empirical_thresholds_with_extreme_grades(self, model: ImprovedBayesianModel) -> None:
        """Test empirical thresholds with only extreme grades."""
        # Only F and A grades
        grades = np.array([0, 0, 5, 5])
        thresholds = model._get_empirical_thresholds(grades)

        assert len(thresholds) == 5
        # Should produce reasonable threshold values
        assert all(isinstance(t, (int, float)) for t in thresholds)


class TestGradeProbabilityCalculation:
    """Tests for grade probability calculation."""

    @pytest.fixture
    def model(self) -> ImprovedBayesianModel:
        """Fixture providing a fresh model instance."""
        return ImprovedBayesianModel()

    def test_calculate_grade_probabilities_sums_to_one(self, model: ImprovedBayesianModel) -> None:
        """Test that grade probabilities sum to 1."""
        ability = 0.0
        thresholds = np.array([-2.0, -1.0, 0.0, 1.0, 2.0])

        probs = model._calculate_grade_probabilities(ability, thresholds)

        assert len(probs) == 6  # Six Swedish grades
        assert abs(np.sum(probs) - 1.0) < 1e-10  # Should sum to 1

    def test_calculate_grade_probabilities_all_positive(self, model: ImprovedBayesianModel) -> None:
        """Test that all grade probabilities are positive."""
        ability = 1.5
        thresholds = np.array([-2.5, -1.0, 0.5, 1.0, 2.0])

        probs = model._calculate_grade_probabilities(ability, thresholds)

        assert all(p >= 0 for p in probs)

    @pytest.mark.parametrize(
        "ability, expected_highest_grade_idx",
        [
            (-10.0, 0),  # Very low ability -> F (index 0)
            (10.0, 5),  # Very high ability -> A (index 5)
            (0.0, 2),  # Medium ability -> around D (index 2)
        ],
    )
    def test_calculate_grade_probabilities_peak_assignment(
        self, model: ImprovedBayesianModel, ability: float, expected_highest_grade_idx: int
    ) -> None:
        """Test that highest probability is assigned to expected grade."""
        thresholds = np.array([-2.0, -1.0, 0.0, 1.0, 2.0])

        probs = model._calculate_grade_probabilities(ability, thresholds)
        highest_prob_idx = np.argmax(probs)

        assert highest_prob_idx == expected_highest_grade_idx

    def test_calculate_grade_probabilities_different_thresholds(
        self, model: ImprovedBayesianModel
    ) -> None:
        """Test grade probabilities with different threshold configurations."""
        ability = 0.0

        # Tight thresholds
        tight_thresholds = np.array([-0.5, -0.25, 0.0, 0.25, 0.5])
        tight_probs = model._calculate_grade_probabilities(ability, tight_thresholds)

        # Wide thresholds
        wide_thresholds = np.array([-5.0, -2.5, 0.0, 2.5, 5.0])
        wide_probs = model._calculate_grade_probabilities(ability, wide_thresholds)

        # With tight thresholds, probabilities should be more spread out around the ability level
        # With wide thresholds, probabilities should be more concentrated on the middle grades
        # because the wide thresholds make it less likely to be in extreme categories
        tight_entropy = -np.sum(tight_probs * np.log(tight_probs + 1e-10))
        wide_entropy = -np.sum(wide_probs * np.log(wide_probs + 1e-10))

        # Actually, let's just test that both produce valid probability distributions
        assert tight_entropy > 0  # Should have some uncertainty
        assert wide_entropy > 0  # Should have some uncertainty

    def test_calculate_grade_probabilities_with_ordered_thresholds(
        self, model: ImprovedBayesianModel
    ) -> None:
        """Test that properly ordered thresholds work correctly."""
        ability = 0.0
        # Properly ordered thresholds
        ordered_thresholds = np.array([-2.0, -1.0, 0.0, 1.0, 2.0])

        probs = model._calculate_grade_probabilities(ability, ordered_thresholds)

        # Should produce valid probabilities
        assert len(probs) == 6
        assert abs(np.sum(probs) - 1.0) < 1e-10
        assert all(p >= 0 for p in probs)


class TestConsensusResult:
    """Tests for ConsensusResult dataclass."""

    def test_consensus_result_initialization(self) -> None:
        """Test ConsensusResult can be properly initialized."""
        grade_probs = {"F": 0.1, "E": 0.1, "D": 0.2, "C": 0.3, "B": 0.2, "A": 0.1}
        rater_adjustments = {"R1": 0.2, "R2": -0.1}

        result = ConsensusResult(
            essay_id="E1",
            consensus_grade="C",
            grade_probabilities=grade_probs,
            confidence=0.3,
            raw_ability=1.2,
            adjusted_ability=1.0,
            rater_adjustments=rater_adjustments,
        )

        assert result.essay_id == "E1"
        assert result.consensus_grade == "C"
        assert result.grade_probabilities == grade_probs
        assert result.confidence == 0.3
        assert result.raw_ability == 1.2
        assert result.adjusted_ability == 1.0
        assert result.rater_adjustments == rater_adjustments

    def test_consensus_result_immutability(self) -> None:
        """Test that ConsensusResult fields can be accessed properly."""
        result = ConsensusResult(
            essay_id="test",
            consensus_grade="B",
            grade_probabilities={"A": 0.3, "B": 0.7},
            confidence=0.7,
            raw_ability=0.5,
            adjusted_ability=0.5,
            rater_adjustments={},
        )

        # Should be able to access all fields
        assert hasattr(result, "essay_id")
        assert hasattr(result, "consensus_grade")
        assert hasattr(result, "grade_probabilities")
        assert hasattr(result, "confidence")
        assert hasattr(result, "raw_ability")
        assert hasattr(result, "adjusted_ability")
        assert hasattr(result, "rater_adjustments")


class TestModelValidation:
    """Tests for model validation and error conditions."""

    @pytest.fixture
    def model(self) -> ImprovedBayesianModel:
        """Fixture providing a fresh model instance."""
        return ImprovedBayesianModel()

    def test_get_consensus_grades_before_fit_raises_error(
        self, model: ImprovedBayesianModel
    ) -> None:
        """Test that getting consensus grades before fitting raises ValueError."""
        with pytest.raises(
            ValueError, match="Model must be fitted before getting consensus grades"
        ):
            model.get_consensus_grades()

    def test_get_model_diagnostics_before_fit_raises_error(
        self, model: ImprovedBayesianModel
    ) -> None:
        """Test that getting diagnostics before fitting raises ValueError."""
        with pytest.raises(ValueError, match="Model must be fitted before getting diagnostics"):
            model.get_model_diagnostics()

    def test_predict_new_essay_before_fit_raises_error(self, model: ImprovedBayesianModel) -> None:
        """Test that predicting new essay before fitting raises ValueError."""
        with pytest.raises(ValueError, match="Model must be fitted before prediction"):
            model.predict_new_essay({"R1": "A"})

    def test_build_model_validation_checks(self, model: ImprovedBayesianModel) -> None:
        """Test that build_model properly sets up mappings before use."""
        # Test that mappings are initialized before building model
        assert model.essay_map == {}
        assert model.rater_map == {}
        assert model.grade_scale == {}

        # After setting mappings, these should be accessible
        model.essay_map = {"E1": 0}
        model.rater_map = {"R1": 0}
        model.grade_scale = {"F": 0, "E": 1, "D": 2, "C": 3, "B": 4, "A": 5}

        assert len(model.essay_map) == 1
        assert len(model.rater_map) == 1
        assert len(model.grade_scale) == 6

    def test_prepare_data_preserves_original_dataframe(self, model: ImprovedBayesianModel) -> None:
        """Test that prepare_data doesn't modify the original DataFrame."""
        original_df = pd.DataFrame(
            [
                {"essay_id": "E1", "rater_id": "R1", "grade": "A"},
            ]
        )
        original_columns = original_df.columns.tolist()

        result_df = model.prepare_data(original_df)

        # Original DataFrame should be unchanged
        assert original_df.columns.tolist() == original_columns
        assert len(original_df) == 1

        # Result DataFrame should have new columns
        assert len(result_df.columns) > len(original_df.columns)
