Awesome — thanks for sharing the real code. Below is a **clean, end-to-end redesign** that removes the heuristic confidence, adds **analytical standard errors** for Bradley–Terry, **anchor-driven calibration**, and **per-essay grade probability distributions** — all wired into your existing DDD layout.

I’ve written this as **concrete patches** for Claude to evaluate and review:

---

# What you get after this change

For every essay in a CJ batch (students + anchors):

* `bt_mean`: Bradley–Terry ability (already computed via `choix`)
* `bt_se`: analytical **standard error** for `bt_mean`
* `grade_centers`: median BT ability per anchor grade (A…F)
* `grade_boundaries`: midpoints between adjacent anchor centers
* `grade_probs`: probability distribution across grades for each **student** essay (Normal approx, `N(bt_mean, bt_se²)`)
* `projected_grade`: argmax of `grade_probs`
* Optional **confidence label** now derived from distribution entropy (no bonuses or ad hoc weights)

All this is produced **inside CJ Assessment Service** and sent to RAS via `CJAssessmentCompletedV1`.

---

## 0) Dependencies (add once)

Add SciPy for the Normal CDF:

```
scipy>=1.11
```

(If you keep a `pyproject.toml` or `requirements.txt`, include it there.)

---

## 1) Database model updates

We persist SE’s and anchor flags on essays, and keep richer projection metadata.

### 1.1 `services/cj_assessment_service/models_db.py`

Add two columns to `ProcessedEssay`:

```python
class ProcessedEssay(Base):
    ...
    current_bt_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    current_bt_se: Mapped[float | None] = mapped_column(Float, nullable=True)  # NEW
    comparison_count: Mapped[int] = mapped_column(default=0, nullable=False)

    # Identify anchors in-batch
    is_anchor: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("FALSE"))  # NEW
```

> **Migration**: add `current_bt_se FLOAT NULL` and `is_anchor BOOLEAN NOT NULL DEFAULT FALSE`.

No other tables need schema changes — we’ll reuse `GradeProjection.calculation_metadata` for rich output.

---

## 2) Bradley–Terry with analytical SEs (Choix + Fisher information)

Create a dedicated inference helper and wire it into scoring.

### 2.1 NEW: `services/cj_assessment_service/cj_core_logic/bt_inference.py`

```python
from __future__ import annotations
import numpy as np
from numpy.linalg import pinv

def compute_bt_standard_errors(
    n_items: int,
    pairs: list[tuple[int, int]],  # (winner_idx, loser_idx)
    theta: np.ndarray,
) -> np.ndarray:
    """
    Analytical SE for Bradley–Terry abilities via Fisher information (negative Hessian).
    Uses a reference parameter for identifiability and Moore–Penrose inverse for stability.
    """
    assert theta.shape == (n_items,)
    ref = n_items - 1
    active = [i for i in range(n_items) if i != ref]
    H = np.zeros((n_items - 1, n_items - 1), dtype=float)

    for w, l in pairs:
        tw, tl = theta[w], theta[l]
        # P(w > l) under BT
        ew, el = np.exp(tw), np.exp(tl)
        p = ew / (ew + el)
        v = p * (1.0 - p)  # variance term under logit link

        if w != ref:
            iw = active.index(w)
            H[iw, iw] += v
        if l != ref:
            il = active.index(l)
            H[il, il] += v
        if w != ref and l != ref:
            iw = active.index(w); il = active.index(l)
            H[iw, il] -= v
            H[il, iw] -= v

    cov_active = pinv(H)  # robust to near singular
    se = np.zeros(n_items, dtype=float)
    for idx, i in enumerate(active):
        se[i] = float(np.sqrt(max(cov_active[idx, idx], 0.0)))
    se[ref] = 0.0
    return se
```

### 2.2 Update: `services/cj_assessment_service/cj_core_logic/scoring_ranking.py`

* Compute **SEs** after Choix.
* Persist both `current_bt_score` and `current_bt_se`.
* Keep `comparison_count` up to date.

Changes in `record_comparisons_and_update_scores(...)`:

