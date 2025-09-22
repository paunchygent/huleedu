"""Cross-validation framework for small sample Bayesian model evaluation.

Implements:
1. Leave-one-out cross-validation (LOO-CV)
2. K-fold cross-validation with stratification
3. Performance metrics suitable for ordinal data
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
from sklearn.model_selection import KFold, StratifiedKFold

from .improved_bayesian_model import ImprovedBayesianModel, ModelConfig


@dataclass
class CVResult:
    """Results from cross-validation."""

    method: str
    n_folds: int
    mean_absolute_error: float
    ordinal_accuracy: float
    adjacent_accuracy: float  # Correct or off-by-one
    grade_confusion_matrix: pd.DataFrame
    fold_metrics: List[Dict]
    ja24_predictions: List[str]  # Predictions for JA24 across folds


class CrossValidator:
    """Cross-validation for Bayesian consensus model."""

    SWEDISH_GRADES = ["F", "E", "D", "C", "B", "A"]
    GRADE_VALUES = {g: i for i, g in enumerate(SWEDISH_GRADES)}

    def __init__(self, model_config: Optional[ModelConfig] = None):
        """Initialize cross-validator.

        Args:
            model_config: Configuration for Bayesian model
        """
        self.model_config = model_config or ModelConfig()
        # Use fewer iterations for CV to speed up
        self.model_config.n_draws = 500
        self.model_config.n_tune = 500

    def leave_one_out_cv(self, ratings_df: pd.DataFrame) -> CVResult:
        """Perform leave-one-out cross-validation.

        Best for very small datasets.

        Args:
            ratings_df: DataFrame with columns [essay_id, rater_id, grade]

        Returns:
            Cross-validation results
        """
        essays = ratings_df["essay_id"].unique()
        n_essays = len(essays)

        predictions = []
        actuals = []
        fold_metrics = []
        ja24_preds = []

        for i, test_essay in enumerate(essays):
            print(f"LOO-CV: Processing essay {i + 1}/{n_essays}")

            # Split data
            train_df = ratings_df[ratings_df["essay_id"] != test_essay]
            test_df = ratings_df[ratings_df["essay_id"] == test_essay]

            if len(train_df) < 10:  # Skip if too little training data
                continue

            try:
                # Fit model on training data
                model = ImprovedBayesianModel(self.model_config)
                model.fit(train_df)

                # Get true consensus for test essay (majority vote)
                test_grades = test_df["grade"].apply(lambda x: x[0] if x else None)
                true_grade = test_grades.mode()[0] if len(test_grades) > 0 else "C"

                # Predict test essay
                test_ratings = {row["rater_id"]: row["grade"] for _, row in test_df.iterrows()}

                # Get prediction using fitted model
                consensus_results = model.get_consensus_grades()

                # Find closest essay in training set for prediction
                if test_essay in consensus_results:
                    pred_grade = consensus_results[test_essay].consensus_grade
                else:
                    # Use model to predict based on test ratings
                    pred_result = model.predict_new_essay(test_ratings)
                    pred_grade = pred_result.consensus_grade

                predictions.append(pred_grade)
                actuals.append(true_grade)

                if test_essay == "JA24":
                    ja24_preds.append(pred_grade)

                # Calculate fold metrics
                error = abs(
                    self.GRADE_VALUES.get(pred_grade, 3) - self.GRADE_VALUES.get(true_grade, 3)
                )
                fold_metrics.append(
                    {
                        "essay": test_essay,
                        "predicted": pred_grade,
                        "actual": true_grade,
                        "error": error,
                    }
                )

            except Exception as e:
                print(f"Error in fold for essay {test_essay}: {e}")
                continue

        # Calculate overall metrics
        mae = np.mean([m["error"] for m in fold_metrics])
        accuracy = np.mean([m["predicted"] == m["actual"] for m in fold_metrics])
        adjacent_acc = np.mean([m["error"] <= 1 for m in fold_metrics])

        # Create confusion matrix
        confusion_matrix = self._create_confusion_matrix(predictions, actuals)

        return CVResult(
            method="Leave-One-Out",
            n_folds=len(fold_metrics),
            mean_absolute_error=mae,
            ordinal_accuracy=accuracy,
            adjacent_accuracy=adjacent_acc,
            grade_confusion_matrix=confusion_matrix,
            fold_metrics=fold_metrics,
            ja24_predictions=ja24_preds,
        )

    def k_fold_cv(
        self, ratings_df: pd.DataFrame, n_folds: int = 5, stratified: bool = True
    ) -> CVResult:
        """Perform K-fold cross-validation.

        Args:
            ratings_df: DataFrame with columns [essay_id, rater_id, grade]
            n_folds: Number of folds
            stratified: Whether to use stratification

        Returns:
            Cross-validation results
        """
        # Prepare essay-level data for splitting
        essay_data = self._prepare_essay_data(ratings_df)

        if stratified:
            # Use median grade for stratification
            splitter = StratifiedKFold(n_splits=n_folds, shuffle=True, random_state=42)
            splits = splitter.split(essay_data["essay_id"], essay_data["median_grade_numeric"])
        else:
            splitter = KFold(n_splits=n_folds, shuffle=True, random_state=42)
            splits = splitter.split(essay_data["essay_id"])

        predictions = []
        actuals = []
        fold_metrics = []
        ja24_preds = []

        for fold, (train_idx, test_idx) in enumerate(splits, 1):
            print(f"K-Fold CV: Processing fold {fold}/{n_folds}")

            # Get train/test essays
            train_essays = essay_data.iloc[train_idx]["essay_id"].values
            test_essays = essay_data.iloc[test_idx]["essay_id"].values

            # Split ratings
            train_df = ratings_df[ratings_df["essay_id"].isin(train_essays)]
            test_df = ratings_df[ratings_df["essay_id"].isin(test_essays)]

            if len(train_df) < 10:
                continue

            try:
                # Fit model
                model = ImprovedBayesianModel(self.model_config)
                model.fit(train_df)

                # Predict test essays
                for test_essay in test_essays:
                    test_essay_df = test_df[test_df["essay_id"] == test_essay]

                    # Get true grade
                    test_grades = test_essay_df["grade"].apply(lambda x: x[0] if x else None)
                    true_grade = test_grades.mode()[0] if len(test_grades) > 0 else "C"

                    # Get prediction
                    test_ratings = {
                        row["rater_id"]: row["grade"] for _, row in test_essay_df.iterrows()
                    }

                    pred_result = model.predict_new_essay(test_ratings)
                    pred_grade = pred_result.consensus_grade

                    predictions.append(pred_grade)
                    actuals.append(true_grade)

                    if test_essay == "JA24":
                        ja24_preds.append(pred_grade)

                    # Calculate error
                    error = abs(
                        self.GRADE_VALUES.get(pred_grade, 3) - self.GRADE_VALUES.get(true_grade, 3)
                    )

                    fold_metrics.append(
                        {
                            "fold": fold,
                            "essay": test_essay,
                            "predicted": pred_grade,
                            "actual": true_grade,
                            "error": error,
                        }
                    )

            except Exception as e:
                print(f"Error in fold {fold}: {e}")
                continue

        # Calculate overall metrics
        mae = np.mean([m["error"] for m in fold_metrics])
        accuracy = np.mean([m["predicted"] == m["actual"] for m in fold_metrics])
        adjacent_acc = np.mean([m["error"] <= 1 for m in fold_metrics])

        # Create confusion matrix
        confusion_matrix = self._create_confusion_matrix(predictions, actuals)

        return CVResult(
            method=f"{n_folds}-Fold {'Stratified' if stratified else ''}",
            n_folds=n_folds,
            mean_absolute_error=mae,
            ordinal_accuracy=accuracy,
            adjacent_accuracy=adjacent_acc,
            grade_confusion_matrix=confusion_matrix,
            fold_metrics=fold_metrics,
            ja24_predictions=ja24_preds,
        )

    def _prepare_essay_data(self, ratings_df: pd.DataFrame) -> pd.DataFrame:
        """Prepare essay-level data for stratification.

        Args:
            ratings_df: Raw ratings data

        Returns:
            Essay-level DataFrame with median grades
        """
        essay_data = []

        for essay_id, group in ratings_df.groupby("essay_id"):
            # Get median grade for stratification
            grades = group["grade"].apply(lambda x: x[0] if x else None)
            numeric_grades = [self.GRADE_VALUES.get(g, 3) for g in grades if g]

            if numeric_grades:
                median_grade = float(np.median(numeric_grades))
            else:
                median_grade = 3.0  # Default to C

            essay_data.append(
                {
                    "essay_id": essay_id,
                    "n_ratings": len(group),
                    "median_grade_numeric": int(median_grade),
                }
            )

        return pd.DataFrame(essay_data)

    def _create_confusion_matrix(self, predictions: List[str], actuals: List[str]) -> pd.DataFrame:
        """Create confusion matrix for ordinal predictions.

        Args:
            predictions: List of predicted grades
            actuals: List of actual grades

        Returns:
            Confusion matrix as DataFrame
        """
        # Initialize matrix
        matrix = pd.DataFrame(
            0, index=self.SWEDISH_GRADES, columns=self.SWEDISH_GRADES, dtype=int
        )

        # Fill matrix
        for pred, actual in zip(predictions, actuals):
            if pred in self.SWEDISH_GRADES and actual in self.SWEDISH_GRADES:
                matrix.loc[actual, pred] += 1

        return matrix

    def evaluate_model(self, ratings_df: pd.DataFrame, method: str = "loo") -> CVResult:
        """Evaluate model using specified CV method.

        Args:
            ratings_df: DataFrame with ratings
            method: "loo" for leave-one-out, "kfold" for k-fold

        Returns:
            Cross-validation results
        """
        if method == "loo":
            return self.leave_one_out_cv(ratings_df)
        elif method == "kfold":
            return self.k_fold_cv(ratings_df, n_folds=5)
        else:
            raise ValueError(f"Unknown CV method: {method}")

    def generate_cv_report(self, cv_result: CVResult) -> str:
        """Generate detailed CV report.

        Args:
            cv_result: Cross-validation results

        Returns:
            Markdown-formatted report
        """
        report = [f"# Cross-Validation Report: {cv_result.method}\n\n"]

        # Overall metrics
        report.append("## Overall Performance\n")
        report.append(f"- **Mean Absolute Error**: {cv_result.mean_absolute_error:.2f} grades\n")
        report.append(f"- **Exact Accuracy**: {cv_result.ordinal_accuracy:.1%}\n")
        report.append(f"- **Adjacent Accuracy**: {cv_result.adjacent_accuracy:.1%}\n")
        report.append(f"- **Number of Folds**: {cv_result.n_folds}\n\n")

        # JA24 predictions
        if cv_result.ja24_predictions:
            report.append("## JA24 Case Predictions\n")
            pred_counts = pd.Series(cv_result.ja24_predictions).value_counts()
            report.append("Predictions across folds:\n")
            for grade, count in pred_counts.items():
                report.append(f"- {grade}: {count} times\n")
            report.append("\n")

        # Confusion matrix
        report.append("## Confusion Matrix\n")
        report.append("```\n")
        report.append(cv_result.grade_confusion_matrix.to_string())
        report.append("\n```\n\n")

        # Per-fold performance
        if len(cv_result.fold_metrics) <= 20:
            report.append("## Detailed Fold Results\n")
            fold_df = pd.DataFrame(cv_result.fold_metrics)
            report.append(fold_df.to_markdown(index=False))

        return "".join(report)
