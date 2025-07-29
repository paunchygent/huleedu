# 🧠 ULTRATHINK SESSION: NLP Service Phase 1 Implementation

## CRITICAL: Read ALL Referenced Rules and Files BEFORE Starting

### MANDATORY READING ORDER:
1. `.cursor/rules/000-rule-index.mdc` - Complete rule reference
2. `.cursor/rules/010-foundational-principles.mdc` - Zero tolerance for vibe coding
3. `.cursor/rules/020-architectural-mandates.mdc` - Service boundaries and patterns
4. `.cursor/rules/042-async-patterns-and-di.mdc` - Worker service structure
5. `.cursor/rules/050-python-coding-standards.mdc` - Python implementation standards
6. `.cursor/rules/048-structured-error-handling-standards.mdc` - Error handling patterns
7. `.cursor/rules/070-testing-and-quality-assurance.mdc` - 90%+ coverage requirement

### MANDATORY FILE READING:
1. `TASKS/NLP_SERVICE_STUDENT_MATCHING_PHASE1_DRAFT.md` - Implementation plan (DRAFT)
2. `services/spellchecker_service/` - Reference pattern for worker services
3. `services/file_service/implementations/extraction_strategies.py` - Strategy pattern example
4. `services/essay_lifecycle_service/protocols.py` - For integration understanding
5. `common_core/src/common_core/events/` - Event model patterns

---

## 🎯 CURRENT MISSION: Implement NLP Service Phase 1 (Student Matching ONLY)

### Context & Progress Summary

**What We've Accomplished:**
1. ✅ Completed comprehensive test validation for File Service Strategy pattern (91% coverage)
2. ✅ Researched and designed NLP Service architecture following HuleEdu patterns
3. ✅ Created DRAFT implementation plan requiring architectural refinement

**Where We Are Now:**
The File Service successfully extracts text from essays using a Strategy pattern. The Batch Orchestrator publishes `BATCH_NLP_INITIATE_COMMAND` events expecting an NLP Service to process them. The Essay Lifecycle Service awaits `ESSAY_NLP_COMPLETED` events (contract needs updating to `ESSAY_AUTHOR_MATCH_SUGGESTED`).

**Critical Discovery:**
The NLP Service is NOT just for student matching - it's a comprehensive analytics platform that will eventually include:
- Phase 1: Student identification (IMPLEMENT NOW)
- Phase 2: Essay metrics (readability, complexity) - DO NOT IMPLEMENT
- Phase 3: [Removed - out of scope]
- Phase 4: Online CJ calibration - DO NOT IMPLEMENT
- Phase 5: Continuous learning - DO NOT IMPLEMENT

**Architectural Decision:**
We're implementing as "NLP Metrics Service" (keeping the broader name) but ONLY implementing Phase 1 functionality while ensuring the architecture supports future analyzers without refactoring.

---

## 🏗️ EXACTLY What Needs Implementation RIGHT NOW

### 1. Common Core Updates (FIRST PRIORITY)
```python
# Add to common_core/src/common_core/events/nlp_events.py (NEW FILE)
class StudentMatchSuggestion(BaseModel):
    student_id: str
    student_name: str
    confidence_score: float = Field(ge=0.0, le=1.0)
    match_reason: str  # "exact_name", "fuzzy_name", "email"

class EssayAuthorMatchSuggestedV1(BaseEventData):
    essay_id: str
    suggestions: list[StudentMatchSuggestion]
    match_status: str  # "HIGH_CONFIDENCE", "NEEDS_REVIEW", "NO_MATCH"

# Add to common_core/src/common_core/models/message_models.py
ESSAY_AUTHOR_MATCH_SUGGESTED = "essay.author.match.suggested.v1"
```

### 2. NLP Service Implementation Pattern
Follow `spellchecker_service` pattern EXACTLY:
- Kafka worker service consuming batch commands
- Process essays individually within batch
- Publish individual result events
- Use protocol-based dependency injection
- Implement comprehensive error handling