```python
import choix
import numpy as np
from services.cj_assessment_service.cj_core_logic.bt_inference import compute_bt_standard_errors
...
    # Build pairs for Choix
    choix_comparison_data: list[tuple[int,int]] = []
    # Also count comparisons per essay
    per_essay_counts: dict[str, int] = {e.id: 0 for e in all_essays}

    for comp in all_valid_db_comparisons:
        ...
        if result_pair_is_valid:
            choix_comparison_data.append((winner_idx, loser_idx))
            per_essay_counts[winner_id_str] = per_essay_counts.get(winner_id_str, 0) + 1
            per_essay_counts[loser_id_str]  = per_essay_counts.get(loser_id_str, 0) + 1
...
    # 4. Compute BT abilities via Choix
    alpha = 0.01
    params = choix.ilsr_pairwise(n_items, choix_comparison_data, alpha=alpha)
    params -= np.mean(params)

    # 4b. Analytical SE for each ability
    se_vec = compute_bt_standard_errors(n_items, choix_comparison_data, params)

    updated_bt_scores: dict[str, float] = {unique_els_essay_ids[i]: float(params[i]) for i in range(n_items)}
    updated_bt_ses: dict[str, float]    = {unique_els_essay_ids[i]: float(se_vec[i]) for i in range(n_items)}

    # 5. Persist scores, SEs, and comparison counts
    await _update_essay_scores_in_database(
        db_session,
        cj_batch_id,
        updated_bt_scores,
        updated_bt_ses,
        per_essay_counts,
    )
...
```

Replace the helper at bottom to take more fields:

```python
async def _update_essay_scores_in_database(
    db_session: AsyncSession,
    cj_batch_id: int,
    scores: dict[str, float],
    ses: dict[str, float],
    counts: dict[str, int],
) -> None:
    for els_id, score_val in scores.items():
        se_val = ses.get(els_id)
        cnt_val = counts.get(els_id, 0)
        stmt = (
            update(CJ_ProcessedEssay)
            .where(
                CJ_ProcessedEssay.els_essay_id == els_id,
                CJ_ProcessedEssay.cj_batch_id == cj_batch_id,
            )
            .values(
                current_bt_score=score_val,
                current_bt_se=se_val,
                comparison_count=cnt_val,
            )
        )
        await db_session.execute(stmt)
```

### 2.3 Make rankings useful to Grade Projector

Enrich `get_essay_rankings(...)` so `rankings` objects include the fields projector needs:

```python
rankings.append(
    {
        "rank": rank,
        "els_essay_id": db_row.els_essay_id,
        "bradley_terry_score": db_row.current_bt_score,
        "bradley_terry_se": db_row.current_bt_se,
        "comparison_count": db_row.comparison_count,
        "is_anchor": bool(db_row.is_anchor),   # NEW: projector uses this to split sets
    }
)
```

---

## 3) Replace heuristic confidence with anchor-calibrated grade probabilities

We will **remove** `ConfidenceCalculator` and implement **probabilities** + (optional) entropy-based label.

### 3.1 Delete heuristic calculator

Remove imports and usage of `ConfidenceCalculator` in `grade_projector.py`. You can delete `services/cj_assessment_service/cj_core_logic/confidence_calculator.py` entirely (and clean imports).

### 3.2 Update: `services/cj_assessment_service/cj_core_logic/grade_projector.py`

Key changes:

* Use **anchor essays in this batch** (`rankings`) to compute **grade centers** (median per grade) and **boundaries** (midpoints).
* For each **student** essay, compute a **grade probability distribution** using Normal CDF and its `bt_se`.
* Choose `projected_grade = argmax(probs)`.
* Optional label from distribution **entropy** (keeps your HIGH/MID/LOW UX without ad hoc weights).
* Persist everything in `GradeProjection.calculation_metadata`.

