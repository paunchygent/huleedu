# CJ Pair Generator TUI - D-Optimal Comparison Design

**Professional-grade tool for generating optimal paired comparison schedules in Comparative Judgment (CJ) assessment.**

## Overview

This application uses **D-optimal experimental design** to automatically generate statistically optimal comparison pairs for CJ assessment sessions. It handles multi-session workflows, anchor-based grading, and produces balanced comparison schedules that maximize Fisher Information for parameter estimation.

### Key Features

- **D-Optimal Design**: Maximizes statistical information (log-determinant of Fisher Information Matrix)
- **Multi-Session Support**: Continuation-aware optimization builds on previous sessions
- **Anchor Integration**: Connects student essays to pre-graded anchor scale
- **Type Balancing**: Automatically allocates student-anchor, student-student, and anchor-anchor pairs
- **Interactive TUI**: Native file dialogs, drag-and-drop support, comprehensive help screen
- **Standalone Binary**: No Python required on target machine (106MB executable)

### Use Cases

1. **Session 1**: Generate initial comparison pairs for teacher raters
2. **Session 2+**: Add new comparisons building on existing data
3. **Anchor Calibration**: Link student essays to pre-graded anchor scale
4. **Multi-Session Assessment**: Iteratively improve parameter estimates across sessions

---

## Installation

### Prerequisites

- Python 3.11+ (for building from source)
- PDM package manager (for building from source)

### Using the Standalone Executable

**Pre-built binary** (recommended for end users):

```bash
# Navigate to project root
cd /path/to/huledu-reboot

# Run the standalone executable
./dist/cj-pair-generator-tui
```

**No Python installation required.** The executable is self-contained (106MB).

### Building from Source

```bash
# From project root
pdm install

# Build standalone executable
bash scripts/build_standalone.sh

# Output: dist/cj-pair-generator-tui
```

### Running from Source (Development)

```bash
# From project root
pdm run python scripts/bayesian_consensus_model/redistribute_tui.py
```

---

## Quick Start

### Session 1: First Assessment Round

1. **Launch the application**:

   ```bash
   ./dist/cj-pair-generator-tui
   ```

2. **Configure parameters**:
   - **Students**: Enter 12 student essay IDs (comma-separated or drag CSV)
   - **Anchors**: Leave default 12-anchor Swedish scale or customize
   - **Total Slots**: `84` (recommended for 12 students)
   - **Max Repetitions**: `3` (allows up to 3 raters per pair)
   - **Include Anchor-Anchor**: `yes` (for first session calibration)
   - **Previous Session CSV**: Leave blank (Session 1)

3. **Generate pairs**: Press `g` (or click Generate button)

4. **Outputs**:
   - `cj_comparison_pairs.csv`: All comparison pairs for Session 1
   - `cj_rater_assignments.csv`: Workload balanced across raters

### Session 2+: Continuation

1. **Load previous session**:
   - **Previous Session CSV**: Drag `session1_comparisons.csv` (containing all judged pairs)

2. **Adjust parameters**:
   - **Total Slots**: `84` (new comparisons to add)
   - **Include Anchor-Anchor**: `no` (adjacency already established)

3. **Generate pairs**: Press `g`

4. **Result**: Optimizer locks previous 58 pairs, adds 84 new pairs optimally

---

## Understanding D-Optimal Design

### What is D-Optimal Optimization?

The optimizer maximizes the **log-determinant of the Fisher Information Matrix**, which:

- **Minimizes** the volume of the confidence ellipsoid for parameter estimates
- **Maximizes** statistical information about essay abilities
- **Balances** comparison types automatically (no manual quotas needed)

### Mathematical Foundation

For Bradley-Terry paired comparisons, the Fisher Information for a design is:

```
M = Σ (eₐ - eᵦ)(eₐ - eᵦ)ᵀ
```

where the sum is over all comparison pairs (a, b).

**Criterion**: Maximize `log|M|` (D-optimality)

**Algorithm**:

1. Greedy forward selection (adds pairs with maximum information gain)
2. Fedorov exchange (swaps pairs to improve design)

