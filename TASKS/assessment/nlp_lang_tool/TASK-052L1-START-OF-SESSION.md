---
id: 'TASK-052L1-START-OF-SESSION'
title: 'Start-of-TASK Prompt for Next Claude Session'
type: 'task'
status: 'research'
priority: 'medium'
domain: 'assessment'
service: ''
owner_team: 'agents'
owner: ''
program: ''
created: '2025-09-20'
last_updated: '2025-11-17'
related: []
labels: []
---
# Start-of-TASK Prompt for Next Claude Session

---
**CRITICAL**: Before starting ANY work, you MUST read the following in order:
1. `.claude/rules/000-rule-index.mdc` - Full rule index
2. `.claude/rules/010-foundational-principles.mdc` - Core principles (YAGNI, DRY, SOLID)
3. `.claude/rules/042-async-patterns-and-di.mdc` - Async patterns and DI
4. `.claude/rules/050-python-coding-standards.mdc` - Python standards
5. `CLAUDE.md` and `CLAUDE.local.md` - User-specific instructions
6. `TASKS/TASK-052L-feature-pipeline-integration-master.md` - Master plan with 50 features
7. `TASKS/TASK-052L.1-feature-pipeline-scaffolding.md` - Current phase requirements
8. THIS DOCUMENT - Critical context about pipeline architecture

**DO NOT** proceed until you have read ALL these files.

---

## Context: NLP Feature Pipeline - Phase 2 Implementation

### What Has Been Completed (TASK-052L.0)

✅ **PHASE 1 COMPLETE**: Spell normalization infrastructure ready:
- `libs/huleedu_nlp_shared/` with SpellNormalizer class extracted from Spellchecker Service
- `scripts/ml/normalize_dataset.py` CLI tool for batch normalization
- Enhanced whitelist (2.98M entries) preventing abbreviation mangling (UK, USA, COVID, CVs preserved)
- Tested on 100 IELTS essays: 1.47 corrections per 100 words

**Key Files Created**:
```
libs/huleedu_nlp_shared/src/huleedu_nlp_shared/normalization/spell_normalizer.py
scripts/ml/normalize_dataset.py
scripts/ml/prepare_ielts_task2_dataset.py (moved from data_preparation/)
services/spellchecker_service/data/whitelist/combined_whitelist.txt (enhanced)
```

### ⚠️ CRITICAL ARCHITECTURAL UNDERSTANDING

The current `normalize_dataset.py` has **two fundamental misunderstandings** of the pipeline architecture:

**Misunderstanding 1: Treating correction metrics as preprocessing, not features**

**CURRENT (INCORRECT) Implementation**:
```
Raw Essay → normalize_dataset.py → Normalized Text + Metrics (stored separately)
                                    ↓
                        build_nlp_features.py → Extract 50 features from normalized text
```

**Misunderstanding 2: Not aggregating spelling errors from multiple sources**

The `spelling_error_rate_p100w` feature requires:
- Errors found and corrected by SpellNormalizer (L2 + PySpellChecker)
- PLUS errors found by Language Tool's SPELLING category on the normalized text
- These must be AGGREGATED, not treated separately

**CORRECT Architecture per TASK-052L Master Plan**:
```
Raw Essay → FeaturePipeline
              ├─> SpellNormalizer → Normalized Text (for downstream processing)
              │                  ↘
              │                    Correction Metrics (ARE features #1-4)
              ├─> Grammar features (using normalized text)
              ├─> Vocabulary features (using normalized text)
              ├─> Syntactic features (using normalized text)
              ├─> Cohesion features (using normalized text)
              ├─> Readability features (using normalized text)
              └─> Task alignment features (using normalized text)
                                    ↓
                            All 50 features (including spell corrections)
```

### The 50 Features (from TASK-052L-master)

The spell correction metrics **ARE PART OF** the Grammar & Mechanics dimension:

**Grammar & Mechanics (10)** - AGGREGATED from multiple sources:
1. `spelling_error_rate_p100w` - AGGREGATE of:
   - SpellNormalizer corrections (already applied to text)
   - Language Tool SPELLING detections (on normalized text)
   - Total spelling errors = SpellNormalizer + LanguageTool(SPELLING)
2. `grammar_error_rate_p100w` - From Language Tool Service (non-SPELLING categories)
3. `punctuation_error_rate_p100w` - From Language Tool
4. `capitalization_error_rate_p100w` - From Language Tool
5. `agreement_error_rate_p100w` - From Language Tool
6. `tense_misuse_rate_p100w` - From Language Tool
7. `sentence_fragment_rate` - From Language Tool
8. `run_on_rate` - From Language Tool
9. `quote_mismatch_count` - Custom extraction
10. `non_alnum_symbol_rate` - Custom extraction

**Plus 40 more features** in: Vocabulary (8), Syntactic (10), Cohesion (8), Readability (8), Task Alignment (6)

---

## YOUR IMMEDIATE TASK

### Primary Objective

Implement `TASK-052L.1-feature-pipeline-scaffolding.md` with the CORRECT understanding that:
1. SpellNormalizer provides BOTH normalized text AND features
2. The FeaturePipeline must orchestrate all 50 feature extractions
3. Normalized text is used by OTHER feature extractors, not stored separately

### Critical Implementation Requirements