```python
from __future__ import annotations
from typing import TYPE_CHECKING, Any, Iterable
from uuid import UUID

import math
import numpy as np
from scipy.stats import norm
from common_core.events.cj_assessment_events import GradeProjectionSummary
from huleedu_service_libs.logging_utils import create_service_logger
from sqlalchemy.ext.asyncio import AsyncSession

from services.cj_assessment_service.cj_core_logic.context_builder import (
    AssessmentContext,
    ContextBuilder,
)
from services.cj_assessment_service.models_db import GradeProjection
from services.cj_assessment_service.protocols import ContentClientProtocol

logger = create_service_logger("cj_assessment.grade_projector")

GRADE_ORDER = ["F","E-","E+","D","D+","C-","C+","B","A"]

class GradeProjector:
    def __init__(self) -> None:
        # if you require anchors to project at all, set min_anchors_required=1
        self.context_builder = ContextBuilder(min_anchors_required=0)
        self.logger = logger

    async def calculate_projections(
        self,
        session: AsyncSession,
        rankings: list[dict[str, Any]],
        cj_batch_id: int,
        assignment_id: str | None,
        course_code: str,
        content_client: ContentClientProtocol,
        correlation_id: UUID,
    ) -> GradeProjectionSummary:
        self.logger.info("Starting grade projection calculation",
            extra={"correlation_id": str(correlation_id), "cj_batch_id": cj_batch_id, "essay_count": len(rankings), "assignment_id": assignment_id}
        )

        if not rankings:
            return GradeProjectionSummary(
                projections_available=False,
                primary_grades={},
                confidence_labels={},
                confidence_scores={},
                # new fields added below in event model
                grade_probabilities={},
                calibration_info={},
                bt_stats={},
            )

        # Build context (instructions + anchor refs); we do not fetch anchor text here
        context = await self.context_builder.build(
            session=session,
            assignment_id=assignment_id,
            course_code=course_code,
            content_client=content_client,
            correlation_id=correlation_id,
        )

        # Split essays: we rely on rankings entries having is_anchor flags
        anchors = [r for r in rankings if r.get("is_anchor") is True]
        students = [r for r in rankings if not r.get("is_anchor")]

        if not anchors:
            self.logger.info("No anchor essays present in batch — skipping projections", extra={"correlation_id": str(correlation_id)})
            return GradeProjectionSummary(
                projections_available=False,
                primary_grades={},
                confidence_labels={},
                confidence_scores={},
                grade_probabilities={},
                calibration_info={},
                bt_stats={},
            )

        # Compute grade centers and boundaries from anchor BT means
        grade_centers, grade_boundaries = self._compute_calibration_from_anchors(anchors, context)

        # Calculate projections
        primary_grades: dict[str, str] = {}
        confidence_labels: dict[str, str] = {}
        confidence_scores: dict[str, float] = {}
        grade_probabilities: dict[str, dict[str, float]] = {}
        bt_stats: dict[str, dict[str, float]] = {}

        for r in students:
            essay_id = r["els_essay_id"]
            mu = float(r.get("bradley_terry_score") or 0.0)
            se = float(r.get("bradley_terry_se") or 0.0)

            probs = self._grade_probs(mu, se, grade_boundaries)
            grade_probabilities[essay_id] = probs
            proj = max(probs.items(), key=lambda kv: kv[1])[0]
            primary_grades[essay_id] = proj

            # entropy-based confidence (optional — no ad hoc weights)
            Hn = self._normalized_entropy(probs)
            label, score = self._label_from_entropy(Hn)
            confidence_labels[essay_id] = label
            confidence_scores[essay_id] = score

            bt_stats[essay_id] = {"bt_mean": mu, "bt_se": se}

        # Persist projections
        await self._store_projections(
            session,
            cj_batch_id,
            students,
            primary_grades,
            confidence_labels,
            confidence_scores,
            grade_probabilities,
            grade_centers,
            grade_boundaries,
            context,
        )

        return GradeProjectionSummary(
            projections_available=True,
            primary_grades=primary_grades,
            confidence_labels=confidence_labels,
            confidence_scores=confidence_scores,
            grade_probabilities=grade_probabilities,
            calibration_info={
                "grade_centers": grade_centers,
                "grade_boundaries": grade_boundaries,
                "context_source": context.context_source,
                "anchor_count": len(anchors),
            },
            bt_stats=bt_stats,
        )

    # ---- calibration & probability helpers ----

    def _compute_calibration_from_anchors(
        self,
        anchors: list[dict[str, Any]],
        context: AssessmentContext,
    ) -> tuple[dict[str, float], dict[tuple[str,str], float]]:
        """
        Returns (grade_centers, grade_boundaries).
        centers[g] = median BT mean for anchors of grade g
        boundaries[(g_lo, g_hi)] = midpoint between centers
        """
        # Map anchor essay id -> grade using ContextBuilder's anchor refs
        # If your batch already marks is_anchor and carries a grade per anchor in processing_metadata,
        # replace this join with that. Otherwise, we infer grade from anchor refs by text_storage_id mapping.
        # Here we expect `anchors` to carry a 'anchor_grade' in their ranking dict if you have it.
        by_grade: dict[str, list[float]] = {g: [] for g in GRADE_ORDER}

        # Try to infer grade per anchor ranking row:
        # The clean approach is to store anchor grade into ProcessedEssay.processing_metadata at insertion time,
        # then expose it in the rankings dict. If that’s not yet in place, wire it when you enqueue anchors.
        for a in anchors:
            g = a.get("anchor_grade")
            if g in by_grade and a.get("bradley_terry_score") is not None:
                by_grade[g].append(float(a["bradley_terry_score"]))

        centers: dict[str, float] = {}
        for g, vals in by_grade.items():
            centers[g] = float(np.median(vals)) if vals else float("nan")

        boundaries: dict[tuple[str, str], float] = {}
        prev_center = None; prev_grade = None
        for g in GRADE_ORDER:
            c = centers.get(g)
            if prev_center is not None and not (math.isnan(prev_center) or math.isnan(c)):
                boundaries[(prev_grade, g)] = 0.5 * (prev_center + c)
            prev_center, prev_grade = c, g

        return centers, boundaries

    def _grade_probs(
        self,
        mu: float,
        se: float,
        boundaries: dict[tuple[str,str], float],
    ) -> dict[str, float]:
        # Build edges from boundaries (−inf .. +inf)
        edges: dict[str, tuple[float, float]] = {}
        lower = -np.inf
        for lo, hi in zip(GRADE_ORDER[:-1], GRADE_ORDER[1:]):
            cut = boundaries.get((lo, hi))
            edges[lo] = (lower, cut if cut is not None else lower)
            lower = cut if cut is not None else lower
        edges[GRADE_ORDER[-1]] = (lower, np.inf)

        sigma = max(se, 1e-9)
        probs: dict[str, float] = {}
        for g in GRADE_ORDER:
            a, b = edges[g]
            p = float(norm.cdf((b - mu) / sigma) - norm.cdf((a - mu) / sigma))
            probs[g] = max(min(p, 1.0), 0.0)

        Z = sum(probs.values()) or 1.0
        for g in probs:
            probs[g] /= Z
        return probs

    def _normalized_entropy(self, probs: dict[str, float]) -> float:
        p = [max(min(v, 1.0), 1e-12) for v in probs.values()]
        H = -sum(x * math.log(x) for x in p)
        return H / math.log(len(p))  # 0..1

    def _label_from_entropy(self, Hn: float) -> tuple[str, float]:
        # Lower entropy ⇒ more certain. Map entropy to a human-friendly score.
        if Hn < 0.35:
            return "HIGH", 1.0 - Hn
        if Hn < 0.65:
            return "MID", 1.0 - Hn
        return "LOW", 1.0 - Hn

    async def _store_projections(
        self,
        session: AsyncSession,
        cj_batch_id: int,
        students: list[dict[str, Any]],
        primary_grades: dict[str, str],
        confidence_labels: dict[str, str],
        confidence_scores: dict[str, float],
        grade_probabilities: dict[str, dict[str, float]],
        grade_centers: dict[str, float],
        grade_boundaries: dict[tuple[str,str], float],
        context: AssessmentContext,
    ) -> None:
        if not students:
            return
        projections = []
        for r in students:
            essay_id = r["els_essay_id"]
            projections.append(
                GradeProjection(
                    els_essay_id=essay_id,
                    cj_batch_id=cj_batch_id,
                    primary_grade=primary_grades[essay_id],
                    confidence_score=confidence_scores[essay_id],
                    confidence_label=confidence_labels[essay_id],
                    calculation_metadata={
                        "bt_mean": float(r.get("bradley_terry_score") or 0.0),
                        "bt_se": float(r.get("bradley_terry_se") or 0.0),
                        "grade_probabilities": grade_probabilities[essay_id],
                        "grade_centers": grade_centers,
                        "grade_boundaries": {f"{a}|{b}": v for (a,b), v in grade_boundaries.items()},
                        "context_source": context.context_source,
                    },
                )
            )
        session.add_all(projections)
        await session.flush()
```