**Guarantee**: Achieves ≥63.2% of optimal solution (via submodularity)

### Why It Produces Optimal Type Distribution Automatically

**Key Insight**: The Fisher Information contribution is **type-agnostic**:

- Student-Anchor, Student-Student, and Anchor-Anchor pairs contribute information based on **which essays** are compared, not their labels
- The optimizer naturally balances types by prioritizing:
  1. **High-uncertainty essays** (students need more comparisons than anchors)
  2. **Graph connectivity** (all essays must be reachable)
  3. **Constraint satisfaction** (adjacency, coverage requirements)

**Expected Distribution** (84 comparisons, Session 2):

- **Student-Anchor**: 40-45 pairs (48-54%) - Scale linking (validity)
- **Student-Student**: 28-35 pairs (33-42%) - Precision (reliability)
- **Anchor-Anchor**: 11 pairs (13%) - Scale validation (consistency)

**Trust the optimizer**: Manual type quotas are unnecessary. The D-optimal design automatically finds near-optimal allocation.

---

## Multi-Session Workflow

### Session 1: Establishing Baseline

**Goal**: Create initial comparison graph connecting all students

**Configuration**:

- **Students**: All 12 essay IDs
- **Anchors**: Leave default or customize
- **Total Slots**: 84 (7× number of students)
- **Max Repetitions**: 3
- **Include Anchor-Anchor**: `yes` (establishes anchor ladder)
- **Previous Session CSV**: Leave blank

**Expected Output**:

- 58-65 comparisons (after optimizer removes infeasible pairs)
- All students connected in comparison graph
- Anchor adjacency ladder established (11 pairs)

**Quality Metrics** (after Session 1):

- Standard Error (SE): 0.12-0.39 (moderate precision)
- Confidence: Low-Medium (insufficient for grading)
- Grade projection: NOT YET POSSIBLE (no student-anchor connections)

### Session 2: Adding Anchor Connections

**Goal**: Link students to anchor scale for absolute grading

**Configuration**:

- **Students**: Same 12 essay IDs
- **Anchors**: Same 12 anchors
- **Total Slots**: 84 (new comparisons)
- **Max Repetitions**: 3
- **Include Anchor-Anchor**: `no` (adjacency sufficient)
- **Previous Session CSV**: `session1_comparisons.csv`

**Optimizer Behavior**:

- Locks 58 Session 1 student-student pairs (cannot be removed)
- Adds 11 anchor adjacency pairs (hard constraint)
- Ensures each student gets ≥1 anchor comparison (coverage)
- Fills remaining ~60 slots with D-optimal selection

**Expected Output**:

- ~40 student-anchor pairs (scale bridging)
- ~33 student-student pairs (cluster resolution)
- ~11 anchor-anchor pairs (adjacency only)

**Quality Metrics** (after Session 2):

- SE: 0.15-0.25 (high precision)
- Confidence: Medium-High (>0.5 for most students)
- Grade projection: ENABLED (students linked to scale)
- Anchor candidates: 6-8 students eligible for promotion

### Session 3+: Refinement (Optional)

**When to Continue**:

- SE still >0.25 for some students
- Confidence <0.5 for critical essays
- Cluster resolution insufficient (tied grades)

**Configuration**: Same as Session 2, load `combined_sessions.csv`

**Expected Improvement**: SE drops to 0.10-0.20 (publication-quality precision)

---

## Parameter Guide

### Students Field

**Purpose**: Specify which student essays to include in the optimization

**Format Options**:

1. **Comma-separated list**:

   ```
   JA24, II24, ES24, EK24, ER24, TK24, SN24, HJ17, SA24, LW24, JF24, JP24
   ```

2. **CSV file** (drag or browse):

   ```csv
   essay_id
   JA24
   II24
   ES24
   ...
   ```

**File Format Requirements**:

- CSV with `essay_id` column (header optional)
- One essay ID per row
- IDs can be any alphanumeric string

**When to use CSV**:

- Large cohorts (>20 students)
- Consistent naming across sessions
- Integration with grade management systems

**Whitespace Handling**: Spaces, newlines, and commas are all supported delimiters