1. **Create `libs/huleedu_nlp_shared/feature_extraction/` module** with:
   ```python
   class FeatureContext:
       """Container for essay analysis state."""
       raw_text: str
       normalized_text: str  # From SpellNormalizer
       spell_metrics: dict  # total_corrections, l2_corrections, etc.
       spacy_doc: Doc | None  # Lazy-loaded
       language_tool_results: dict | None  # Lazy-loaded
       # ... other analysis results

   class FeaturePipeline:
       """Orchestrates all 50 feature extractions."""
       def __init__(
           self,
           spell_normalizer: SpellNormalizer,
           language_tool_client: LanguageToolClient | None,
           # ... other dependencies
       ):
           self.spell_normalizer = spell_normalizer
           # Register feature extractors...

       async def extract_features(self, text: str) -> dict[str, float]:
           """Extract all 50 features from raw text."""
           # Step 1: Normalize and get spell metrics
           norm_result = await self.spell_normalizer.normalize_text(text)
           word_count = len(norm_result.corrected_text.split())

           context = FeatureContext(
               raw_text=text,
               normalized_text=norm_result.corrected_text,
               spell_normalizer_corrections=norm_result.total_corrections,
               word_count=word_count
           )

           # Step 2: Run Language Tool on NORMALIZED text
           if self.language_tool_client:
               lt_results = await self.language_tool_client.check(
                   context.normalized_text
               )
               # Count Language Tool SPELLING errors (these are ADDITIONAL)
               lt_spelling_errors = sum(
                   1 for error in lt_results.errors
                   if error.category == 'SPELLING'
               )
               context.language_tool_results = lt_results
           else:
               lt_spelling_errors = 0

           # Step 3: AGGREGATE spelling errors from both sources
           total_spelling_errors = (
               context.spell_normalizer_corrections +  # Already corrected
               lt_spelling_errors  # Found but not corrected
           )

           features = {
               'spelling_error_rate_p100w': (total_spelling_errors / word_count) * 100,
               'grammar_error_rate_p100w': self._extract_grammar_rate(context),
               # ... other 48 features
           }

           return features  # All 50 features with AGGREGATED spelling
   ```

2. **Refactor `scripts/ml/normalize_dataset.py`** to:
   - REMOVE standalone normalization logic
   - USE the FeaturePipeline for normalization + initial features
   - Or rename to `prepare_normalized_dataset.py` if keeping as preprocessing step

3. **Create `scripts/ml/build_nlp_features.py`** that:
   - Uses FeaturePipeline to extract ALL 50 features
   - Outputs complete feature matrix for model training

### Expected Pipeline Flow

```python
# In build_nlp_features.py
pipeline = FeaturePipeline(
    spell_normalizer=normalizer,  # Provides normalized text + spell features
    language_tool_client=lt_client,  # Provides grammar features
    # ... other components
)

# Process each essay
for essay in essays:
    features = await pipeline.extract_features(essay.raw_text)
    # features now contains all 50 features including:
    # - spelling_error_rate_p100w (from SpellNormalizer)
    # - grammar_error_rate_p100w (from Language Tool)
    # - mtld, hdd, ttr_lemma (from vocabulary extractors)
    # - ... all other features
```

### Implementation Priorities

1. **FIRST**: Create FeatureContext and FeaturePipeline base classes
2. **SECOND**: Implement spell feature extraction (already have SpellNormalizer)
3. **THIRD**: Add Grammar features via Language Tool client
4. **THEN**: Incrementally add other feature bundles

### Key Design Decisions

1. **Normalized text is ephemeral** - It's an intermediate product for feature extraction, not a final output
2. **Spell metrics ARE features** - Not just preprocessing statistics
3. **FeaturePipeline owns the flow** - It orchestrates normalization → feature extraction
4. **Lazy loading** - SpaCy docs, Language Tool results loaded only when needed
5. **CRITICAL: Spelling errors are AGGREGATED** from two sources:
   - SpellNormalizer finds and corrects errors (count these)
   - Language Tool finds ADDITIONAL spelling errors in the normalized text
   - `spelling_error_rate_p100w` = (SpellNormalizer corrections + LanguageTool SPELLING) / words * 100
   - This prevents double-counting while capturing all spelling issues

---

## WARNINGS - READ CAREFULLY

1. **Architecture**: The spell correction metrics are FEATURES, not just preprocessing stats
2. **No Duplication**: Don't extract spelling features twice (once in normalize, once in features)
3. **Consistency**: All 50 features must be extracted in the same pipeline
4. **Testing**: Each feature extractor needs unit tests with known inputs/outputs
5. **Performance**: Use async and batching - this will process thousands of essays

---

## Verification Checklist

After implementation, verify:
- [ ] FeaturePipeline extracts exactly 50 features
- [ ] `spelling_error_rate_p100w` = (SpellNormalizer + LanguageTool SPELLING) / words * 100
- [ ] Language Tool runs on NORMALIZED text (not raw text)
- [ ] No double-counting: SpellNormalizer corrections are not re-detected by Language Tool
- [ ] Normalized text is used by all downstream extractors
- [ ] All features have consistent naming per TASK-052L master list
- [ ] Pipeline can process 100 essays without memory leaks

---

## Current State vs. Required State

**Current State**:
- ✅ SpellNormalizer works and provides metrics
- ✅ normalize_dataset.py can batch process essays
- ❌ Metrics treated as side effects, not features
- ❌ No unified FeaturePipeline
- ❌ No integration with Language Tool or other extractors

**Required State**:
- ✅ FeaturePipeline orchestrates all extraction
- ✅ Spell metrics recognized as features 1-2 of 50
- ✅ Normalized text feeds into other extractors
- ✅ All 50 features extracted in single pass
- ✅ Ready for decision tree model training

---

## Next Steps After This Task

1. TASK-052L.2: Implement all 50 feature extractors
2. TASK-052L.3: Validate features on full IELTS dataset
3. TASK-052K: Train decision tree model using feature matrix

Remember: The spell correction is not just preprocessing - it's an integral part of the feature extraction pipeline. The correction metrics ARE features that the model will use for IELTS band prediction.