### 3. Key Integration Points
- **Consume**: `BATCH_NLP_INITIATE_COMMAND` from Batch Orchestrator
- **Fetch**: Essay text from Content Service (HTTP API)
- **Fetch**: Class roster from Class Management Service (HTTP API + Redis cache)
- **Publish**: `ESSAY_AUTHOR_MATCH_SUGGESTED` to Essay Lifecycle Service

### 4. Core Functionality (Phase 1 ONLY)
```python
# Student matching logic:
1. Extract emails with regex
2. Extract names from patterns (Name:, Student:, By:)
3. Fuzzy match against class roster
4. Assign confidence scores
5. Publish suggestions
```

---

## ⚠️ CRITICAL CONSTRAINTS & WARNINGS

1. **DO NOT IMPLEMENT** Phase 2+ features (metrics, calibration, etc.)
2. **DO NOT CREATE** complex analyzer frameworks - simple implementation first
3. **MUST FOLLOW** spellchecker_service patterns exactly
4. **MUST IMPLEMENT** Redis caching for class rosters (1-hour TTL)
5. **MUST ACHIEVE** 90%+ test coverage
6. **MUST USE** structured error handling from huleedu_service_libs

---

## 🚀 IMPLEMENTATION SEQUENCE

### Phase 1: Foundation (Use general-purpose agent)
1. Read ALL mandatory rules and files
2. Review DRAFT task document for gaps
3. Update common_core with new event models
4. Verify event contract compatibility

### Phase 2: Service Scaffold (Use code-implementation-specialist agent)
1. Create service structure following spellchecker pattern
2. Implement protocols.py with clean interfaces
3. Setup dependency injection (di.py)
4. Create config.py with environment variables

### Phase 3: Core Logic (Use code-implementation-specialist agent)
1. Implement student_matcher_impl.py with regex/fuzzy matching
2. Implement API clients (content, class management) with caching
3. Implement event_processor.py following established patterns
4. Add structured error handling throughout

### Phase 4: Testing (Use test-engineer agent)
1. Unit tests for matching algorithms
2. Integration tests with testcontainers
3. Contract tests for events
4. Achieve 90%+ coverage

### Phase 5: Integration (Use lead-architect-planner agent)
1. Update Essay Lifecycle Service to consume new events
2. Test end-to-end flow
3. Update documentation

---

## 📋 SUBAGENT RECOMMENDATIONS

1. **general-purpose**: Initial research and file reading
2. **lead-architect-planner**: Review implementation against patterns
3. **code-implementation-specialist**: Write production code
4. **test-engineer**: Comprehensive test suite
5. **documentation-maintainer**: Update service documentation

---

## 🎯 SUCCESS CRITERIA

✅ NLP Service processes batch commands successfully
✅ Accurately identifies students with confidence scores
✅ Follows ALL HuleEdu patterns (zero vibe coding)
✅ 90%+ test coverage
✅ Proper Redis caching implementation
✅ Structured error handling throughout
✅ Clean protocol-based architecture
✅ Phase 1 ONLY - no over-engineering

---

## 🔍 CONTEXT NOTES FOR OPTIMAL ALIGNMENT

1. **User Philosophy**: Extreme proponent of structured, planned development. HATES makeshift solutions.
2. **Monorepo Structure**: PDM-managed, Docker-based, PostgreSQL + Kafka + Redis
3. **Testing Philosophy**: Modern frameworks, explicit imports, testcontainers for integration
4. **Error Handling**: MUST use huleedu_service_libs structured patterns
5. **No AI Slop**: Avoid words like "refined" and "enhanced" in code/docs

---

## START HERE:

1. Use ULTRATHINK methodology throughout
2. Read ALL referenced rules and files FIRST
3. Review the DRAFT task document
4. Begin with common_core event model updates
5. Implement following exact patterns from spellchecker_service

**REMEMBER**: This is Phase 1 ONLY - student matching. The architecture should SUPPORT future analyzers but NOT implement them. Follow established patterns religiously - zero deviation tolerance.