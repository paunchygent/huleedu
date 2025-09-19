# TASK-052M: LanguageTool N-Gram Implementation for Enhanced Grammar Detection

## Problem Statement

The Language Tool Service currently cannot detect certain grammar errors that require statistical language modeling:

- **Missing apostrophes**: "In a weeks time" is not flagged (should be "week's")
- **Context-based errors**: Statistically unlikely word combinations
- **Confusion pairs**: their/there, your/you're in context

Investigation revealed that LanguageTool's rule-based detection has limitations, particularly for:

1. Missing possessive apostrophes (vs. misplaced ones which ARE detected)
2. Short introductory phrase commas (≤4 words)
3. Context-dependent grammar that requires statistical validation

## Solution: N-Gram Language Models

N-grams provide statistical language modeling to detect errors based on word combination probabilities. LanguageTool supports n-gram integration via Lucene indexes for enhanced detection.

## Current Findings

### Configuration Issues Fixed

- Removed TYPOS category from `GRAMMAR_CATEGORIES_BLOCKED`
- Now detects spelling errors ("grammer", "identifyed")
- Still cannot detect missing apostrophes in "weeks time"

### N-Gram Availability

#### English ✅

- **Source**: LanguageTool official
- **File**: `ngrams-en-20150817.zip` (8.9GB)
- **URL**: `https://languagetool.org/download/ngram-data/ngrams-en-20150817.zip`
- **Format**: Ready-to-use Lucene indexes

#### Swedish ⚠️ (Requires Conversion)

- **Source**: NST (Språkbanken)
- **File**: `ngram_swe.tar.gz`
- **URL**: `https://www.nb.no/sprakbanken/ressurskatalog/oai-nb-no-sbr-11/`
- **Format**: Raw text (needs Lucene conversion)
- **Date**: 2012 (437M tokens)

## Implementation Plan

### Phase 1: Infrastructure Setup

#### 1.1 Docker Volumes

```yaml
volumes:
  lt_ngrams_english:   # ~15GB extracted
  lt_ngrams_swedish:   # ~5GB estimated
  lt_ngrams_builder:   # Temp for conversion
```

#### 1.2 N-Gram Builder Service

Create a one-time init container for:

- Downloading English n-grams
- Converting Swedish NST data to Lucene format
- Building LanguageTool dev tools

### Phase 2: Swedish N-Gram Conversion

#### 2.1 Converter Script

```python
# convert_nst_to_lt.py
# Input: NST format (word<TAB>count<TAB>metadata)
# Output: LT format (ngram<TAB>count)
# Process: 1-grams, 2-grams, 3-grams separately
```

#### 2.2 Lucene Index Building

```bash
# Using FrequencyIndexCreator from languagetool-dev
java -cp languagetool-dev.jar \
  org.languagetool.dev.bigdata.FrequencyIndexCreator \
  lucene /data/1gram.tsv /ngrams/sv/1grams
```

### Phase 3: Service Configuration

#### 3.1 Config Updates

```python
# config.py additions
LANGUAGE_TOOL_LANGUAGE_MODEL_DIR: str | None = Field(
    default=None,
    description="Path to n-gram language model directory"
)
LANGUAGE_TOOL_HEAP_SIZE: str = Field(
    default="512m",  # Increase to "3g" when n-grams enabled
    description="JVM heap size for LanguageTool"
)
```

#### 3.2 LanguageTool Manager Updates

```python
# Pass --languageModel flag when starting JAR
if settings.LANGUAGE_TOOL_LANGUAGE_MODEL_DIR:
    cmd.extend(["--languageModel", settings.LANGUAGE_TOOL_LANGUAGE_MODEL_DIR])
```

### Phase 4: Multi-Language Support

#### 4.1 Directory Structure

```
/ngrams/
├── en/
│   ├── 1grams/
│   ├── 2grams/
│   └── 3grams/
└── sv/
    ├── 1grams/
    ├── 2grams/
    └── 3grams/
```

#### 4.2 Language Detection

- Detect request language (en-US vs sv-SE)
- Switch n-gram model path accordingly
- OR: Load both models if memory permits (6GB heap)

## Resource Requirements

### Disk Space

- English n-grams: ~15GB
- Swedish n-grams: ~5GB (estimated)
- Build workspace: ~5GB (temporary)
- **Total**: 25GB persistent, 5GB temporary

### Memory

- Without n-grams: 512MB heap
- With n-grams: 3-4GB heap
- Recommended: 4GB to support both languages

### Performance

- SSD strongly recommended (mmap'd indexes)
- Initial startup: +30-60s
- Query latency: Minimal impact (<50ms)

## Testing Strategy

### Unit Tests

- Mock n-gram responses
- Test with/without models
- Language switching logic

### Integration Tests

```python
# Test cases for n-gram detection
test_cases = [
    ("In a weeks time", "In a week's time"),  # Missing apostrophe
    ("I seen it", "I saw it"),                # Common grammar error
    ("their going", "they're going"),         # Confusion pair
]
```

### Validation Metrics

- Apostrophe detection rate
- False positive rate
- Performance impact

## Expected Outcomes

### With N-Grams Enabled

- ✅ Detect "a weeks time" → "a week's time"
- ✅ Better confusion pair detection
- ✅ Context-aware grammar checking
- ✅ Statistical validation of word combinations

### Limitations Remaining

- ⚠️ Swedish n-grams from 2012 (may miss modern usage)
- ⚠️ Increased resource consumption
- ⚠️ One-time conversion overhead for Swedish

## Implementation Steps

### Immediate Actions

1. Create n-gram builder Dockerfile
2. Implement NST → LT converter script
3. Add Docker volumes to compose files
4. Update service configuration

### Follow-up Tasks

1. Performance benchmarking
2. Documentation updates
3. Consider newer Swedish corpus sources
4. Evaluate Dutch n-grams (also available)

## Success Criteria

1. **Functional**: Missing apostrophes detected in English
2. **Performance**: <100ms latency increase
3. **Resource**: Within 4GB heap limit
4. **Coverage**: Both en-US and sv-SE supported
5. **Maintainable**: Automated build process

## Notes

- N-gram data is versioned but rarely updated (English: 2015, Swedish: 2012)
- Consider caching converted Swedish indexes in shared storage
- Monitor heap usage carefully with both language models loaded
- Document the one-time Swedish conversion process clearly

## Dependencies

- LanguageTool dev tools (for FrequencyIndexCreator)
- Maven (to build dev tools)
- ~25GB disk space
- 4GB available RAM

## References

1. [LanguageTool N-gram Documentation](https://dev.languagetool.org/finding-errors-using-n-gram-data.html)
2. [NST Swedish N-grams](https://www.nb.no/sprakbanken/ressurskatalog/oai-nb-no-sbr-11/)
3. [LanguageTool FrequencyIndexCreator](https://github.com/languagetool-org/languagetool/tree/master/languagetool-dev)
4. [Issue #10398: N-gram Downloads](https://github.com/languagetool-org/languagetool/issues/10398)

---

**Status**: Planning
**Priority**: Medium
**Estimated Effort**: 2-3 days
**Assigned**: TBD