### Anchors Field

**Purpose**: Define the anchor essay scale for grade calibration

**Default**: Swedish 12-anchor system (F+1, F+2, E-, E+, D-, D+, C-, C+, B1, B2, A1, A2)

**Custom Anchors**:

```
A1, A2, B1, B2, C1, C2, D1, D2, E1, E2, F1, F2
```

**Requirements**:

- At least 2 unique anchors (minimum for calibration)
- Anchors must have known grades (pre-validated essays)
- Order matters: Define adjacency order (low to high)

**Anchor Ordering**: List anchors in grade order (worst → best). This defines the "ladder" for adjacency constraints.

### Total Slots

**Purpose**: Number of comparison pairs to generate

**Calculation Guidelines**:

**Session 1** (no previous data):

```
Recommended: 6-8× number of students
Example: 12 students → 72-96 comparisons
```

**Session 2+** (with baseline):

```
Recommended: Same as Session 1
Example: 84 new comparisons (optimizer adds to existing 58)
```

**Constraints**:

- Minimum: `2 × (students + anchors)` for connectivity
- Maximum: No hard limit, but >200 may be impractical for raters
- Typical: 60-100 comparisons per session

**Trade-offs**:

- **Fewer slots**: Faster rater completion, lower precision
- **More slots**: Higher precision, longer rater time

### Max Repetitions Per Pair

**Purpose**: How many times the same comparison can be assigned to different raters

**Recommended Values**:

- `1`: Each pair judged once (minimum)
- `2`: Each pair can be judged twice (allows disagreement detection)
- `3`: Up to three raters per pair (balanced reliability vs coverage)
- `4+`: High reliability for critical pairs (reduces coverage)

**Default**: `3` (sweet spot for most use cases)

**Impact on Design**:

- Higher max → more repeat judgments → higher reliability per pair
- Lower max → more unique pairs → better coverage of comparison space

**When to Increase**:

- High-stakes assessment (final grades)
- Rater disagreement expected
- Small cohort (few students, many raters available)

**When to Decrease**:

- Exploratory assessment
- Large cohort (need broad coverage)
- Limited rater availability

### Include Anchor-Anchor Comparisons

**Purpose**: Whether to allow optimizer to select anchor-anchor pairs beyond the mandatory adjacency ladder

**Options**:

- `yes`: Optimizer can select additional anchor-anchor pairs if they improve design
- `no`: Only mandatory adjacency pairs (11 for 12 anchors) are included

**Recommended Settings**:

**Session 1**: `yes`

- Establishes anchor scale validation
- Allows 15-20 anchor-anchor pairs total
- Useful for rater calibration

**Session 2+**: `no`

- Adjacency ladder already established
- Forces optimizer to prioritize student-anchor connections
- Maximizes scale linking for grading

**Theory**: From a Comparative Judgment perspective, anchor-anchor pairs:

- **Pros**: Validate scale consistency, help raters calibrate
- **Cons**: Minimal new information (grades already known)
- **Optimal**: 11 adjacency pairs (spanning tree) + 0-10 additional

**When to Keep Enabled**:

- Anchor grades uncertain or experimental
- Rater calibration important
- Very few students (<5)

**When to Disable**:

- Anchors pre-graded and trusted
- Maximize student-anchor density
- Creating new anchor candidates

### Previous Session CSV

**Purpose**: Load historical comparisons to build continuation-aware designs

**Format**: CSV with columns:

```csv
essay_a,essay_b,rater_id,outcome
JA24,II24,Rater1,a_wins
ES24,EK24,Rater2,b_wins
...
```

**Required Columns**:

- `essay_a`: First essay ID
- `essay_b`: Second essay ID

**Optional Columns** (ignored by optimizer but passed through):

- `rater_id`: Who made the judgment
- `outcome`: Result (a_wins, b_wins, tie)
- `timestamp`: When judgment was made

**Multi-Session Workflow**:

1. **Session 1**: Leave blank → generates initial 58 pairs
2. **After Session 1**: Raters complete judgments → export to CSV
3. **Session 2**: Load Session 1 CSV → optimizer locks those 58 pairs, adds 84 new
4. **After Session 2**: Combine Session 1+2 → export combined CSV
5. **Session 3**: Load combined CSV → optimizer locks 142 pairs, adds more

**Key Feature**: Optimizer ensures no pair appears more than `max_repeat` times **across all sessions**

---

## Best Practices for Optimal Results

### For Creating New Anchor Essays

**Goal**: Promote high-quality student essays to become new anchors (maximum validity and reliability)

**Recommended Distribution** (Session 2):

- **Student-Anchor**: 40-45 pairs (48-54%) - Establishes absolute positioning
- **Student-Student**: 28-35 pairs (33-42%) - Ensures precise estimates
- **Anchor-Anchor**: 11 pairs (13%) - Minimal validation only

**Rationale**:

1. **Validity** requires dense student-anchor connections (3-5 anchors per student)
2. **Reliability** requires low Standard Error (SE <0.25) from sufficient comparisons
3. **Balance** naturally emerges from D-optimal optimization

**Promotion Criteria** (apply after Session 2):

```python
# Student eligible for anchor promotion if:
- Confidence > 0.75 (HIGH)
- Standard Error < 0.25 (precise)
- Comparison Count ≥ 10 (adequate data)
- Grade Entropy < 0.5 (sharp distribution)
- BT Score Stable across sessions (drift <0.5)
```

**Expected**: 6-8 students out of 12 will meet criteria after Session 2 (142 total comparisons)

### When to Enable/Disable Anchor-Anchor Comparisons

**Enable** (`yes`) when:

- **Session 1**: Establishing baseline, need anchor validation
- **Uncertain anchors**: Anchor grades are experimental or need empirical confirmation
- **Rater calibration**: Want raters to practice on "known" comparisons first
- **Small cohort**: Few students (<5), anchor-anchor helps maintain design quality

**Disable** (`no`) when:

- **Session 2+**: Adjacency ladder already established
- **Trusted anchors**: Anchor grades are pre-validated and stable
- **Maximize student focus**: Want all free slots to go to student connections
- **Creating new anchors**: Need dense student-anchor coverage for promotion

**Default Recommendation**: `yes` for Session 1, `no` for Session 2+

### Target Quality Metrics

**After Session 1** (58 comparisons):

- **Standard Error**: 0.12-0.39 (wide range)
- **Confidence**: N/A (no anchors yet)
- **Coverage**: All students connected (graph connectivity)

**After Session 2** (142 total comparisons):

- **Standard Error**: <0.25 for all students (target: 0.15-0.20)
- **Confidence**: >0.50 for all (target: >0.60)
- **HIGH confidence count**: ≥8 students out of 12
- **Anchor candidates**: 6-8 students eligible for promotion

**After Session 3** (optional, 226+ total comparisons):

- **Standard Error**: <0.20 (publication-quality)
- **Confidence**: >0.70 (high confidence)
- **Grade stability**: Minimal drift from Session 2

### Handling Large Cohorts

**For >20 students**:

1. **Use CSV file input**:

   ```bash
   # Create students.csv
   essay_id
   Student001
   Student002
   ...
   Student050
   ```

2. **Increase total slots proportionally**:

   ```
   Recommended: 6-8× student count
   Example: 50 students → 300-400 comparisons
   ```

3. **Consider splitting into batches**:

   ```
   Batch 1: Students 1-25 (200 comparisons)
   Batch 2: Students 26-50 (200 comparisons)
   Combined: All 50 (100 cross-batch comparisons)
   ```

4. **Adjust max repetitions**:

   ```
   Large cohort: max_repeat=2 (favor coverage over reliability)
   Small cohort: max_repeat=3 (favor reliability over coverage)
   ```

---

## Understanding the Output

### Pairs CSV Format

**File**: `cj_comparison_pairs.csv`

**Columns**:

```csv
essay_a,essay_b,comparison_type
JA24,F+1,student_anchor
II24,ES24,student_student
F+1,F+2,anchor_anchor
...
```

**Fields**:

- `essay_a`: First essay ID (order matters for some rater interfaces)
- `essay_b`: Second essay ID
- `comparison_type`: One of `student_anchor`, `student_student`, `anchor_anchor`

**Usage**:

- Import into rater interface
- Track completion status
- Analyze type distribution

### Assignments CSV Format

**File**: `cj_rater_assignments.csv`

**Columns**:

```csv
rater_id,essay_a,essay_b,comparison_type,display_a,display_b
Rater_1,JA24,F+1,student_anchor,essay_03,essay_17
Rater_1,II24,ES24,student_student,essay_08,essay_12
...
```

**Fields**:

- `rater_id`: Assigned rater (Rater_1, Rater_2, ...)
- `essay_a`, `essay_b`: Original essay IDs
- `comparison_type`: Type of comparison
- `display_a`, `display_b`: Anonymized labels (essay_01, essay_02, ...)

**Features**:

- **Workload balanced**: Each rater gets approximately equal number of comparisons
- **Type balanced**: Each rater gets mixed comparison types
- **Anonymized**: Display labels prevent rater bias

**Rater Count**: Automatically calculated from `total_slots / desired_per_rater`

### Optimization Diagnostics

**Displayed in log widget**:

```
Design Summary:
- Total Comparisons: 84
- Student-Anchor: 42 (50%)
- Student-Student: 31 (37%)
- Anchor-Anchor: 11 (13%)

Optimization:
- Log-Det: 51.63 (52% improvement over baseline)
- Greedy Iterations: 61
- Fedorov Swaps: 12

Constraints:
- Locked Pairs: 58 (from previous session)
- Adjacency Pairs: 11 (anchor ladder)
- Coverage Pairs: 12 (minimum student-anchor)
```

**Key Metrics**:

- **Log-Det**: Higher is better (aim for >50 for 24 essays)
- **Type Distribution**: Should align with theoretical expectations
- **Constraint Satisfaction**: All required pairs must be included

---

## Troubleshooting

### Common Errors

#### Error: "At least one student essay ID is required"

**Cause**: Students field is empty

**Solution**: Enter student IDs (comma-separated or CSV file)

#### Error: "Pairs CSV not found: [path]"

**Cause**: Previous Session CSV path is invalid

**Solution**:

- Check file exists at specified path
- Use Browse button or drag-and-drop
- Leave blank for Session 1

#### Error: "No comparisons available in pairs CSV"

**Cause**: Previous Session CSV is empty or malformed

**Solution**:

- Check CSV has `essay_a` and `essay_b` columns
- Verify at least one row of data
- Check for encoding issues (use UTF-8)

#### Error: "Max repeat constraint violated"

**Cause**: Not enough unique pairs to satisfy total_slots with max_repeat limit

**Solution**:

- Reduce `total_slots`
- Increase `max_repeat`
- Check if locked/previous pairs already saturate some combinations

### File Dialog Not Working

**Symptoms**: Browse button does nothing or crashes

**Causes**:

- Running on headless system (SSH, Docker)
- Missing GUI libraries (Linux without GTK)
- `crossfiledialog` dependency not installed

**Solutions**:

1. **Manual path entry**: Type or paste file path directly into field
2. **Drag-and-drop**: Drag file from Finder/Explorer into input field
3. **Install dependencies** (if building from source):

   ```bash
   pdm install  # Installs crossfiledialog
   ```

**Platform-Specific**:

- **macOS**: File dialogs use native NSOpenPanel (should always work)
- **Windows**: Uses Win32 Common Dialogs (requires Windows 7+)
- **Linux**: Requires GTK3 (`sudo apt install python3-gi gir1.2-gtk-3.0`)

### Validation Errors

#### "Not a valid CSV file"

**Solution**: Ensure CSV has proper structure:

```csv
essay_id
Student1
Student2
```

#### "Duplicate essay IDs found"

**Solution**: Remove duplicates from students or anchors list

#### "Anchor order invalid"

**Solution**: Anchors must be comma-separated with at least 2 unique values

### Performance Issues

**Symptoms**: Generation takes >30 seconds

**Causes**:

