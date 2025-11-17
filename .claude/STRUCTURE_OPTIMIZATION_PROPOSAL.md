# .claude/ Directory Structure Optimization Proposal

## Current Issues

### Redundancy
- `TODOs/` (12K) and `tasks/` (340K) contain similar task-tracking content
- `reviews/` (empty) and `code-reviews/` (92K) - one is unused

### Organization
- 6 top-level markdown files without clear hierarchy
- Mixed active/archive content (prompts, results, repomix_packages are historical)
- Research directory (1.4M) mixes papers with technical validation

### Clarity
- Unclear purpose of `audits/`, `results/`, `prompts/`
- No separation between active work and completed/archived artifacts

## Proposed Optimized Structure

```
.claude/
├── config/                    # Configuration & settings
│   ├── settings.local.json
│   └── README.md              # Config documentation
│
├── agents/                    # Agent definitions (keep as-is)
│
├── skills/                    # Reusable skills (keep as-is)
│   ├── hooks/
│   ├── docs-structure/
│   └── repomix/
│
├── commands/                  # Slash commands (keep as-is)
│
├── hooks/                     # Hook scripts (keep as-is)
│
├── rules/                     # Development rules (keep as-is)
│
├── work/                      # ACTIVE work artifacts
│   ├── tasks/                 # Active task tracking (merge TODOs/ + tasks/)
│   ├── session/               # Session-specific files
│   │   ├── handoff.md         # Current session handoff
│   │   ├── readme-first.md    # Session start instructions
│   │   └── next-prompt.md     # Next session prompt
│   └── audits/                # Recent compliance audits
│
├── archive/                   # COMPLETED/historical artifacts
│   ├── code-reviews/          # Historical PR reviews
│   ├── session-results/       # Completed session results
│   ├── prompts/               # Old prompt templates
│   ├── repomix/               # Old repomix packages
│   └── task-archive/          # Archived task recommendations
│
└── research/                  # Research & validation
    ├── papers/                # Academic papers on CJ, assessment
    ├── validation/            # Technical validation reports
    └── README.md              # Research index
```

## Migration Plan

### Phase 1: Create New Structure
1. Create `config/`, `work/`, `archive/`, `research/papers/`, `research/validation/`
2. Move `settings.local.json` → `config/`
3. Create `work/session/` for active session files

### Phase 2: Consolidate Tasks
1. Review `TODOs/` and `tasks/` for active vs archived
2. Merge active tasks into `work/tasks/`
3. Archive old/completed tasks to `archive/task-archive/`

### Phase 3: Organize Archives
1. Move `code-reviews/` → `archive/code-reviews/`
2. Move `results/` → `archive/session-results/`
3. Move `prompts/` → `archive/prompts/`
4. Move `repomix_packages/` → `archive/repomix/`

### Phase 4: Organize Research
1. Move research papers → `research/papers/`
2. Move technical validation → `research/validation/`
3. Create research index

### Phase 5: Consolidate Session Files
1. Move `HANDOFF.md` → `work/session/handoff.md`
2. Move `README_FIRST.md` → `work/session/readme-first.md`
3. Move `NEXT_SESSION_PROMPT.md` → `work/session/next-prompt.md`
4. Move `CLOUD_ENV_INSTRUCTIONS.md` → `config/cloud-env-instructions.md`
5. Move `TASK_ARCHIVE_RECOMMENDATION.md` → `archive/task-archive/README.md`

### Phase 6: Cleanup
1. Remove empty `reviews/` directory
2. Update any references in documentation
3. Create README.md in each major directory

## Benefits

### Clarity
- Clear separation between active work and archives
- Session-specific files grouped together
- Configuration isolated from work artifacts

### Navigation
- Easier to find relevant files
- Logical grouping reduces cognitive load
- Active work immediately visible

### Maintenance
- Easier to clean up old artifacts
- Clear archiving strategy
- Reduced clutter in top-level

## Backward Compatibility

### Files That Reference .claude/ Paths
- Pre-commit hooks
- Scripts
- Documentation
- Agents

### Strategy
1. Use symlinks for critical paths during transition
2. Update references in a single commit
3. Test all hooks and scripts after migration

## Implementation

Would you like me to:
1. Execute the full migration automatically?
2. Execute phase-by-phase with your approval?
3. Modify the proposal based on your feedback?
