---
id: "continuation-prompt"
title: "HANDOFF: TUI Help Screen Completion"
type: "task"
status: "research"
priority: "medium"
domain: "content"
service: ""
owner_team: "agents"
owner: ""
program: ""
created: "2025-11-02"
last_updated: "2025-11-17"
related: []
labels: []
---
## CRITICAL: Read These Files First (In Order)

1. `.agent/rules/095-textual-tui-patterns.md` - Textual API patterns and gotchas
2. `TASKS/pyinstaller_standalone_executables_plan.md` - Implementation context
3. `scripts/bayesian_consensus_model/tui/help_screen.py` - CURRENT INCOMPLETE HELP
4. `scripts/bayesian_consensus_model/tui/form_layout.py` - All form fields and their IDs
5. `scripts/bayesian_consensus_model/tui/workflow_executor.py` - What fields actually do

## Current Problem

**ISSUE**: Help screen content in `help_screen.py` is INCOMPLETE. The Markdown string ends abruptly after the "Students (Manual Entry)" field. The following fields are MISSING from help:

### Missing Field Documentation

1. Anchors (Custom Ladder) - partially written but incomplete
2. Assignments CSV Path
3. Number of Raters
4. Explicit Rater Names
5. Comparisons Per Rater
6. Generated Pairs Output
7. Previous Session CSV
8. Locked Pairs
9. Max Repetitions Per Pair
10. Include Anchor-Anchor Comparisons

## What the TUI Actually Does (User Context)

**App Purpose**: Generate optimized comparison pair assignments for Comparative Judgment (CJ) assessment

**User Workflow**:

1. **Input**: Student essays to be compared + optional pre-graded anchor essays
2. **Process**: D-optimal algorithm generates balanced comparison pairs
3. **Output**: Assignment CSV mapping each rater to specific pairs they should judge

**Why Users Need This**:

- Manual pair generation is tedious and prone to bias
- Optimal design ensures statistical efficiency
- Fair distribution prevents rater overload
- Multi-session support allows spreading judgments over time

## Field Purposes (What User Needs to Know)

### Student Input Fields

- **Students CSV**: Large cohorts (20+ students) - load from existing data
- **Students Manual**: Small cohorts or testing - quick comma-separated entry
- User will typically use ONE of these fields, not both

### Anchor Fields

- **Anchors**: Custom pre-graded essays for calibration. Format: grade-based IDs (e.g., F+1, F+2 means two F+ grade essays, B1, B2 means two B grade essays)
- Default: 12-anchor ladder covering F+ through A3
- User provides this when they have specific graded essays to use as reference points

### Rater Configuration

- **Rater Count**: How many people will judge (default 14)
- **Rater Names**: Alternative to count - specific identities for personalized assignments
- **Comparisons Per Rater**: Workload per person (default 10 pairs each)
- User determines their available rater pool and reasonable workload

### Output Paths

- **Assignments CSV**: Final file raters will receive with their assigned pairs
- **Generated Pairs Output**: Reference file of all pairs before distribution

### Optimization Settings

- **Previous Session CSV**: For multi-session workflows - loads existing pairs to avoid duplicates
- **Locked Pairs**: Force specific comparisons (e.g., research requirements)
- **Max Repetitions**: How many times same pair can appear (reliability vs coverage tradeoff)
- **Include Anchor-Anchor**: Whether anchors compare to each other (usually yes for calibration)

## Solution Steps

### Step 1: Read Current Help Content

```bash
# Locate where content ends
grep -A 50 "Students (Manual Entry)" scripts/bayesian_consensus_model/tui/help_screen.py
```

### Step 2: Understand Field IDs and Purposes

Read `form_layout.py` lines 115-172 to see:

- All Input/Select field IDs
- Field labels
- Default values
- Placeholder text

Read `workflow_executor.py` to understand:

- `extract_optimizer_inputs()` - what optimizer needs
- `extract_assignment_inputs()` - what assignment generator needs
- How fields map to functionality

### Step 3: Fix the Help Content

**In `help_screen.py`**, replace the truncated `HELP_CONTENT` string with COMPLETE documentation covering:

1. **All form fields** (not just first two!)
2. **Purpose**: What is this field for?
3. **Format**: How should user enter data?
4. **When to use**: Use cases and decision guidance
5. **Examples**: Concrete examples with explanation
6. **Defaults**: What happens if left blank?

### Step 4: Markdown Formatting

Use proper Markdown structure:

```markdown
### Field Name
**Purpose**: One-line summary

**Format**: Input format description

**When to use**: User decision criteria

**Example**: Concrete example

**Notes**: Any gotchas or tips
```

## Key User Knowledge Gaps to Address

### Anchors Confusion

Users don't understand:

- What "anchor ladder" means (essays with known grades)
- Why grade should be in the ID (so they know what grade level each anchor represents)
- Why use numbers for same grade (F+1, F+2 = two F+ essays, distinguishable)
- That any grade system works (not just A-F)

### Multi-Session Workflow

Users don't understand:

- When to use "Previous Session CSV" (session 2+)
- Why this prevents duplicate pairs (algorithm excludes already-judged comparisons)
- Workflow: Session 1 generates pairs → Session 2 loads those + generates more

### Rater Configuration

Users don't understand:

- Count vs Names (use count for anonymous, names for personalized)
- Total pairs calculation (count × per_rater)
- Locked pairs use case (force specific research comparisons)

## Testing After Fix

```bash
# Test direct execution
pdm run python -m scripts.bayesian_consensus_model.redistribute_tui

# Press F1 or ?
# Verify:
# 1. All 15+ fields documented
# 2. Content scrolls to bottom
# 3. Markdown renders properly (headers, bold, lists)
# 4. Examples are concrete and clear
# 5. User decision criteria provided
```

## Code Pattern to Follow

**DO NOT** modify any logic, only the `HELP_CONTENT` string in `help_screen.py`.

The string should be ~200-300 lines of Markdown covering:

- Form Fields section (all fields!)
- Optimization Settings section
- Workflow section
- Tips & Shortcuts section

## Context: Recent TUI Improvements

Session completed these fixes:

1. ✅ Button black highlight removed (CSS fix)
2. ✅ Button disables during generation
3. ✅ Default focus on CSV field
4. ✅ Anchors placeholder improved
5. ✅ Help screen infrastructure created (F1/? bindings work)
6. ❌ Help content INCOMPLETE (current task)

## Project Standards Compliance

- **From `.agent/rules/095-textual-tui-patterns.md`**: Verify Textual imports before use
- **From `CLAUDE.md`**: Run `pdm run python -m ...` for testing, never use relative imports
- **From `CLAUDE.local.md`**: No makeshift solutions - complete the help properly

## Success Criteria

Help screen shows:

- ✅ All form fields documented with purpose/format/examples
- ✅ Optimization settings explained
- ✅ Complete workflow from input → output
- ✅ Clear user decision criteria for each field
- ✅ Concrete examples (not vague descriptions)
- ✅ Multi-session workflow guidance
- ✅ Anchor ladder concept clearly explained
- ✅ Content scrollable to end (no truncation)

## Additional Files Modified This Session

**Files with UX improvements (all working)**:

- `scripts/bayesian_consensus_model/tui/form_layout.py`:
  - Line 92-94: Added CSS `Button:focus { text-style: bold; }` (removes black highlight)
  - Line 117: Updated Anchors placeholder to show example format

- `scripts/bayesian_consensus_model/redistribute_tui.py`:
  - Line 28: Added HelpScreen import
  - Line 48-49: Added F1 and ? keybindings
  - Line 59: Changed default focus to `#students_csv_input` (was `#students_input`)
  - Line 103-105: Added `action_show_help()` method
  - Line 109: Button disables on click
  - Line 188-191: Button re-enables in finally block

**New file created**:

- `scripts/bayesian_consensus_model/tui/help_screen.py` - Help screen with INCOMPLETE content

## How to Resume

1. Read the files listed at the top in order
2. Locate the truncated `HELP_CONTENT` string in `help_screen.py`
3. Review all field IDs in `form_layout.py` lines 100-172
4. Complete the help content with ALL missing fields
5. Test with `pdm run python -m scripts.bayesian_consensus_model.redistribute_tui`
6. After confirmation, rebuild distribution: `pdm run build-standalone`