- Large problem size (>50 essays, >150 comparisons)
- Many locked pairs from previous sessions
- High max_repeat setting

**Solutions**:

1. **Reduce problem size**:

   ```
   Split large cohort into batches
   Use fewer total slots per session
   ```

2. **Optimize parameters**:

   ```
   Lower max_repeat (3 → 2)
   Disable anchor-anchor if not needed
   ```

3. **Run from source** (faster than standalone):

   ```bash
   pdm run python scripts/bayesian_consensus_model/redistribute_tui.py
   ```

**Complexity**: O(slots × candidates²) = O(84 × 100²) ≈ 840,000 operations

**Typical Runtime**:

- 12 students, 84 slots: 3-5 seconds
- 24 students, 150 slots: 10-15 seconds
- 50 students, 300 slots: 30-60 seconds

---

## Keyboard Shortcuts

- `g`: Generate comparison pairs
- `F1` or `?`: Open help screen
- `q` or `Ctrl+C`: Quit application
- `Tab`: Navigate between fields
- `Shift+Tab`: Navigate backwards
- `Esc`: Close help screen
- `Enter`: Submit focused field

---

## File Locations

**Standalone Executable**:

```
dist/cj-pair-generator-tui
```

**Source Code**:

```
scripts/bayesian_consensus_model/
├── redistribute_tui.py          # Main TUI application
├── d_optimal_optimizer.py       # D-optimal algorithm
├── redistribute_core.py         # Assignment logic
├── d_optimal_workflow/          # Workflow modules
│   ├── models.py                # Data models
│   ├── data_loaders.py          # CSV loading
│   ├── optimization_runners.py  # Optimizer interface
│   └── synthetic_data.py        # Testing utilities
└── tui/                         # TUI components
    ├── form_layout.py           # Widget layout
    ├── help_screen.py           # Help documentation
    ├── workflow_executor.py     # Business logic
    ├── result_formatter.py      # Log formatting
    └── file_drop_handler.py     # File path extraction
```

**Build Script**:

```
scripts/build_standalone.sh
```

**Documentation**:

```
scripts/bayesian_consensus_model/TUI_README.md  # This file
.claude/research_prompts/                       # Session planning documents
```

---

## References

### D-Optimal Design Theory

- **Atkinson, Donev, & Tobias (2007).** *Optimum Experimental Designs, with SAS.* Oxford University Press.
  - Standard reference for D-optimal experimental design
  - Chapter 11: Paired comparison designs

- **Krause & Golovin (2014).** "Submodular Function Maximization." In *Tractability: Practical Approaches to Hard Problems.*
  - Proof that log-det is submodular
  - Greedy approximation guarantee

- **Nemhauser, Wolsey, & Fisher (1978).** "An analysis of approximations for maximizing submodular set functions." *Mathematical Programming*, 14(1), 265-294.
  - (1-1/e) ≈ 63.2% approximation bound for greedy

### Comparative Judgment

- **Pollitt (2012).** "The method of Adaptive Comparative Judgement." *Assessment in Education*, 19(3), 281-300.
  - Foundation of CJ methodology

- **Bramley (2007, 2015).** Various papers on rank-ordering and paired comparisons in educational assessment

- **Bartholomew & Bramley (2015).** "A framework for adaptive comparative judgement." *Assessment in Education*, 22(3), 371-397.

### Bradley-Terry Model

- **Bradley & Terry (1952).** "Rank analysis of incomplete block designs: I. The method of paired comparisons." *Biometrika*, 39(3/4), 324-345.
  - Original paired comparison probability model

- **Hunter (2004).** "MM algorithms for generalized Bradley-Terry models." *Annals of Statistics*, 32(1), 384-406.
  - Modern estimation algorithms

---

## Support & Contribution

**Issues**: Report bugs or request features in the project issue tracker

**Documentation**: Additional planning documents available in `.claude/research_prompts/`

**Help**: Press `F1` or `?` in the application for comprehensive inline help

**Version**: 1.0.0 (2025-01-03)

---

## License

Part of the HuleEdu educational assessment platform.

**Last Updated**: 2025-01-03