> **Note:** this expects `rankings` to carry `is_anchor` and (ideally) `anchor_grade` for anchor rows. See §4 below for how to ensure that.

---

## 4) Make anchors first-class citizens in the batch

Your `ContextBuilder` fetches anchor **references**. To calibrate on their BT positions, anchors must be **in the batch** and flagged.

* When you seed the batch in your orchestration (where you create `CJ_ProcessedEssay` rows), also insert the anchors as `ProcessedEssay` rows with:

  * `is_anchor=True`
  * `assessment_input_text` = fetched anchor text (you already have `ContentClientImpl`)
  * `processing_metadata` should include their **true grade** as `"anchor_grade": "B"` (etc.)

This lets the LLM compare *students vs anchors* inside the same flow. After comparisons + BT scoring, anchors get `current_bt_score/current_bt_se` just like students, and then the projector can calibrate.

If you don’t already seed anchors, add a small step right after you build context:

* In the workflow that builds `all_essays` for `pair_generation`, append anchors pulled from `ContextBuilder.anchor_contents` with synthetic `els_essay_id`s and `is_anchor=True`. Persist them using the existing repository `create_or_update_cj_processed_essay(...)`, adding an overload or metadata param to mark anchors and anchor grade.

Also, ensure `get_essay_rankings(...)` includes `is_anchor` (and if you add `anchor_grade` into `ProcessedEssay.processing_metadata`, expose it in the ranking dict).

---

## 5) Event contract: return richer data to RAS

Extend `GradeProjectionSummary` to include probabilities, calibration info and bt stats. (You said no backward-compat policy, so we can evolve the schema now.)

### 5.1 `libs/common_core/src/common_core/events/cj_assessment_events.py`

Add fields:

```python
class GradeProjectionSummary(BaseModel):
    projections_available: bool = Field(default=False, ...)
    primary_grades: dict[str, str] = Field(...)
    confidence_labels: dict[str, str] = Field(...)
    confidence_scores: dict[str, float] = Field(...)

    # NEW: raw probability distribution per essay_id
    grade_probabilities: dict[str, dict[str, float]] = Field(
        default_factory=dict,
        description="Per-essay probability over grades (e.g. {'uuid': {'C+':0.42, 'C-':0.33, ...}})"
    )
    # NEW: calibration details used for this batch
    calibration_info: dict[str, Any] = Field(
        default_factory=dict,
        description="Centers and boundaries derived from anchors used for projection"
    )
    # NEW: per-essay bt stats (bt_mean, bt_se)
    bt_stats: dict[str, dict[str, float]] = Field(
        default_factory=dict,
        description="Per-essay BT statistics {'uuid': {'bt_mean':..., 'bt_se':...}}"
    )
```

`CJAssessmentCompletedV1` type stays the same; it embeds `GradeProjectionSummary`.

RAS can decide whether to display just the top grade or the full distribution.

---

## 6) Remove the legacy confidence file and its imports

* Delete: `services/cj_assessment_service/cj_core_logic/confidence_calculator.py`
* Remove imports/usages from `grade_projector.py`

---

## 7) Surface comparison\_count correctly (optional but recommended)

You already have `comparison_count` on `ProcessedEssay`. In §2.2 we incremented counts when building `choix_comparison_data`. If you also track counts when **submitting** pairs (pre-result), keep that, but **the authoritative count for confidence** should be the number of *completed* valid comparisons (as we do when we record results).

---

## 8) Pair generation: ensure anchors are mixed fairly

No code shown for `pair_generation.py`, but for calibration quality:

* Guarantee each student meets at least **k** anchors spread across adjacent grades (e.g., 3–4 pairings).
* Ensure anchors also meet each other enough to “lock” centers.

This improves the stability of `grade_centers` and shrinks student SEs.

---

## 9) Testing checklist (unit/integration)

* **No anchors** → `projections_available=False`, new fields empty.
* **Anchors present with grades across A..F** → boundaries monotone, probabilities sum to 1.
* **Large SE** → entropy increases, label shifts to MID/LOW.
* **More comparisons** → SE ↓, entropy ↓, probabilities concentrate.
* **Anchor scarcity in a band** → centers unstable; you can reflect that by showing larger boundary uncertainty in `calibration_info` later if desired.

---

## 10) Example end-to-end flow after patch

1. CJ compares (students + anchors); results stored.
2. `record_comparisons_and_update_scores()` calls Choix, computes `bt_mean` **and** `bt_se`, persists both.
3. Rankings fetched now include `is_anchor`, `bradley_terry_se`, `comparison_count`.
4. Projector:

   * builds `grade_centers` (median anchor BT per grade),
   * builds `grade_boundaries` (midpoints),
   * creates `grade_probs` for every student via Normal CDF,
   * picks `projected_grade` = argmax,
   * derives entropy-based label (no bonuses),
   * persists projections with rich `calculation_metadata`.
5. Publishes `CJAssessmentCompletedV1` including probabilities, calibration and bt stats.
6. RAS renders either **top grade + confidence** or the full **probability chart**.

---

## 11) What you need to wire where (quick map)

* **New file**: `cj_core_logic/bt_inference.py` (Fisher SEs)
* **Modify**: `scoring_ranking.py` (compute/persist SEs + counts, richer rankings)
* **Modify**: `grade_projector.py` (remove heuristic, add centers/boundaries, probs, entropy)
* **Delete**: `cj_core_logic/confidence_calculator.py`
* **Modify model**: `ProcessedEssay` (+`current_bt_se`, `is_anchor`)
* **Event model**: `GradeProjectionSummary` (+`grade_probabilities`, `calibration_info`, `bt_stats`)
* **(Orchestration)**: Ensure anchors are inserted in the batch as `ProcessedEssay` with `is_anchor=True` and a stored `anchor_grade` (e.g., in `processing_metadata`) so rankings can expose it.

Your current generator is an all-pairs loop with an early “new pairs” cap, so it:

* doesn’t guarantee **every student** meets **enough anchors**,
* can waste capacity on **anchor↔anchor** or **redundant** student↔student pairs,
* and doesn’t diversify anchor grades.

Below is a **drop-in replacement** for `pair_generation.py` that:

1. prioritizes **student↔anchor** pairs (configurable `ANCHOR_TARGET_PER_STUDENT`),
2. diversifies anchor picks across the grade spectrum,
3. adds a small backbone of **anchor↔anchor** pairs (`ANCHOR_BACKBONE_PAIRS`) to lock centers,
4. fills the remaining budget with **student↔student** round-robin pairs,
5. respects existing pairs and the `max_new_pairs` budget deterministically.

> Assumptions (consistent with your redesign):
> • `EssayForComparison` includes `is_anchor: bool` and optional `anchor_grade: str | None`.
> • Anchors are inserted into the batch earlier with `is_anchor=True` and `anchor_grade` set in `processing_metadata`.
> • If you haven’t added those fields yet, add them to `EssayForComparison` (DDD-safe; you said no backwards-compat required).

---

### `services/cj_assessment_service/cj_core_logic/pair_generation.py` (replace file)

```python
"""Pair generation logic for comparative judgment (robust, anchor-first).

Strategy:
1) Student↔Anchor coverage: ensure each student is paired with diversified anchors.
2) Minimal Anchor↔Anchor backbone to stabilize grade centers.
3) Fill with Student↔Student round-robin pairs for local resolution.
All while respecting existing pairs and a max_new_pairs budget.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Iterable, Sequence
from uuid import UUID

from huleedu_service_libs.logging_utils import create_service_logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.cj_assessment_service.models_api import ComparisonTask, EssayForComparison
from services.cj_assessment_service.models_db import ComparisonPair as CJ_ComparisonPair

logger = create_service_logger("cj_assessment_service.pair_generation")

# ---- Tuning knobs (env-configurable later if desired) ----
ANCHOR_TARGET_PER_STUDENT = 4           # how many distinct anchor matches per student per wave
ANCHOR_BACKBONE_PAIRS = 6               # extra anchor↔anchor pairs to “lock” the scale
STUDENT_STUDENT_FALLBACK = 8            # budget for student↔student pairs after coverage
MAX_NEW_PAIRS_DEFAULT = 24              # overall budget for one generation call
DIVERSIFY_GRADES = True                 # spread anchor grades across spectrum if available

# Grade order from lowest to highest – used for diversification buckets
GRADE_ORDER = ["F","E-","E+","D","D+","C-","C+","B","A"]


@dataclass(frozen=True)
class _Pair:
    a: str
    b: str
    def norm(self) -> tuple[str, str]:
        return (self.a, self.b) if self.a <= self.b else (self.b, self.a)


async def generate_comparison_tasks(
    essays_for_comparison: list[EssayForComparison],
    db_session: AsyncSession,
    cj_batch_id: int,
    existing_pairs_threshold: int = MAX_NEW_PAIRS_DEFAULT,  # kept name to avoid ripple effects
    correlation_id: UUID | None = None,
) -> list[ComparisonTask]:
    """
    Generate comparison tasks prioritizing student↔anchor coverage, with
    optional anchor backbone and student↔student fallback, avoiding duplicates.
    """
    n = len(essays_for_comparison)
    if n < 2:
        logger.warning("Need at least 2 essays; got %d", n)
        return []

    logger.info(
        "Generating comparison tasks (anchor-first) for %d essays",
        n,
        extra={"correlation_id": correlation_id, "cj_batch_id": cj_batch_id, "essay_count": n},
    )

    existing = await _fetch_existing_comparison_ids(db_session, cj_batch_id)
    budget = max(0, int(existing_pairs_threshold))
    tasks: list[ComparisonTask] = []
    planned: set[tuple[str, str]] = set()

    # Split pools
    anchors = [e for e in essays_for_comparison if getattr(e, "is_anchor", False)]
    students = [e for e in essays_for_comparison if not getattr(e, "is_anchor", False)]

    if not anchors:
        logger.info("No anchors in batch; generating student↔student only", extra={"cj_batch_id": cj_batch_id})
        return _emit_tasks_student_student_only(students, existing, budget)

    # 1) Student ↔ Anchor coverage
    sxa_pairs = _plan_student_anchor_pairs(
        students=students,
        anchors=anchors,
        existing=existing,
        budget=budget,
        diversify=DIVERSIFY_GRADES,
        target_per_student=ANCHOR_TARGET_PER_STUDENT,
    )
    _append_tasks(tasks, planned, sxa_pairs, existing, budget, "student↔anchor")

    if len(tasks) >= budget:
        return tasks

    # 2) Minimal Anchor ↔ Anchor backbone
    axa_pairs = _plan_anchor_backbone_pairs(
        anchors=anchors,
        existing=existing,
        budget=min(ANCHOR_BACKBONE_PAIRS, budget - len(tasks)),
    )
    _append_tasks(tasks, planned, axa_pairs, existing, budget, "anchor↔anchor")

    if len(tasks) >= budget:
        return tasks

    # 3) Fill with Student ↔ Student pairs (round-robin)
    sxs_pairs = _plan_student_student_pairs(
        students=students,
        existing=existing,
        budget=min(STUDENT_STUDENT_FALLBACK, budget - len(tasks)),
    )
    _append_tasks(tasks, planned, sxs_pairs, existing, budget, "student↔student")

    logger.info(
        "Generated %d new comparison tasks (budget=%d)",
        len(tasks),
        budget,
        extra={"correlation_id": correlation_id, "cj_batch_id": cj_batch_id, "task_count": len(tasks)},
    )
    return tasks


async def _fetch_existing_comparison_ids(
    db_session: AsyncSession,
    cj_batch_id: int,
) -> set[tuple[str, str]]:
    """Return normalized (a,b) ids for existing comparisons in this batch."""
    logger.debug("Fetching existing comparison pairs for CJ Batch ID: %s", cj_batch_id, extra={"cj_batch_id": str(cj_batch_id)})
    stmt = select(CJ_ComparisonPair.essay_a_els_id, CJ_ComparisonPair.essay_b_els_id).where(
        CJ_ComparisonPair.cj_batch_id == cj_batch_id,
    )
    result = await db_session.execute(stmt)
    normalized: set[tuple[str, str]] = set()
    for id_a, id_b in result.all():
        normalized.add(tuple(sorted((id_a, id_b))))
    logger.debug("Found %d existing normalized pairs", len(normalized), extra={"cj_batch_id": str(cj_batch_id)})
    return normalized


# ---------------- planning helpers ---------------- #

def _plan_student_anchor_pairs(
    students: Sequence[EssayForComparison],
    anchors: Sequence[EssayForComparison],
    existing: set[tuple[str, str]],
    budget: int,
    diversify: bool,
    target_per_student: int,
) -> list[_Pair]:
    if not students or not anchors or budget <= 0 or target_per_student <= 0:
        return []

    # Bucket anchors by grade to diversify
    by_grade: dict[str, list[EssayForComparison]] = defaultdict(list)
    for a in anchors:
        g = getattr(a, "anchor_grade", None)
        if g in GRADE_ORDER:
            by_grade[g].append(a)
        else:
            by_grade["__ungrouped__"].append(a)

    # Build a rotating queue of grades to spread picks
    grade_cycle = deque([g for g in GRADE_ORDER if by_grade.get(g)])
    if by_grade.get("__ungrouped__"):
        grade_cycle.append("__ungrouped__")

    planned: list[_Pair] = []
    remaining_budget = budget

    # Greedily give each student up to target_per_student anchor matches
    for s in students:
        if remaining_budget <= 0:
            break

        seen_anchor_ids: set[str] = set()
        assigned = 0

        # rotate through grade buckets to diversify
        while assigned < target_per_student and remaining_budget > 0 and grade_cycle:
            grade_cycle.rotate(-1)
            g = grade_cycle[0]
            pool = by_grade.get(g, [])
            if not pool:
                # remove empty grade
                empty = grade_cycle.popleft()
                continue

            # pick first anchor in bucket that we haven't paired with s and not existing
            picked = None
            for a in pool:
                pr = _Pair(s.id, a.id).norm()
                if a.id not in seen_anchor_ids and pr not in existing:
                    picked = a
                    break

            if picked is None:
                # this bucket is exhausted for this student; try next grade
                continue

            planned.append(_Pair(s.id, picked.id))
            seen_anchor_ids.add(picked.id)
            assigned += 1
            remaining_budget -= 1

            if remaining_budget <= 0:
                break

    return planned


def _plan_anchor_backbone_pairs(
    anchors: Sequence[EssayForComparison],
    existing: set[tuple[str, str]],
    budget: int,
) -> list[_Pair]:
    if budget <= 0 or len(anchors) < 2:
        return []

    # Chain neighboring grades (A with B, B with C+, ...), then sprinkle random
    by_grade: dict[str, list[EssayForComparison]] = defaultdict(list)
    for a in anchors:
        g = getattr(a, "anchor_grade", None)
        by_grade[g].append(a)

    planned: list[_Pair] = []

    # Neighbor links to connect the scale
    for lo, hi in zip(GRADE_ORDER[:-1], GRADE_ORDER[1:]):
        if budget <= 0:
            break
        if by_grade.get(lo) and by_grade.get(hi):
            a_lo = by_grade[lo][0]
            a_hi = by_grade[hi][0]
            pr = _Pair(a_lo.id, a_hi.id).norm()
            if pr not in existing:
                planned.append(_Pair(a_lo.id, a_hi.id))
                budget -= 1

    # If budget remains, add within-grade or cross-grade extras
    if budget > 0:
        all_ids = [a.id for a in anchors]
        # simple round-robin extras
        for i in range(len(all_ids)):
            if budget <= 0:
                break
            j = (i + 1) % len(all_ids)
            pr = _Pair(all_ids[i], all_ids[j]).norm()
            if pr not in existing:
                planned.append(_Pair(all_ids[i], all_ids[j]))
                budget -= 1

    return planned


def _plan_student_student_pairs(
    students: Sequence[EssayForComparison],
    existing: set[tuple[str, str]],
    budget: int,
) -> list[_Pair]:
    if budget <= 0 or len(students) < 2:
        return []
    # Circle method (round-robin) to avoid O(n^2) explosion, truncated by budget
    ids = [s.id for s in students]
    planned: list[_Pair] = []
    i = 0
    while budget > 0 and i < len(ids):
        a = ids[i]
        b = ids[(i + 1) % len(ids)]
        pr = _Pair(a, b).norm()
        if pr not in existing:
            planned.append(_Pair(a, b))
            budget -= 1
        i += 1
    return planned


def _emit_tasks_student_student_only(
    students: Sequence[EssayForComparison],
    existing: set[tuple[str, str]],
    budget: int,
) -> list[ComparisonTask]:
    pairs = _plan_student_student_pairs(students, existing, budget)
    tasks: list[ComparisonTask] = []
    for p in pairs:
        a = _find(students, p.a)
        b = _find(students, p.b)
        if a and b:
            tasks.append(ComparisonTask(essay_a=a, essay_b=b, prompt=_build_comparison_prompt(a, b)))
    logger.info("Generated %d student↔student tasks (no anchors)", len(tasks))
    return tasks


def _append_tasks(
    out: list[ComparisonTask],
    planned: set[tuple[str, str]],
    pairs: Iterable[_Pair],
    existing: set[tuple[str, str]],
    budget: int,
    phase: str,
) -> None:
    added = 0
    for p in pairs:
        if len(out) >= budget:
            break
        pr = p.norm()
        if pr in existing or pr in planned:
            continue
        a = _find_any(p.a)
        b = _find_any(p.b)
        if not a or not b:
            continue
        out.append(ComparisonTask(essay_a=a, essay_b=b, prompt=_build_comparison_prompt(a, b)))
        planned.add(pr)
        added += 1
    if added:
        logger.info("Phase %s: added %d tasks", phase, added)


# These two helpers rely on EssayForComparison being lightweight value objects
# available in the outer scope of generation. If your DI feeds them differently,
# adapt accordingly (but keep O(1) lookup).
_ID_CACHE: dict[str, EssayForComparison] = {}

def _index_cache(pool: Iterable[EssayForComparison]) -> None:
    for e in pool:
        _ID_CACHE[e.id] = e

def _find(pool: Sequence[EssayForComparison], eid: str) -> EssayForComparison | None:
    for e in pool:
        if e.id == eid:
            return e
    return None

def _find_any(eid: str) -> EssayForComparison | None:
    return _ID_CACHE.get(eid)


def _build_comparison_prompt(essay_a: EssayForComparison, essay_b: EssayForComparison) -> str:
    # Consider injecting assessment instructions here if available.
    return f"""Compare these two essays and determine which is better written.

Essay A (ID: {essay_a.id}):
{essay_a.text_content}

Essay B (ID: {essay_b.id}):
{essay_b.text_content}

Please evaluate based on clarity, structure, argument quality, and writing mechanics.
Respond with JSON indicating the winner, justification, and confidence level (1-5).
"""
```

**Notes & decisions**

* **Anchor-first coverage**: `ANCHOR_TARGET_PER_STUDENT = 4` ensures each student is linked to multiple anchors, which measurably reduces SE and tightens grade boundary estimates.
* **Diversification**: we bucket anchors by `anchor_grade` and rotate buckets so a student doesn’t only meet, say, B-level anchors.
* **Backbone**: a small set of **anchor↔anchor** neighbors helps stabilize the monotonic order of anchor centers even if some students are sparse.
* **Budget**: we respect the `existing_pairs_threshold` (renamed internally to `budget`) as your per-wave cap. If you plan bigger waves, just raise it in the caller.
* **Determinism**: no random here; if you want randomized order, seed and shuffle buckets at the top (optional).
* **Lookups**: a tiny in-module `_ID_CACHE` provides O(1) id→object binding for prompt building.

**What you may need to add elsewhere**

* Ensure `EssayForComparison` exposes `is_anchor: bool` and `anchor_grade: str | None`. If not, extend it (and set these when you insert anchors into the batch).
* Right before calling `generate_comparison_tasks`, call `_index_cache(essays_for_comparison)` once to populate the ID cache (or move that into the function’s first lines).