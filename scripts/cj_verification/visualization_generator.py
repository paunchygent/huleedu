"""Visualization generator for Bayesian model diagnostics.

Creates visualizations showing rating flows (Sankey), severity impacts (heatmaps),
threshold issues, and consensus method comparisons.
"""

from pathlib import Path
from typing import Dict, Optional

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import seaborn as sns


class VisualizationGenerator:
    """Generate diagnostic visualizations for Bayesian model analysis."""

    def __init__(self, output_dir: Optional[Path] = None):
        """Initialize with output directory.

        Args:
            output_dir: Directory for saving plots (default: current directory)
        """
        self.output_dir = Path(output_dir) if output_dir else Path(".")
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Set style
        plt.style.use("seaborn-v0_8-darkgrid")
        sns.set_palette("husl")

    def create_sankey_diagram(
        self,
        raw_ratings: Dict[str, str],
        adjusted_ratings: Dict[str, float],
        final_grade: str,
        essay_id: str = "JA24",
    ) -> go.Figure:
        """Create Sankey diagram showing rating flow from raw to final.

        Args:
            raw_ratings: Dictionary of rater to raw grade
            adjusted_ratings: Dictionary of rater to adjusted numeric score
            final_grade: Final consensus grade
            essay_id: Essay identifier for title

        Returns:
            Plotly Figure object
        """
        # Define nodes
        node_labels = []
        node_colors = []

        # Raw grade nodes
        unique_raw_grades = list(set(raw_ratings.values()))
        for grade in unique_raw_grades:
            node_labels.append(f"Raw: {grade}")
            node_colors.append(self._grade_to_color(grade))

        # Adjusted category nodes
        adjusted_categories = ["Adjusted: Low", "Adjusted: Medium", "Adjusted: High"]
        node_labels.extend(adjusted_categories)
        node_colors.extend(["lightgray", "gray", "darkgray"])

        # Final grade node
        node_labels.append(f"Final: {final_grade}")
        node_colors.append(self._grade_to_color(final_grade))

        # Create links
        source = []
        target = []
        values = []
        link_colors = []

        # Raw to adjusted links
        for rater, raw_grade in raw_ratings.items():
            raw_idx = node_labels.index(f"Raw: {raw_grade}")

            # Categorize adjusted score
            if rater in adjusted_ratings:
                adj_score = adjusted_ratings[rater]
                if adj_score < 10:
                    adj_category = "Adjusted: Low"
                elif adj_score < 12:
                    adj_category = "Adjusted: Medium"
                else:
                    adj_category = "Adjusted: High"

                adj_idx = node_labels.index(adj_category)

                source.append(raw_idx)
                target.append(adj_idx)
                values.append(1)
                link_colors.append("rgba(200,200,200,0.4)")

        # Adjusted to final links
        for category in adjusted_categories:
            if category in node_labels:
                cat_idx = node_labels.index(category)
                final_idx = node_labels.index(f"Final: {final_grade}")

                # Count how many ratings went through this category
                count = sum(1 for s, t in zip(source, target) if t == cat_idx)
                if count > 0:
                    source.append(cat_idx)
                    target.append(final_idx)
                    values.append(count)
                    link_colors.append("rgba(150,150,150,0.4)")

        # Create Sankey diagram
        fig = go.Figure(
            data=[
                go.Sankey(
                    node=dict(
                        pad=15,
                        thickness=20,
                        line=dict(color="black", width=0.5),
                        label=node_labels,
                        color=node_colors,
                    ),
                    link=dict(source=source, target=target, value=values, color=link_colors),
                )
            ]
        )

        fig.update_layout(
            title_text=f"Rating Flow for Essay {essay_id}: Raw Grades → Adjustments → Final Grade",
            font_size=10,
            height=600,
        )

        # Save to file
        output_file = self.output_dir / f"{essay_id}_sankey_diagram.html"
        fig.write_html(str(output_file))

        return fig

    def create_rater_severity_heatmap(
        self, severities_df: pd.DataFrame, ratings_matrix: pd.DataFrame
    ) -> plt.Figure:
        """Create heatmap showing rater severity impacts.

        Args:
            severities_df: DataFrame with rater severities
            ratings_matrix: Matrix of ratings (essays x raters)

        Returns:
            Matplotlib Figure
        """
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10))

        # Create severity map
        severity_map = dict(zip(severities_df["rater"], severities_df["severity"]))

        # Top subplot: Rater severities as horizontal bar chart
        raters = severities_df.sort_values("severity")["rater"].values
        severities = severities_df.sort_values("severity")["severity"].values

        colors = ["green" if s < -0.5 else "red" if s > 0.5 else "gray" for s in severities]
        bars = ax1.barh(range(len(raters)), severities, color=colors)

        ax1.set_yticks(range(len(raters)))
        ax1.set_yticklabels(raters)
        ax1.set_xlabel("Severity Score (Negative = Generous, Positive = Strict)")
        ax1.set_title("Rater Severity Adjustments")
        ax1.axvline(x=0, color="black", linestyle="--", alpha=0.5)
        ax1.grid(True, alpha=0.3)

        # Add value labels
        for i, (bar, val) in enumerate(zip(bars, severities)):
            ax1.text(
                val + 0.05 if val > 0 else val - 0.05,
                bar.get_y() + bar.get_height() / 2,
                f"{val:.2f}",
                va="center",
                ha="left" if val > 0 else "right",
                fontsize=8,
            )

        # Bottom subplot: Impact matrix
        # Create impact matrix showing how each rater's severity affects each essay
        impact_matrix = []
        essay_ids = ratings_matrix.index[:12]  # Limit to first 12 essays

        for essay_id in essay_ids:
            essay_impacts = []
            for rater in raters:
                if pd.notna(ratings_matrix.loc[essay_id, rater]):
                    # Calculate impact as severity * presence of rating
                    impact = severity_map[rater]
                    essay_impacts.append(impact)
                else:
                    essay_impacts.append(np.nan)
            impact_matrix.append(essay_impacts)

        # Create heatmap
        im = ax2.imshow(impact_matrix, cmap="RdBu_r", aspect="auto", vmin=-2, vmax=2)

        ax2.set_xticks(range(len(raters)))
        ax2.set_xticklabels(raters, rotation=45, ha="right")
        ax2.set_yticks(range(len(essay_ids)))
        ax2.set_yticklabels(essay_ids)
        ax2.set_xlabel("Rater")
        ax2.set_ylabel("Essay")
        ax2.set_title("Rater Severity Impact on Each Essay (Red = Strict, Blue = Generous)")

        # Add colorbar
        cbar = plt.colorbar(im, ax=ax2)
        cbar.set_label("Severity Impact")

        plt.tight_layout()

        # Save figure
        output_file = self.output_dir / "rater_severity_heatmap.png"
        fig.savefig(output_file, dpi=150, bbox_inches="tight")

        return fig

    def create_threshold_visualization(self, thresholds_df: pd.DataFrame) -> plt.Figure:
        """Visualize grade thresholds and their spacing.

        Args:
            thresholds_df: DataFrame with threshold values

        Returns:
            Matplotlib Figure
        """
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8))

        thresholds = thresholds_df["tau_k"].values
        grade_labels = thresholds_df["between_grades"].values

        # Top subplot: Threshold positions
        ax1.scatter(thresholds, [0] * len(thresholds), s=100, c="red", zorder=5)

        for i, (thresh, label) in enumerate(zip(thresholds, grade_labels)):
            ax1.annotate(
                label,
                (thresh, 0),
                xytext=(0, 10),
                textcoords="offset points",
                ha="center",
                fontsize=8,
            )

        ax1.set_ylim(-0.5, 0.5)
        ax1.set_xlabel("Threshold Value (Logit Scale)")
        ax1.set_title("Grade Threshold Positions")
        ax1.grid(True, alpha=0.3)
        ax1.set_yticks([])

        # Highlight problematic B to A gap
        b_idx = -2  # Second to last
        a_idx = -1  # Last
        ax1.axvspan(thresholds[b_idx], thresholds[a_idx], alpha=0.2, color="red")
        ax1.text(
            (thresholds[b_idx] + thresholds[a_idx]) / 2,
            -0.3,
            f"B→A Gap: {thresholds[a_idx] - thresholds[b_idx]:.2f}",
            ha="center",
            fontsize=10,
            color="red",
            weight="bold",
        )

        # Bottom subplot: Gap sizes
        gaps = np.diff(thresholds)
        gap_labels = [
            grade_labels[i].split(" | ")[0] + "→" + grade_labels[i].split(" | ")[1]
            for i in range(len(grade_labels) - 1)
        ]

        bars = ax2.bar(range(len(gaps)), gaps, color=["red" if g > 2 else "gray" for g in gaps])
        ax2.set_xticks(range(len(gaps)))
        ax2.set_xticklabels(gap_labels, rotation=45, ha="right")
        ax2.set_ylabel("Gap Size")
        ax2.set_title("Spacing Between Grade Thresholds")
        ax2.axhline(
            y=np.mean(gaps),
            color="blue",
            linestyle="--",
            alpha=0.5,
            label=f"Mean: {np.mean(gaps):.2f}",
        )
        ax2.legend()
        ax2.grid(True, alpha=0.3)

        # Add value labels
        for bar, val in zip(bars, gaps):
            ax2.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 0.05,
                f"{val:.2f}",
                ha="center",
                fontsize=8,
            )

        plt.tight_layout()

        # Save figure
        output_file = self.output_dir / "threshold_visualization.png"
        fig.savefig(output_file, dpi=150, bbox_inches="tight")

        return fig

    def create_consensus_comparison_plot(
        self, methods_df: pd.DataFrame, essay_id: str = "JA24"
    ) -> plt.Figure:
        """Create comparison plot of different consensus methods.

        Args:
            methods_df: DataFrame from compare_all_methods()
            essay_id: Essay identifier for title

        Returns:
            Matplotlib Figure
        """
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))

        # Left plot: Consensus grades
        methods = methods_df["Method"].values
        grades = methods_df["Consensus Grade"].values

        # Convert grades to numeric for plotting
        grade_numeric = []
        for grade in grades:
            if grade == "ERROR":
                grade_numeric.append(-1)
            else:
                grade_numeric.append(self._grade_to_numeric(grade))

        colors = ["green" if g >= 12 else "orange" if g >= 10 else "red" for g in grade_numeric]
        bars = ax1.bar(range(len(methods)), grade_numeric, color=colors)

        ax1.set_xticks(range(len(methods)))
        ax1.set_xticklabels(methods, rotation=45, ha="right")
        ax1.set_ylabel("Consensus Grade (Numeric)")
        ax1.set_title(f"Consensus Grades by Method - Essay {essay_id}")
        ax1.set_ylim(-2, 15)

        # Add grade labels
        for bar, grade, num in zip(bars, grades, grade_numeric):
            if num >= 0:
                ax1.text(
                    bar.get_x() + bar.get_width() / 2,
                    bar.get_height() + 0.2,
                    grade,
                    ha="center",
                    fontsize=10,
                    weight="bold",
                )

        # Add reference lines
        ax1.axhline(y=12, color="blue", linestyle="--", alpha=0.3, label="B threshold")
        ax1.axhline(y=14, color="green", linestyle="--", alpha=0.3, label="A threshold")
        ax1.legend()

        # Right plot: Confidence scores
        confidences = methods_df["Confidence"].values
        bars2 = ax2.bar(
            range(len(methods)),
            confidences,
            color=["green" if c > 0.7 else "orange" if c > 0.5 else "red" for c in confidences],
        )

        ax2.set_xticks(range(len(methods)))
        ax2.set_xticklabels(methods, rotation=45, ha="right")
        ax2.set_ylabel("Confidence Score")
        ax2.set_title("Method Confidence Scores")
        ax2.set_ylim(0, 1.1)
        ax2.axhline(y=0.7, color="green", linestyle="--", alpha=0.3, label="High confidence")
        ax2.axhline(y=0.5, color="orange", linestyle="--", alpha=0.3, label="Medium confidence")
        ax2.legend()

        # Add value labels
        for bar, val in zip(bars2, confidences):
            ax2.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 0.01,
                f"{val:.3f}",
                ha="center",
                fontsize=8,
            )

        plt.suptitle(f"Consensus Method Comparison for {essay_id}", fontsize=14, weight="bold")
        plt.tight_layout()

        # Save figure
        output_file = self.output_dir / f"{essay_id}_consensus_comparison.png"
        fig.savefig(output_file, dpi=150, bbox_inches="tight")

        return fig

    def create_ja24_specific_visualization(
        self,
        raw_ratings: Dict[str, str],
        severities: Dict[str, float],
        model_grade: str,
        alternative_grades: Dict[str, str],
    ) -> plt.Figure:
        """Create comprehensive visualization for JA24 case.

        Args:
            raw_ratings: Raw ratings for JA24
            severities: Rater severity scores
            model_grade: Bayesian model's grade
            alternative_grades: Grades from alternative methods

        Returns:
            Matplotlib Figure
        """
        fig = plt.figure(figsize=(16, 10))
        gs = fig.add_gridspec(3, 3, hspace=0.3, wspace=0.3)

        # Top left: Raw rating distribution
        ax1 = fig.add_subplot(gs[0, 0])
        grade_counts = {}
        for grade in raw_ratings.values():
            grade_counts[grade] = grade_counts.get(grade, 0) + 1

        grades = list(grade_counts.keys())
        counts = list(grade_counts.values())
        colors = ["green" if g == "A" else "orange" if g == "B" else "gray" for g in grades]

        ax1.bar(grades, counts, color=colors)
        ax1.set_title("Raw Rating Distribution")
        ax1.set_xlabel("Grade")
        ax1.set_ylabel("Count")

        for i, (grade, count) in enumerate(zip(grades, counts)):
            ax1.text(i, count + 0.1, str(count), ha="center", fontsize=12, weight="bold")

        # Top middle: Rater severities for JA24 raters
        ax2 = fig.add_subplot(gs[0, 1])
        ja24_severities = [(r, severities[r]) for r in raw_ratings.keys() if r in severities]
        ja24_severities.sort(key=lambda x: x[1])

        raters = [r for r, _ in ja24_severities]
        sev_values = [s for _, s in ja24_severities]
        colors = ["green" if s < -0.5 else "red" if s > 0.5 else "gray" for s in sev_values]

        ax2.barh(range(len(raters)), sev_values, color=colors)
        ax2.set_yticks(range(len(raters)))
        ax2.set_yticklabels(raters)
        ax2.set_xlabel("Severity")
        ax2.set_title("JA24 Rater Severities")
        ax2.axvline(x=0, color="black", linestyle="--", alpha=0.5)

        # Top right: Grade by severity
        ax3 = fig.add_subplot(gs[0, 2])
        for rater, grade in raw_ratings.items():
            if rater in severities:
                sev = severities[rater]
                grade_num = self._grade_to_numeric(grade)
                color = "green" if grade == "A" else "orange" if grade == "B" else "gray"
                ax3.scatter(sev, grade_num, s=100, c=color, alpha=0.7)
                ax3.annotate(rater[:5], (sev, grade_num), fontsize=6)

        ax3.set_xlabel("Rater Severity")
        ax3.set_ylabel("Grade Given (Numeric)")
        ax3.set_title("Grade vs Rater Severity")
        ax3.axvline(x=0, color="black", linestyle="--", alpha=0.3)
        ax3.grid(True, alpha=0.3)

        # Middle: All consensus methods comparison
        ax4 = fig.add_subplot(gs[1, :])
        all_grades = {"Bayesian Model": model_grade}
        all_grades.update(alternative_grades)

        methods = list(all_grades.keys())
        grades = list(all_grades.values())
        grade_nums = [self._grade_to_numeric(g) if g != "ERROR" else -1 for g in grades]

        colors = [
            "red" if m == "Bayesian Model" else "green" if grade_nums[i] >= 14 else "orange"
            for i, m in enumerate(methods)
        ]

        bars = ax4.bar(range(len(methods)), grade_nums, color=colors, alpha=0.7)
        ax4.set_xticks(range(len(methods)))
        ax4.set_xticklabels(methods, rotation=45, ha="right")
        ax4.set_ylabel("Consensus Grade (Numeric)")
        ax4.set_title("All Consensus Methods Comparison")
        ax4.axhline(y=14, color="green", linestyle="--", alpha=0.3, label="A")
        ax4.axhline(y=12, color="orange", linestyle="--", alpha=0.3, label="B")
        ax4.legend()

        for bar, grade in zip(bars, grades):
            ax4.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 0.2,
                grade,
                ha="center",
                fontsize=10,
                weight="bold",
            )

        # Bottom: Summary text
        ax5 = fig.add_subplot(gs[2, :])
        ax5.axis("off")

        summary_text = f"""
        ESSAY JA24 ANALYSIS SUMMARY
        ═══════════════════════════
        Raw Ratings: 5 × A, 2 × B
        Expected: A (clear majority)
        Bayesian Model Result: {model_grade}

        KEY FINDINGS:
        • A-raters labeled as "generous" (avg severity: {np.mean([severities[r] for r in raw_ratings if raw_ratings[r] == "A" and r in severities]):.2f})
        • B-raters labeled as "neutral/strict" (avg severity: {np.mean([severities[r] for r in raw_ratings if raw_ratings[r] == "B" and r in severities]):.2f})
        • Model discounts A ratings due to "generous" label → circular reasoning
        • Alternative methods mostly agree on A or high B

        CONCLUSION: The Bayesian model's sum-to-zero constraint and overparameterization
        led to artificial rater adjustments that incorrectly lowered JA24's consensus grade.
        """

        ax5.text(
            0.5,
            0.5,
            summary_text,
            ha="center",
            va="center",
            fontsize=11,
            family="monospace",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="lightyellow"),
        )

        plt.suptitle(
            "JA24 Case Study: Why Did the Model Give B Despite 5A/2B?", fontsize=16, weight="bold"
        )

        # Save figure
        output_file = self.output_dir / "ja24_comprehensive_analysis.png"
        fig.savefig(output_file, dpi=150, bbox_inches="tight")

        return fig

    def _grade_to_numeric(self, grade: str) -> float:
        """Convert grade to numeric value."""
        grade_map = {
            "F": 0,
            "F+": 1,
            "E-": 2,
            "E": 3,
            "E+": 4,
            "D-": 5,
            "D": 6,
            "D+": 7,
            "C-": 8,
            "C": 9,
            "C+": 10,
            "B-": 11,
            "B": 12,
            "B+": 13,
            "A": 14,
        }
        return grade_map.get(grade, -1)

    def _grade_to_color(self, grade: str) -> str:
        """Convert grade to color for visualization."""
        if grade == "A":
            return "darkgreen"
        elif grade in ["B", "B+", "B-"]:
            return "green"
        elif grade in ["C+", "C", "C-"]:
            return "yellow"
        elif grade in ["D+", "D", "D-"]:
            return "orange"
        else:
            return "red"
