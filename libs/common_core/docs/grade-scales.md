# Grade Scales

GRADE_SCALES registry for CJ assessment grade projection.

## Registry

```python
from common_core.grade_scales import GRADE_SCALES, get_scale

GRADE_SCALES: dict[str, GradeScaleMetadata] = {
    "swedish_8_anchor": GradeScaleMetadata(...),
    "eng5_np_legacy_9_step": GradeScaleMetadata(...),
    "eng5_np_national_9_step": GradeScaleMetadata(...),
}
```

## GradeScaleMetadata

```python
@dataclass(frozen=True)
class GradeScaleMetadata:
    scale_id: str                          # Unique identifier
    display_name: str                      # UI display name
    grades: list[str]                      # Ordered lowest to highest
    population_priors: dict[str, float] | None  # Grade distribution
    description: str                       # Purpose and context
    allows_below_lowest: bool              # Can score below lowest anchor
    below_lowest_grade: str | None         # Grade for below-lowest (e.g., "F", "0")
```

## Scale Variants

### swedish_8_anchor

```python
grades: ["F", "E", "D", "D+", "C", "C+", "B", "A"]
allows_below_lowest: False
population_priors: {
    "F": 0.02, "E": 0.08, "D": 0.15, "D+": 0.20,
    "C": 0.25, "C+": 0.15, "B": 0.10, "A": 0.05
}
```

Psychometrically robust, historical Swedish national exam data.

### eng5_np_legacy_9_step

```python
grades: ["F+", "E-", "E+", "D-", "D+", "C-", "C+", "B", "A"]
allows_below_lowest: True
below_lowest_grade: "F"
population_priors: uniform (1/9 per grade)
```

Anchor IDs like "F+1", "F+2" map to grade "F+". Essays below F+ anchor assigned "F".

### eng5_np_national_9_step

```python
grades: ["1", "2", "3", "4", "5", "6", "7", "8", "9"]
allows_below_lowest: True
below_lowest_grade: "0"
population_priors: uniform (1/9 per grade)
```

Numerical scale, essays below "1" anchor assigned "0".

## Functions

### get_scale(scale_id)

```python
from common_core.grade_scales import get_scale

scale = get_scale("swedish_8_anchor")
# Returns: GradeScaleMetadata
# Raises: ValueError if unknown scale_id
```

### validate_grade_for_scale(grade, scale_id)

```python
from common_core.grade_scales import validate_grade_for_scale

is_valid = validate_grade_for_scale("B", "swedish_8_anchor")  # True
is_valid = validate_grade_for_scale("F", "eng5_np_legacy_9_step")  # True (below-lowest)
is_valid = validate_grade_for_scale("Z", "swedish_8_anchor")  # False
```

### get_grade_index(grade, scale_id)

```python
from common_core.grade_scales import get_grade_index

index = get_grade_index("C", "swedish_8_anchor")  # 4 (zero-based from lowest)
index = get_grade_index("F", "eng5_np_legacy_9_step")  # -1 (below-lowest)
```

Returns -1 for below-lowest grades.

### get_uniform_priors(scale_id)

```python
from common_core.grade_scales import get_uniform_priors

priors = get_uniform_priors("swedish_8_anchor")
# Returns: {"F": 0.125, "E": 0.125, ..., "A": 0.125}
```

Equal probability for each grade.

## CJ Assessment Usage

```python
# CJ Assessment Service
from common_core.grade_scales import get_scale

scale = get_scale(assignment.scale_id)

# Validate anchor essays
for anchor in anchor_essays:
    if not validate_grade_for_scale(anchor.grade, scale.scale_id):
        raise ValueError(f"Invalid anchor grade: {anchor.grade}")

# Use priors for Bayesian grade projection
priors = scale.population_priors or get_uniform_priors(scale.scale_id)

# Project grades
for essay in essays:
    projected_grade = project_grade(
        bt_score=essay.bt_score,
        anchor_calibration=calibration,
        priors=priors,
        scale=scale
    )

    # Handle below-lowest
    if scale.allows_below_lowest and essay.bt_score < lowest_anchor_score:
        projected_grade = scale.below_lowest_grade
```

## Related

- `common_core/grade_scales.py` - Implementation
- CJ Assessment Service - Grade projection logic
