---
id: "ai-feedback-service-implementation"
title: "AI Feedback Service Implementation Task"
type: "task"
status: "research"
priority: "medium"
domain: "assessment"
service: ""
owner_team: "agents"
owner: ""
program: ""
created: "2025-11-06"
last_updated: "2025-11-17"
related: []
labels: []
---
## Executive Summary

The AI Feedback Service is an intelligent prompt curator and orchestrator that collects pre-computed analyses from upstream services (Spellchecker, NLP, CJ Assessment) and uses this rich context to generate comprehensive AI-powered teacher feedback and edited essays. It acts as the final stage in the essay processing pipeline, consuming aggregated data to craft optimal prompts for LLM-based feedback generation.

## Architectural Overview

### Service Classification

- **Type**: Pure Kafka Worker Service (no client-facing APIs)
- **Pattern**: Event-driven consumer with batch processing
- **Template**: Based on CJ Assessment Service architecture
- **Domain**: Intelligent prompt curation and AI feedback orchestration

### Core Responsibility

**AI Feedback Service = Data Collector + Prompt Curator + LLM Orchestrator**

The service:

1. Collects pre-analyzed data from Result Aggregator
2. Builds rich context from upstream analyses (grammar, spelling, rankings)
3. Curates optimal prompts using this context
4. Orchestrates LLM calls for feedback and editing
5. Returns comprehensive feedback artifacts

### Key Architectural Decisions

1. **Sequential Pipeline Dependencies**:

   ```
   Required Upstream Completion:
   1. Spellchecker Service → spelling errors & corrected text
   2. NLP Service → grammar analysis & linguistic metrics
   
   Optional Upstream Completion:
   3. CJ Assessment Service → comparative rankings (if applicable)
   4. Assessment Service → AES scores (future)
   
   Data Flow:
   Result Aggregator → Aggregates all upstream results
   AI Feedback Service → Consumes aggregated data
   AI Feedback Service → Curates prompts with context
   AI Feedback Service → Orchestrates LLM calls
   ```

2. **Separation of Concerns**:
   - **Grammar Analysis**: Owned by NLP Service (NOT duplicated here)
   - **Spelling Correction**: Owned by Spellchecker Service
   - **Prompt Curation**: Owned by AI Feedback Service (core responsibility)
   - **LLM API Management**: Delegated to LLM Provider Service

3. **Event Flow**:

   ```
   ELS → Publishes BatchAIFeedbackRequestedV1 (after upstream completion)
   AI Feedback → Consumes request
   AI Feedback → Fetches aggregated data from Result Aggregator (HTTP)
   AI Feedback → Builds context and curates prompts
   AI Feedback → Calls LLM Provider Service for generation (HTTP)
   AI Feedback → Stores results via Content Service (HTTP)
   AI Feedback → Publishes BatchAIFeedbackCompletedV1
   ELS → Aggregates results into ELSBatchPhaseOutcomeV1
   ```

4. **Infrastructure Mandates**:
   - All Kafka operations via `huleedu-service-libs.KafkaBus`
   - All HTTP operations via `aiohttp` with circuit breakers
   - Idempotency via `huleedu-service-libs.idempotency_v2`
   - Structured error handling via `huleedu-service-libs.error_handling`

## Implementation Phases

### Phase 1: Service Scaffolding and Event Contracts

#### 1.1 Event Contract Updates

**Location**: `libs/common_core/src/common_core/events/ai_feedback_events.py`

```python
# REFACTOR existing AIFeedbackResultDataV1 to use thin event pattern
from common_core.metadata_models import StorageReferenceMetadata

class AIFeedbackResultDataV1(ProcessingUpdate):
    """
    Thin event pattern with storage references for feedback artifacts.
    Published by AI Feedback Service, consumed by ELS.
    """
    event_name: ProcessingEvent = Field(
        default=ProcessingEvent.ESSAY_AIFEEDBACK_COMPLETED
    )
    
    # Replace feedback_content_storage_id with standard pattern
    storage_references: StorageReferenceMetadata = Field(
        description="References to stored feedback artifacts: feedback_text, edited_essay, grammar_analysis"
    )
    
    feedback_metadata: AIFeedbackMetadata = Field(
        description="Metadata about feedback generation (model versions, timings, flags)"
    )
    
    generated_components: dict[str, bool] = Field(
        default_factory=dict,
        description="Success flags: feedback, edited_essay, grammar_analysis"
    )
    
    processing_metrics: dict[str, float] = Field(
        default_factory=dict,
        description="Performance metrics: feedback_generation_ms, editing_ms, grammar_analysis_ms"
    )

# ADD new batch-level events
class BatchAIFeedbackRequestedV1(BaseEventData):
    """
    Batch request from ELS to AI Feedback Service.
    Publisher: Essay Lifecycle Service
    Consumer: AI Feedback Service
    Topic: batch.ai.feedback.requested
    
    Note: Following DDD Name Propagation Refactor, teacher names are NOT included
    in events. AI Feedback Service resolves teacher name via Identity Service
    using owner_user_id. Student names resolved via CMS internal endpoints.
    """
    event_name: ProcessingEvent = ProcessingEvent.BATCH_AI_FEEDBACK_REQUESTED
    batch_id: str = Field(description="Batch identifier")
    essay_refs: list[str] = Field(description="Essay IDs to process")
    owner_user_id: str = Field(description="Batch owner user ID for teacher name resolution via Identity Service")
    processing_config: dict[str, Any] | None = Field(
        default=None,
        description="Optional overrides: model_selection, temperature, etc."
    )

class BatchAIFeedbackCompletedV1(BaseEventData):
    """
    Batch completion from AI Feedback Service to ELS.
    Publisher: AI Feedback Service
    Consumer: Essay Lifecycle Service
    Topic: batch.ai.feedback.completed
    """
    event_name: ProcessingEvent = ProcessingEvent.BATCH_AI_FEEDBACK_COMPLETED
    batch_id: str = Field(description="Batch identifier")
    results: list[AIFeedbackResultDataV1] = Field(
        description="Individual essay results"
    )
    processing_summary: dict[str, int] = Field(
        default_factory=dict,
        description="Counts: total, succeeded, failed, partial"
    )
    batch_metrics: dict[str, float] = Field(
        default_factory=dict,
        description="Batch-level metrics: total_duration_seconds, avg_essay_duration_seconds"
    )
```

#### 1.2 Service Directory Structure (Simplified)

```
services/ai_feedback_service/
├── Dockerfile
├── pyproject.toml
├── alembic.ini                    # For future state tracking if needed
├── alembic/
│   └── versions/
├── worker_main.py                 # Service entrypoint & Kafka consumer
├── config.py                      # Pydantic Settings
├── protocols.py                   # typing.Protocol interfaces
├── di.py                          # Dishka providers
├── event_processor.py             # Main orchestration logic
├── metrics.py                     # Prometheus metrics
├── implementations/
│   ├── __init__.py
│   ├── result_aggregator_client_impl.py  # Fetch aggregated essay data
│   ├── content_client_impl.py            # Store feedback artifacts
│   ├── llm_provider_client_impl.py       # LLM API interactions
│   ├── identity_client_impl.py           # HTTP client for teacher names (Phase 5)
│   ├── cms_client_impl.py                # HTTP client for student names (Phase 5)
│   └── event_publisher_impl.py           # Kafka publishing
├── core_logic/
│   ├── __init__.py
│   ├── domain_models.py          # FeedbackContext, AggregatedData models
│   ├── prompt_manager.py         # All prompt templates & selection
│   ├── context_builder.py        # Build rich context from aggregated data
│   └── llm_workflows.py          # Feedback & editing orchestration ONLY
└── tests/
    ├── __init__.py
    ├── conftest.py
    ├── unit/
    │   ├── test_prompt_manager.py
    │   ├── test_context_builder.py
    │   └── test_llm_workflows.py
    └── integration/
        └── test_ai_feedback_workflow.py
```

**Note the removals:**

- ❌ `class_management_client_impl.py` - Student associations come via Result Aggregator
- ❌ `text_utils.py` - Text preprocessing done by upstream services
- ❌ `result_curation.py` - Grammar curation done by NLP Service

### Phase 1.5: DDD Name Resolution HTTP Clients (Phase 5 Implementation)

**Context**: Following the DDD Name Propagation Refactor Plan (Phase 5), AI Feedback Service must resolve names via HTTP calls rather than receiving them in events/data models. This ensures clean bounded contexts and keeps PII out of Kafka.

#### 1.5.1 Identity Client Implementation

**Purpose**: Resolve teacher names using `owner_user_id` from batch commands

**Location**: `implementations/identity_client_impl.py`

```python
"""HTTP client for Identity Service name resolution."""

from aiohttp import ClientSession, ClientTimeout, ClientError
from datetime import timedelta
from uuid import UUID
from typing import Optional

from common_core.metadata_models import PersonNameV1
from huleedu_service_libs.resilience import CircuitBreaker
from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.error_handling import raise_processing_error

from ..protocols import IdentityClientProtocol

logger = create_service_logger("identity_client")

class IdentityClientImpl(IdentityClientProtocol):
    """HTTP client for resolving teacher names via Identity Service."""
    
    def __init__(self, session: ClientSession, settings: Settings):
        self.session = session
        self.base_url = settings.IDENTITY_SERVICE_URL
        self.circuit_breaker = CircuitBreaker(
            name="ai_feedback.identity",
            failure_threshold=3,
            recovery_timeout=timedelta(seconds=30),
            success_threshold=2,
            expected_exception=ClientError
        )
    
    async def get_user_person_name(
        self, user_id: str, correlation_id: UUID
    ) -> PersonNameV1:
        """
        Resolve teacher name via Identity Service profile endpoint.
        
        Args:
            user_id: The owner_user_id from batch command
            correlation_id: Request correlation ID
            
        Returns:
            PersonNameV1 with teacher name or default on failure
        """
        try:
            async with self.circuit_breaker:
                url = f"{self.base_url}/v1/users/{user_id}/profile"
                headers = {"X-Correlation-ID": str(correlation_id)}
                timeout = ClientTimeout(total=5)
                
                async with self.session.get(url, headers=headers, timeout=timeout) as response:
                    if response.status == 404:
                        logger.warning(f"Teacher profile not found for user {user_id}")
                        return self._get_default_teacher_name()
                    
                    response.raise_for_status()
                    data = await response.json()
                    
                    person_name = data.get("person_name", {})
                    return PersonNameV1(
                        first_name=person_name.get("first_name", "Unknown"),
                        last_name=person_name.get("last_name", "Teacher"),
                        legal_full_name=person_name.get("legal_full_name")
                    )
                    
        except Exception as e:
            logger.warning(
                f"Failed to resolve teacher name for user {user_id}: {e}",
                extra={"user_id": user_id, "correlation_id": str(correlation_id)}
            )
            return self._get_default_teacher_name()
    
    def _get_default_teacher_name(self) -> PersonNameV1:
        """Return default teacher name for graceful degradation."""
        return PersonNameV1(
            first_name="Unknown",
            last_name="Teacher", 
            legal_full_name=None
        )
```

#### 1.5.2 CMS Client Implementation

**Purpose**: Resolve student names using essay/batch associations

**Location**: `implementations/cms_client_impl.py`

```python
"""HTTP client for CMS student name resolution."""

from aiohttp import ClientSession, ClientTimeout, ClientError
from datetime import timedelta
from uuid import UUID
from typing import Optional

from common_core.metadata_models import PersonNameV1
from huleedu_service_libs.resilience import CircuitBreaker
from huleedu_service_libs.logging_utils import create_service_logger

from ..protocols import CMSClientProtocol

logger = create_service_logger("cms_client")

class CMSClientImpl(CMSClientProtocol):
    """HTTP client for resolving student names via CMS internal endpoints."""
    
    def __init__(self, session: ClientSession, settings: Settings):
        self.session = session
        self.base_url = settings.CMS_SERVICE_URL
        self.circuit_breaker = CircuitBreaker(
            name="ai_feedback.cms",
            failure_threshold=3,
            recovery_timeout=timedelta(seconds=30),
            success_threshold=2,
            expected_exception=ClientError
        )
    
    async def get_batch_student_names(
        self, batch_id: str, correlation_id: UUID
    ) -> list[dict]:
        """
        Batch resolve all student names for a batch.
        
        Args:
            batch_id: The batch ID
            correlation_id: Request correlation ID
            
        Returns:
            List of essay->student mappings with PersonNameV1
        """
        try:
            async with self.circuit_breaker:
                url = f"{self.base_url}/internal/v1/batches/{batch_id}/student-names"
                headers = {"X-Correlation-ID": str(correlation_id)}
                timeout = ClientTimeout(total=10)  # Longer for batch operations
                
                async with self.session.get(url, headers=headers, timeout=timeout) as response:
                    if response.status == 404:
                        logger.info(f"No student associations found for batch {batch_id}")
                        return []
                    
                    response.raise_for_status()
                    return await response.json()
                    
        except Exception as e:
            logger.warning(
                f"Failed to resolve batch student names for {batch_id}: {e}",
                extra={"batch_id": batch_id, "correlation_id": str(correlation_id)}
            )
            return []
    
    async def get_essay_student_name(
        self, essay_id: str, correlation_id: UUID
    ) -> PersonNameV1 | None:
        """
        Resolve student name for a single essay.
        
        Args:
            essay_id: The essay ID
            correlation_id: Request correlation ID
            
        Returns:
            PersonNameV1 with student name or None if not found
        """
        try:
            async with self.circuit_breaker:
                url = f"{self.base_url}/internal/v1/associations/essay/{essay_id}"
                headers = {"X-Correlation-ID": str(correlation_id)}
                timeout = ClientTimeout(total=5)
                
                async with self.session.get(url, headers=headers, timeout=timeout) as response:
                    if response.status == 404:
                        logger.info(f"No student association found for essay {essay_id}")
                        return None
                    
                    response.raise_for_status()
                    data = await response.json()
                    
                    person_name = data.get("student_person_name", {})
                    return PersonNameV1(
                        first_name=person_name.get("first_name", "Student"),
                        last_name=person_name.get("last_name", ""),
                        legal_full_name=person_name.get("legal_full_name")
                    )
                    
        except Exception as e:
            logger.warning(
                f"Failed to resolve student name for essay {essay_id}: {e}",
                extra={"essay_id": essay_id, "correlation_id": str(correlation_id)}
            )
            return None
```

#### 1.5.3 Graceful Degradation Strategy

**Name Resolution Fallback Behavior**:

1. **Teacher Name Resolution Failure**:
   - Circuit breaker open → Use PersonNameV1("Unknown", "Teacher", None)
   - Identity Service 404 → Use PersonNameV1("Unknown", "Teacher", None)
   - Network timeout → Use PersonNameV1("Unknown", "Teacher", None)

2. **Student Name Resolution Failure**:
   - Circuit breaker open → Use "the student" in prompts
   - CMS Service empty response → Use "the student" in prompts
   - Network timeout → Use "the student" in prompts

3. **Observability**:
   - Log all fallback scenarios with correlation IDs
   - Metrics track resolution success/failure rates
   - Structured logs include user_id, essay_id, batch_id context

**Critical Design Principle**: AI Feedback generation continues even when name services are unavailable, ensuring service resilience while maintaining DDD boundaries.

### Phase 2: Core Logic Implementation

#### 2.1 Prompt Management (`core_logic/prompt_manager.py`)

**Extract from prototype lines**: 100-571, 574-630, 2704-2735
**Purpose**: Maintain all prompt templates and course-based selection logic

```python
"""Prompt template management for AI Feedback Service."""

from common_core.domain_enums import CourseCode
from typing import TypedDict

# Extract all prompt constants (lines 100-571)
MASTER_SYSTEM_PROMPT_ENG = """..."""  # Line 100-110
MASTER_SYSTEM_PROMPT_SWE = """..."""  # Line 112-131
SYSTEM_MESSAGE_ENG5 = """..."""       # Line 134-219
SYSTEM_MESSAGE_ENG6 = """..."""       # Line 220-223
SYSTEM_MESSAGE_ENG7 = """..."""       # Line 224-297
SYSTEM_MESSAGE_SVE1 = """..."""       # Line 298-347
SYSTEM_MESSAGE_SVE2 = """..."""       # Line 348-351
SYSTEM_MESSAGE_SVE3 = """..."""       # Line 352-355

GRAMMAR_ANALYSIS_ENG5 = """..."""     # Line 358-428
GRAMMAR_ANALYSIS_ENG6 = """..."""     # Line 430-438
GRAMMAR_ANALYSIS_ENG7 = """..."""     # Line 440-500
GRAMMAR_ANALYSIS_SVE1 = """..."""     # Line 502-556
GRAMMAR_ANALYSIS_SVE2 = """..."""     # Line 558-562
GRAMMAR_ANALYSIS_SVE3 = """..."""     # Line 564-571

# Extract EDITOR_PROMPTS dict (lines 2704-2735)
EDITOR_PROMPTS = {
    'en-US': {
        'original_label': "<CORRECTED ESSAY TEXT (LanguageTool Pass):>",
        'teacher_feedback_label': "<TEACHER FEEDBACK:>",
        'task_label': "<INSTRUCTIONS/YOUR TASK:>",
        # ... etc
    },
    'sv-SE': {
        'original_label': "<GRANSKAD TEXT (LanguageTool):>",
        'teacher_feedback_label': "<lararfeedback>",
        # ... etc
    }
}

class PromptSet(TypedDict):
    """Type definition for a complete prompt set."""
    master_system: str
    feedback_system: str
    grammar_analysis: str
    editor_prompts: dict[str, str]
    language_code: str  # 'en-US' or 'sv-SE'

def select_prompts(course_code: CourseCode) -> PromptSet:
    """
    Select appropriate prompts based on course code.
    Re-implementation of prototype lines 577-630.
    """
    # Course to prompt mappings
    system_message_map = {
        CourseCode.ENGLISH_5: SYSTEM_MESSAGE_ENG5,
        CourseCode.ENGLISH_6: SYSTEM_MESSAGE_ENG6,
        CourseCode.ENGLISH_7: SYSTEM_MESSAGE_ENG7,
        CourseCode.SVENSKA_1: SYSTEM_MESSAGE_SVE1,
        CourseCode.SVENSKA_2: SYSTEM_MESSAGE_SVE2,
        CourseCode.SVENSKA_3: SYSTEM_MESSAGE_SVE3,
    }
    
    grammar_prompt_map = {
        CourseCode.ENGLISH_5: GRAMMAR_ANALYSIS_ENG5,
        CourseCode.ENGLISH_6: GRAMMAR_ANALYSIS_ENG6,
        CourseCode.ENGLISH_7: GRAMMAR_ANALYSIS_ENG7,
        CourseCode.SVENSKA_1: GRAMMAR_ANALYSIS_SVE1,
        CourseCode.SVENSKA_2: GRAMMAR_ANALYSIS_SVE2,
        CourseCode.SVENSKA_3: GRAMMAR_ANALYSIS_SVE3,
    }
    
    # Determine language and master prompt
    is_swedish = course_code in [CourseCode.SVENSKA_1, CourseCode.SVENSKA_2, CourseCode.SVENSKA_3]
    
    return PromptSet(
        master_system=MASTER_SYSTEM_PROMPT_SWE if is_swedish else MASTER_SYSTEM_PROMPT_ENG,
        feedback_system=system_message_map[course_code],
        grammar_analysis=grammar_prompt_map[course_code],
        editor_prompts=EDITOR_PROMPTS['sv-SE'] if is_swedish else EDITOR_PROMPTS['en-US'],
        language_code='sv-SE' if is_swedish else 'en-US'
    )
```

#### 2.2 Context Builder (`core_logic/context_builder.py`)

**NEW MODULE - Not in prototype**
**Purpose**: Build rich feedback context from aggregated upstream analyses

```python
"""Context building for intelligent prompt curation."""

from typing import Optional
from ..domain_models import (
    FeedbackContext, 
    GrammarIssue,
    SpellingError,
    CJRanking,
    AESScore,
    NLPMetrics
)

def build_feedback_context(
    nlp_metrics: NLPMetrics,
    spelling_errors: list[SpellingError],
    cj_ranking: Optional[CJRanking] = None,
    aes_score: Optional[AESScore] = None  # Future
) -> FeedbackContext:
    """
    Build rich context from all upstream analyses.
    This is the intelligence layer - determining what context
    matters for different feedback types.
    
    Args:
        nlp_metrics: Grammar issues, readability scores from NLP Service
        spelling_errors: Errors from Spellchecker Service
        cj_ranking: Comparative ranking from CJ Assessment (if available)
        aes_score: AES score from Assessment Service (future)
    
    Returns:
        FeedbackContext with curated insights for prompt generation
    """
    context = FeedbackContext()
    
    # Summarize grammar patterns from NLP analysis
    context.grammar_summary = _summarize_grammar_patterns(
        nlp_metrics.grammar_issues
    )
    context.grammar_count = len(nlp_metrics.grammar_issues)
    
    # Identify recurring spelling patterns
    context.spelling_patterns = _identify_spelling_patterns(spelling_errors)
    context.spelling_error_count = len(spelling_errors)
    
    # Add readability metrics from NLP
    context.readability_score = nlp_metrics.readability_score
    context.complexity_level = nlp_metrics.complexity_level
    
    # Add comparative context if available
    if cj_ranking:
        context.comparative_position = _format_ranking_context(cj_ranking)
        context.peer_comparison = _build_peer_comparison(cj_ranking)
    
    # Future: Add assessment insights
    if aes_score:
        context.assessment_insights = _format_assessment_context(aes_score)
        context.strength_areas = aes_score.strength_areas
        context.improvement_areas = aes_score.improvement_areas
    
    return context

def _summarize_grammar_patterns(issues: list[GrammarIssue]) -> str:
    """
    Create a summary of grammar patterns for prompt context.
    Groups issues by category and identifies recurring patterns.
    """
    if not issues:
        return "No significant grammar issues detected."
    
    # Group by category
    by_category = {}
    for issue in issues:
        category = issue.category
        if category not in by_category:
            by_category[category] = []
        by_category[category].append(issue)
    
    # Build summary
    summary_parts = []
    for category, category_issues in by_category.items():
        count = len(category_issues)
        examples = category_issues[:2]  # First 2 examples
        example_text = ", ".join([f"'{i.original_text}'" for i in examples])
        summary_parts.append(f"{category}: {count} issues (e.g., {example_text})")
    
    return "; ".join(summary_parts)

def _identify_spelling_patterns(errors: list[SpellingError]) -> str:
    """Identify patterns in spelling errors for targeted feedback."""
    if not errors:
        return "No spelling errors detected."
    
    # Categorize errors
    patterns = []
    
    # Common patterns to detect
    homophones = [e for e in errors if e.error_type == "homophone"]
    typos = [e for e in errors if e.error_type == "typo"]
    
    if homophones:
        patterns.append(f"Homophone confusion ({len(homophones)} instances)")
    if typos:
        patterns.append(f"Typographical errors ({len(typos)} instances)")
    
    return "; ".join(patterns) if patterns else "Minor spelling issues"

def _format_ranking_context(ranking: CJRanking) -> str:
    """Format CJ ranking for feedback context."""
    percentile = ranking.percentile
    if percentile >= 90:
        return "Top 10% of class"
    elif percentile >= 75:
        return "Top 25% of class"
    elif percentile >= 50:
        return "Above average"
    elif percentile >= 25:
        return "Below average"
    else:
        return "Bottom 25% of class"

def _build_peer_comparison(ranking: CJRanking) -> str:
    """Build peer comparison insights."""
    strengths = ranking.relative_strengths
    weaknesses = ranking.relative_weaknesses
    
    comparison_parts = []
    if strengths:
        comparison_parts.append(f"Stronger than peers in: {', '.join(strengths)}")
    if weaknesses:
        comparison_parts.append(f"Areas for improvement: {', '.join(weaknesses)}")
    
    return "; ".join(comparison_parts)
```

#### 2.3 Domain Models (`core_logic/domain_models.py`)

**Simplified models - Most data comes pre-analyzed from upstream**

```python
"""Domain models for AI Feedback Service."""

from pydantic import BaseModel, Field
from typing import Any, Optional
from common_core.domain_enums import CourseCode

# Models for aggregated data from upstream services

class GrammarIssue(BaseModel):
    """Grammar issue from NLP Service."""
    category: str  # GRAMMAR, PUNCTUATION, COHESION, STYLE
    original_text: str
    suggestion: str
    explanation: str
    severity: str  # high, medium, low

class SpellingError(BaseModel):
    """Spelling error from Spellchecker Service."""
    word: str
    suggestions: list[str]
    error_type: str  # typo, homophone, etc.
    context: str

class NLPMetrics(BaseModel):
    """Aggregated NLP analysis from NLP Service."""
    grammar_issues: list[GrammarIssue]
    readability_score: float
    complexity_level: str
    sentence_count: int
    avg_sentence_length: float
    vocabulary_diversity: float

class CJRanking(BaseModel):
    """Comparative judgment results from CJ Assessment."""
    rank: int
    percentile: float
    score: float
    relative_strengths: list[str]
    relative_weaknesses: list[str]
    comparison_count: int

class AESScore(BaseModel):
    """Future: Assessment score from Assessment Service."""
    overall_score: float
    component_scores: dict[str, float]
    strength_areas: list[str]
    improvement_areas: list[str]
    feedback_suggestions: list[str]

class AggregatedEssayData(BaseModel):
    """Complete aggregated data from Result Aggregator.
    
    Note: Following DDD Name Propagation Refactor, names are NOT included in data models.
    Names are resolved via HTTP:
    - Teacher names via Identity Service using owner_user_id
    - Student names via CMS internal endpoints using essay_id/batch_id
    """
    # Identity
    essay_id: str
    batch_id: str
    
    # Essay content (already spellchecked)
    corrected_text_storage_id: str  # Spellchecked version
    original_text_storage_id: str   # Original submission
    
    # Context
    owner_user_id: str  # For teacher name resolution via Identity Service
    course_code: CourseCode
    student_prompt_storage_id: Optional[str]
    student_prompt_text: Optional[str]
    class_designation: Optional[str]
    # Note: student_name and teacher_name removed - resolved via HTTP clients
    
    # Aggregated analyses
    nlp_metrics: NLPMetrics
    spelling_errors: list[SpellingError]
    cj_ranking: Optional[CJRanking] = None
    aes_score: Optional[AESScore] = None  # Future
    
    # Metadata
    word_count: int
    processing_timestamp: str

class FeedbackContext(BaseModel):
    """Rich context built from aggregated data for prompt curation."""
    # Grammar insights
    grammar_summary: str
    grammar_count: int
    
    # Spelling insights  
    spelling_patterns: str
    spelling_error_count: int
    
    # Readability metrics
    readability_score: float
    complexity_level: str
    
    # Comparative insights (if available)
    comparative_position: Optional[str] = None
    peer_comparison: Optional[str] = None
    
    # Assessment insights (future)
    assessment_insights: Optional[str] = None
    strength_areas: Optional[list[str]] = None
    improvement_areas: Optional[list[str]] = None

class PromptComponents(BaseModel):
    """Components for building LLM prompts."""
    system_prompt: str
    user_prompt: str
    context_section: str
    instructions_section: str
    analysis_section: str
```

#### 2.4 LLM Workflows (`core_logic/llm_workflows.py`)

**SIMPLIFIED - Only feedback and editing, NO grammar analysis**
**Extract from prototype lines**: 2570-2860 (feedback & editing only)

```python
"""LLM workflow orchestration for AI Feedback Service."""

import re
from typing import Optional
from uuid import UUID

from huleedu_service_libs.logging_utils import create_service_logger
from common_core.domain_enums import CourseCode

from ..protocols import LLMProviderClientProtocol
from .domain_models import FeedbackContext, PromptComponents
from .prompt_manager import select_prompts

logger = create_service_logger("llm_workflows")

async def generate_feedback(
    essay_text: str,
    student_name: str,
    instructions: str,
    course_code: CourseCode,
    context: FeedbackContext,  # Rich context from upstream analyses
    llm_client: LLMProviderClientProtocol,
    correlation_id: UUID,
    model_config: Optional[dict] = None
) -> Optional[str]:
    """
    Generate teacher-style feedback using rich context.
    Adapted from prototype lines 2570-2736.
    
    Args:
        essay_text: The spellchecked essay text
        student_name: Student's name for personalization
        instructions: Original essay instructions
        course_code: Course for prompt selection
        context: Rich context from all upstream analyses
        llm_client: LLM provider client
        correlation_id: Request correlation ID
        model_config: Optional model configuration overrides
    
    Returns:
        Generated feedback text or None on failure
    """
    prompts = select_prompts(course_code)
    
    # Build context-aware prompt
    context_section = _build_context_section(context)
    
    # Format the user prompt with rich context
    user_prompt = f"""
ANALYSIS CONTEXT:
{context_section}

ESSAY INSTRUCTIONS:
{instructions}

STUDENT ESSAY:
{essay_text}

Based on the analysis context above, provide comprehensive feedback for {student_name}.
Consider the grammar issues, spelling patterns, and readability metrics when crafting your feedback.
"""
    
    # Add comparative context if available
    if context.comparative_position:
        user_prompt += f"\nCOMPARATIVE STANDING: {context.comparative_position}"
        if context.peer_comparison:
            user_prompt += f"\n{context.peer_comparison}"
    
    # Prepare model configuration
    config = model_config or {
        "provider": "anthropic",
        "model": "claude-3-sonnet-20240229",
        "temperature": 0.3,
        "max_tokens": 2000
    }
    
    try:
        response = await llm_client.request_feedback(
            system_prompt=f"{prompts['master_system']}\n\n{prompts['feedback_system']}",
            user_prompt=user_prompt.replace("{student_name}", student_name),
            model_config=config,
            correlation_id=correlation_id
        )
        
        if response and "content" in response:
            logger.info(
                f"Generated feedback for essay",
                extra={
                    "correlation_id": str(correlation_id),
                    "word_count": len(response["content"].split()),
                    "has_comparative": bool(context.comparative_position)
                }
            )
            return response["content"]
        
        logger.warning(f"Empty feedback response for correlation_id={correlation_id}")
        return None
        
    except Exception as e:
        logger.error(f"Failed generating feedback: {e}", exc_info=True)
        return None

async def generate_edited_version(
    corrected_text: str,  # Already spellchecked from upstream
    feedback: str,
    course_code: CourseCode,
    context: FeedbackContext,
    llm_client: LLMProviderClientProtocol,
    correlation_id: UUID,
    model_config: Optional[dict] = None
) -> Optional[str]:
    """
    Generate edited version incorporating teacher feedback and analysis context.
    Adapted from prototype lines 2738-2860.
    
    Args:
        corrected_text: Spellchecked essay from Spellchecker Service
        feedback: Generated teacher feedback
        course_code: Course for prompt selection
        context: Rich context from analyses
        llm_client: LLM provider client
        correlation_id: Request correlation ID
        model_config: Optional model configuration overrides
    
    Returns:
        Edited essay text or None on failure
    """
    prompts = select_prompts(course_code)
    editor_prompts = prompts['editor_prompts']
    
    # Build grammar context for editing
    grammar_context = ""
    if context.grammar_count > 0:
        grammar_context = f"""
GRAMMAR ISSUES TO ADDRESS:
{context.grammar_summary}
Total issues: {context.grammar_count}
"""
    
    # Format prompt using editor template with context
    user_prompt = f"""{editor_prompts['original_label']}
{corrected_text}
</{editor_prompts['original_label'][1:]}

{grammar_context}

{editor_prompts['teacher_feedback_label']}
{feedback}
</{editor_prompts['teacher_feedback_label'][1:]}

{editor_prompts['task_label']}
{editor_prompts['task_instruction_1']}
{editor_prompts['task_instruction_2']}
{editor_prompts['task_instruction_3']}
{editor_prompts['task_instruction_4']}
{editor_prompts['output_instruction']}
"""
    
    config = model_config or {
        "provider": "openai",
        "model": "gpt-4o",
        "temperature": 0.3,
        "max_tokens": 2500
    }
    
    try:
        response = await llm_client.request_edit(
            system_prompt=editor_prompts['system_message_role'],
            user_prompt=user_prompt,
            model_config=config,
            correlation_id=correlation_id
        )
        
        if response and "content" in response:
            # Extract from <redigerad_text> tags if present
            content = response["content"]
            match = re.search(
                r"<redigerad_text>(.*?)</redigerad_text>", 
                content, 
                re.DOTALL | re.IGNORECASE
            )
            
            edited_text = match.group(1).strip() if match else content.strip()
            
            # Basic validation
            if len(edited_text) < len(corrected_text) * 0.5:
                logger.warning("Edited text significantly shorter than original")
            
            logger.info(
                f"Generated edited version",
                extra={
                    "correlation_id": str(correlation_id),
                    "original_length": len(corrected_text),
                    "edited_length": len(edited_text)
                }
            )
            
            return edited_text
        
        return None
        
    except Exception as e:
        logger.error(f"Failed generating edited version: {e}", exc_info=True)
        return None

def _build_context_section(context: FeedbackContext) -> str:
    """
    Build a formatted context section for the prompt.
    
    Args:
        context: Rich feedback context
    
    Returns:
        Formatted context string for prompt inclusion
    """
    sections = []
    
    # Grammar analysis
    sections.append(f"Grammar Analysis: {context.grammar_summary}")
    sections.append(f"Grammar Issues Count: {context.grammar_count}")
    
    # Spelling analysis
    sections.append(f"Spelling Patterns: {context.spelling_patterns}")
    sections.append(f"Spelling Errors Count: {context.spelling_error_count}")
    
    # Readability metrics
    sections.append(f"Readability Score: {context.readability_score:.1f}")
    sections.append(f"Complexity Level: {context.complexity_level}")
    
    # Optional comparative context
    if context.comparative_position:
        sections.append(f"Class Standing: {context.comparative_position}")
    
    # Future: Assessment context
    if context.assessment_insights:
        sections.append(f"Assessment Insights: {context.assessment_insights}")
    
    return "\n".join(sections)

# REMOVED FUNCTIONS:
# - analyze_grammar_chunk() - Grammar analysis done by NLP Service
# - validate_grammar_issues_batch() - Validation done by NLP Service
# - All grammar-related workflows moved to NLP Service
```

**Note: Result curation module REMOVED - Grammar curation is handled by NLP Service**

### Phase 3: Service Implementation

#### 3.1 Protocols (`protocols.py`)

```python
"""Protocol interfaces for AI Feedback Service."""

from typing import Protocol, Any
from uuid import UUID

from .core_logic.domain_models import AggregatedEssayData
from common_core.events.ai_feedback_events import BatchAIFeedbackCompletedV1

class ResultAggregatorClientProtocol(Protocol):
    """Interface for Result Aggregator Service."""
    
    async def fetch_aggregated_data(
        self, 
        essay_id: str, 
        correlation_id: UUID
    ) -> AggregatedEssayData:
        """
        Fetch complete pre-aggregated essay data including:
        - Spellchecked essay content
        - NLP metrics (grammar, readability)
        - Spelling errors
        - CJ rankings (if available)
        - Student association
        - Course and instruction context
        """
        ...

class ContentClientProtocol(Protocol):
    """Interface for Content Service."""
    
    async def fetch_content(
        self, 
        storage_id: str, 
        correlation_id: UUID
    ) -> str:
        """Fetch essay text content by storage ID."""
        ...
    
    async def store_content(
        self,
        content: str,
        content_type: str,
        correlation_id: UUID
    ) -> str:
        """Store content and return storage_id."""
        ...

class LLMProviderClientProtocol(Protocol):
    """Interface for LLM Provider Service."""
    
    async def request_feedback(
        self,
        system_prompt: str,
        user_prompt: str,
        model_config: dict[str, Any],
        correlation_id: UUID
    ) -> dict[str, Any]:
        """Request feedback generation from LLM."""
        ...
    
    async def request_edit(
        self,
        system_prompt: str,
        user_prompt: str,
        model_config: dict[str, Any],
        correlation_id: UUID
    ) -> dict[str, Any]:
        """Request essay editing from LLM."""
        ...

class IdentityClientProtocol(Protocol):
    """Interface for Identity Service HTTP client (DDD Phase 5)."""
    
    async def get_user_person_name(
        self, user_id: str, correlation_id: UUID
    ) -> PersonNameV1:
        """
        Resolve teacher name via Identity Service using owner_user_id.
        
        Args:
            user_id: The owner_user_id from batch command
            correlation_id: Request correlation ID
            
        Returns:
            PersonNameV1 with teacher name or default on failure
        """
        ...

class CMSClientProtocol(Protocol):
    """Interface for CMS HTTP client (DDD Phase 5)."""
    
    async def get_batch_student_names(
        self, batch_id: str, correlation_id: UUID
    ) -> list[dict]:
        """
        Batch resolve all student names for a batch.
        
        Args:
            batch_id: The batch ID
            correlation_id: Request correlation ID
            
        Returns:
            List of essay->student mappings with PersonNameV1
        """
        ...
    
    async def get_essay_student_name(
        self, essay_id: str, correlation_id: UUID
    ) -> PersonNameV1 | None:
        """
        Resolve student name for a single essay.
        
        Args:
            essay_id: The essay ID
            correlation_id: Request correlation ID
            
        Returns:
            PersonNameV1 with student name or None if not found
        """
        ...

class EventPublisherProtocol(Protocol):
    """Interface for publishing events to Kafka."""
    
    async def publish_batch_completion(
        self,
        event: BatchAIFeedbackCompletedV1,
        correlation_id: UUID
    ) -> None:
        """Publish batch completion event."""
        ...
```

#### 3.2 Event Processor (`event_processor.py`)

```python
"""Main event processing orchestration for AI Feedback Service."""

import asyncio
from datetime import UTC, datetime
from typing import Optional
from uuid import UUID

from common_core.events.ai_feedback_events import (
    BatchAIFeedbackRequestedV1,
    BatchAIFeedbackCompletedV1,
    AIFeedbackResultDataV1,
    AIFeedbackMetadata
)
from common_core.metadata_models import StorageReferenceMetadata
from common_core.status_enums import EssayStatus
from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.error_handling import HuleEduError

from .protocols import *
from .core_logic import (
    llm_workflows,
    context_builder,
    domain_models
)
from .config import Settings

logger = create_service_logger("event_processor")

class AIFeedbackEventProcessor:
    """
    Orchestrates AI feedback generation by collecting data,
    building context, and curating prompts for LLM calls.
    """
    
    def __init__(
        self,
        result_aggregator: ResultAggregatorClientProtocol,
        content_client: ContentClientProtocol,
        llm_client: LLMProviderClientProtocol,
        event_publisher: EventPublisherProtocol,
        settings: Settings
    ):
        self.result_aggregator = result_aggregator
        self.content_client = content_client
        self.llm_client = llm_client
        self.event_publisher = event_publisher
        self.settings = settings
        self.semaphore = asyncio.Semaphore(settings.MAX_CONCURRENT_ESSAYS)
    
    async def process_batch_event(
        self,
        event: BatchAIFeedbackRequestedV1,
        correlation_id: UUID
    ) -> None:
        """
        Process batch AI feedback request.
        This is the main entry point from Kafka consumer.
        """
        processing_start = datetime.now(UTC)
        logger.info(
            f"Processing AI feedback batch {event.batch_id} with {len(event.essay_refs)} essays",
            extra={"batch_id": event.batch_id, "correlation_id": str(correlation_id)}
        )
        
        # Process all essays concurrently with semaphore control
        tasks = [
            self._process_single_essay_with_semaphore(essay_id, event.batch_id, correlation_id)
            for essay_id in event.essay_refs
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Separate successful results from failures
        valid_results = []
        failed_count = 0
        
        for essay_id, result in zip(event.essay_refs, results):
            if isinstance(result, AIFeedbackResultDataV1):
                valid_results.append(result)
            else:
                failed_count += 1
                logger.error(
                    f"Failed processing essay {essay_id}: {result}",
                    extra={"essay_id": essay_id, "error": str(result)}
                )
                # Create failure result
                valid_results.append(
                    self._create_failure_result(essay_id, str(result))
                )
        
        # Calculate metrics
        processing_duration = (datetime.now(UTC) - processing_start).total_seconds()
        
        # Publish completion event
        completion_event = BatchAIFeedbackCompletedV1(
            batch_id=event.batch_id,
            results=valid_results,
            processing_summary={
                "total": len(event.essay_refs),
                "succeeded": len(event.essay_refs) - failed_count,
                "failed": failed_count,
                "partial": 0  # Track partial successes if needed
            },
            batch_metrics={
                "total_duration_seconds": processing_duration,
                "avg_essay_duration_seconds": processing_duration / len(event.essay_refs) if event.essay_refs else 0
            }
        )
        
        await self.event_publisher.publish_batch_completion(
            completion_event, correlation_id
        )
        
        logger.info(
            f"Completed batch {event.batch_id}: {len(event.essay_refs) - failed_count}/{len(event.essay_refs)} succeeded",
            extra={
                "batch_id": event.batch_id,
                "duration_seconds": processing_duration,
                "success_rate": (len(event.essay_refs) - failed_count) / len(event.essay_refs) if event.essay_refs else 0
            }
        )
    
    async def _process_single_essay_with_semaphore(
        self,
        essay_id: str,
        batch_id: str,
        correlation_id: UUID
    ) -> AIFeedbackResultDataV1:
        """Process single essay with concurrency control."""
        async with self.semaphore:
            return await self._process_single_essay(essay_id, batch_id, correlation_id)
    
    async def _process_single_essay(
        self,
        essay_id: str,
        batch_id: str,
        correlation_id: UUID
    ) -> AIFeedbackResultDataV1:
        """
        Process single essay through simplified AI feedback pipeline.
        
        Pipeline steps:
        1. Fetch aggregated data from Result Aggregator
        2. Fetch spellchecked essay text from Content Service
        3. Build rich context from aggregated analyses
        4. Generate teacher feedback with context
        5. Generate edited version with context
        6. Store results and create event
        """
        essay_start = datetime.now(UTC)
        
        try:
            # 1. Fetch aggregated data (includes all upstream analyses)
            logger.debug(f"Fetching aggregated data for essay {essay_id}")
            aggregated_data = await self.result_aggregator.fetch_aggregated_data(
                essay_id, correlation_id
            )
            
            # 2. Fetch spellchecked essay text
            logger.debug(f"Fetching corrected essay content for {essay_id}")
            corrected_text = await self.content_client.fetch_content(
                aggregated_data.corrected_text_storage_id, correlation_id
            )
            
            # 3. Build rich context from all analyses
            logger.info(f"Building feedback context for essay {essay_id}")
            feedback_context = context_builder.build_feedback_context(
                nlp_metrics=aggregated_data.nlp_metrics,
                spelling_errors=aggregated_data.spelling_errors,
                cj_ranking=aggregated_data.cj_ranking,
                aes_score=aggregated_data.aes_score  # Future
            )
            
            # Log context richness
            logger.info(
                f"Context built for essay {essay_id}",
                extra={
                    "grammar_issues": feedback_context.grammar_count,
                    "spelling_errors": feedback_context.spelling_error_count,
                    "has_cj_ranking": bool(aggregated_data.cj_ranking),
                    "readability_score": feedback_context.readability_score
                }
            )
            
            # 4. Generate feedback with rich context
            student_name = aggregated_data.student_name or "the student"
            
            logger.info(f"Generating AI feedback for essay {essay_id}")
            feedback_text = await llm_workflows.generate_feedback(
                essay_text=corrected_text,
                student_name=student_name,
                prompt_text=aggregated_data.student_prompt_text,
                prompt_storage_id=aggregated_data.student_prompt_storage_id,
                course_code=aggregated_data.course_code,
                context=feedback_context,
                llm_client=self.llm_client,
                correlation_id=correlation_id,
                model_config=self._get_feedback_model_config()
            )
            
            # 5. Generate edited version if feedback was successful
            edited_essay = None
            if feedback_text:
                logger.info(f"Generating edited version for essay {essay_id}")
                edited_essay = await llm_workflows.generate_edited_version(
                    corrected_text=corrected_text,
                    feedback=feedback_text,
                    course_code=aggregated_data.course_code,
                    context=feedback_context,
                    llm_client=self.llm_client,
                    correlation_id=correlation_id,
                    model_config=self._get_editor_model_config()
                )
            
            # 6. Store results and create response
            result = await self._store_and_create_result(
                essay_id=essay_id,
                feedback_text=feedback_text,
                edited_essay=edited_essay,
                feedback_context=feedback_context,
                aggregated_data=aggregated_data,
                processing_time=(datetime.now(UTC) - essay_start).total_seconds(),
                correlation_id=correlation_id
            )
            
            logger.info(
                f"Successfully processed essay {essay_id}",
                extra={
                    "essay_id": essay_id,
                    "duration_seconds": (datetime.now(UTC) - essay_start).total_seconds(),
                    "generated_feedback": bool(feedback_text),
                    "generated_edit": bool(edited_essay),
                    "used_cj_context": bool(aggregated_data.cj_ranking)
                }
            )
            
            return result
            
        except Exception as e:
            logger.error(
                f"Error processing essay {essay_id}: {e}",
                extra={"essay_id": essay_id},
                exc_info=True
            )
            return self._create_failure_result(essay_id, str(e))
    
    # REMOVED METHODS:
    # - _analyze_grammar_full() - Grammar analysis done by NLP Service
    # - _apply_basic_corrections() - Spellchecking done by Spellchecker Service
    
    async def _store_and_create_result(
        self,
        essay_id: str,
        feedback_text: Optional[str],
        edited_essay: Optional[str],
        feedback_context: domain_models.FeedbackContext,
        aggregated_data: domain_models.AggregatedEssayData,
        processing_time: float,
        correlation_id: UUID
    ) -> AIFeedbackResultDataV1:
        """Store artifacts and create result event."""
        
        storage_refs = {}
        
        # Store feedback text if generated
        if feedback_text:
            storage_refs["feedback_text"] = await self.content_client.store_content(
                content=feedback_text,
                content_type="text/plain",
                correlation_id=correlation_id
            )
        
        # Store edited essay if generated
        if edited_essay:
            storage_refs["edited_essay"] = await self.content_client.store_content(
                content=edited_essay,
                content_type="text/plain",
                correlation_id=correlation_id
            )
        
        # Store context summary for transparency
        context_summary = self._format_context_summary(feedback_context)
        storage_refs["context_summary"] = await self.content_client.store_content(
            content=context_summary,
            content_type="text/plain",
            correlation_id=correlation_id
        )
        
        # Create metadata
        feedback_metadata = AIFeedbackMetadata(
            model_version=self.settings.MODEL_VERSION,
            feedback_type="comprehensive",
            processing_time_seconds=processing_time
        )
        
        # Create result event
        return AIFeedbackResultDataV1(
            entity_ref={"essay_id": essay_id},
            status=EssayStatus.AI_FEEDBACK_COMPLETED_SUCCESS,
            storage_references=StorageReferenceMetadata(references=storage_refs),
            feedback_metadata=feedback_metadata,
            generated_components={
                "feedback": bool(feedback_text),
                "edited_essay": bool(edited_essay),
                "context_summary": True
            },
            processing_metrics={
                "total_processing_ms": processing_time * 1000,
                "grammar_issues_from_nlp": feedback_context.grammar_count,
                "spelling_errors_from_spellchecker": feedback_context.spelling_error_count,
                "used_cj_ranking": bool(aggregated_data.cj_ranking)
            }
        )
    
    def _create_failure_result(
        self,
        essay_id: str,
        error_message: str
    ) -> AIFeedbackResultDataV1:
        """Create a failure result for an essay."""
        return AIFeedbackResultDataV1(
            entity_ref={"essay_id": essay_id},
            status=EssayStatus.AI_FEEDBACK_FAILED,
            storage_references=StorageReferenceMetadata(references={}),
            feedback_metadata=AIFeedbackMetadata(
                model_version=self.settings.MODEL_VERSION,
                feedback_type="failed"
            ),
            generated_components={
                "feedback": False,
                "edited_essay": False,
                "grammar_analysis": False
            },
            additional_metrics={"error": error_message}
        )
    
    def _get_feedback_model_config(self) -> dict:
        """Get model configuration for feedback generation."""
        return {
            "provider": self.settings.FEEDBACK_MODEL_PROVIDER,
            "model": self.settings.FEEDBACK_MODEL_NAME,
            "temperature": self.settings.FEEDBACK_TEMPERATURE,
            "max_tokens": self.settings.FEEDBACK_MAX_TOKENS
        }
    
    def _format_context_summary(self, context: domain_models.FeedbackContext) -> str:
        """Format context summary for storage."""
        summary_lines = [
            "AI Feedback Context Summary",
            "=" * 40,
            f"Grammar Issues: {context.grammar_count}",
            f"Grammar Summary: {context.grammar_summary}",
            f"Spelling Errors: {context.spelling_error_count}",
            f"Spelling Patterns: {context.spelling_patterns}",
            f"Readability Score: {context.readability_score:.1f}",
            f"Complexity Level: {context.complexity_level}",
        ]
        
        if context.comparative_position:
            summary_lines.append(f"Class Standing: {context.comparative_position}")
        if context.peer_comparison:
            summary_lines.append(f"Peer Comparison: {context.peer_comparison}")
        if context.assessment_insights:
            summary_lines.append(f"Assessment Insights: {context.assessment_insights}")
        
        return "\n".join(summary_lines)
    
    def _get_editor_model_config(self) -> dict:
        """Get model configuration for essay editing."""
        return {
            "provider": self.settings.EDITOR_MODEL_PROVIDER,
            "model": self.settings.EDITOR_MODEL_NAME,
            "temperature": 0.3,
            "max_tokens": 2500
        }
```

#### 3.3 Configuration (`config.py`)

```python
"""Configuration for AI Feedback Service."""

from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """Service configuration following Rule 043-service-configuration-and-logging."""
    
    model_config = SettingsConfigDict(env_prefix="AI_FEEDBACK_")
    
    # Service identity
    SERVICE_NAME: str = "ai-feedback-service"
    SERVICE_VERSION: str = "0.1.0"
    MODEL_VERSION: str = "ai-feedback-v1"
    
    # Kafka configuration
    KAFKA_BOOTSTRAP_SERVERS: str
    KAFKA_CONSUMER_GROUP: str = "ai-feedback-consumer-group"
    KAFKA_INPUT_TOPIC: str = "batch.ai.feedback.requested"
    KAFKA_OUTPUT_TOPIC: str = "batch.ai.feedback.completed"
    
    # External service URLs
    RESULT_AGGREGATOR_URL: str
    CLASS_MANAGEMENT_URL: str
    CONTENT_SERVICE_URL: str
    LLM_PROVIDER_SERVICE_URL: str
    
    # Processing configuration
    MAX_CONCURRENT_ESSAYS: int = 10
    CHUNK_SIZE: int = 500
    TOKEN_WINDOW: int = 75
    MAX_GRAMMAR_ISSUES: int = 10
    VALIDATE_GRAMMAR_ISSUES: bool = True
    
    # Model configuration - Feedback
    FEEDBACK_MODEL_PROVIDER: str = "anthropic"
    FEEDBACK_MODEL_NAME: str = "claude-3-sonnet-20240229"
    FEEDBACK_TEMPERATURE: float = 0.3
    FEEDBACK_MAX_TOKENS: int = 2000
    
    # Grammar analysis done by NLP Service - no configuration needed
    
    # Model configuration - Editor
    EDITOR_MODEL_PROVIDER: str = "openai"
    EDITOR_MODEL_NAME: str = "gpt-4o"
    
    # Observability
    LOG_LEVEL: str = "INFO"
    METRICS_PORT: int = 8000
    
    # Redis (for idempotency)
    REDIS_URL: str
    
    # Retry configuration
    MAX_RETRIES: int = 3
    RETRY_DELAY_SECONDS: float = 1.0

settings = Settings()
```

### Phase 4: Testing Strategy

#### 4.1 Unit Tests

Test each core logic module in isolation:

1. **test_prompt_manager.py**: Verify correct prompt selection for each course code
2. **test_text_utils.py**: Test chunking, preprocessing, and context formatting
3. **test_llm_workflows.py**: Mock LLM client and verify workflow logic
4. **test_result_curation.py**: Test deduplication and filtering algorithms

#### 4.2 Integration Tests

Test service interactions:

1. **test_ai_feedback_workflow.py**: End-to-end workflow with mocked external services
2. **test_event_processing.py**: Kafka message handling and batch processing
3. **test_resilience.py**: Failure handling and partial success scenarios

### Phase 5: Deployment and Operations

#### 5.1 Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY pyproject.toml ./
RUN pip install -e .

# Copy application code
COPY . .

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/healthz')"

# Run the service
CMD ["python", "worker_main.py"]
```

#### 5.2 Docker Compose Integration

```yaml
ai_feedback_service:
  build: ./services/ai_feedback_service
  environment:
    - AI_FEEDBACK_KAFKA_BOOTSTRAP_SERVERS=kafka:9092
    - AI_FEEDBACK_RESULT_AGGREGATOR_URL=http://result_aggregator:8000
    - AI_FEEDBACK_CONTENT_SERVICE_URL=http://content_service:8000
    - AI_FEEDBACK_LLM_PROVIDER_SERVICE_URL=http://llm_provider:8000
    - AI_FEEDBACK_CLASS_MANAGEMENT_URL=http://class_management:8000
    - AI_FEEDBACK_REDIS_URL=redis://redis:6379
  depends_on:
    - kafka
    - redis
    - result_aggregator
    - content_service
    - llm_provider
    - class_management
  networks:
    - huleedu_network
```

## Success Criteria

1. **Functional Requirements**:
   - ✅ Consumes BatchAIFeedbackRequestedV1 events from Kafka with owner_user_id
   - ✅ Fetches aggregated data from Result Aggregator Service (with all upstream analyses)
   - ✅ Resolves teacher names via Identity Service HTTP client using owner_user_id
   - ✅ Resolves student names via CMS internal endpoints using batch_id/essay_id
   - ✅ Builds rich context from NLP grammar, spellcheck errors, CJ rankings
   - ✅ Generates context-aware teacher feedback and edited essays with resolved names
   - ✅ Stores results in Content Service with proper references
   - ✅ Publishes BatchAIFeedbackCompletedV1 events to ELS
   - ✅ NO PII (names) transmitted in Kafka events (DDD compliance)

2. **Non-Functional Requirements**:
   - ✅ Processes essays concurrently with configurable limits
   - ✅ Implements idempotency for message processing
   - ✅ Provides comprehensive observability (logs, metrics, traces)
   - ✅ Handles failures gracefully with partial batch success
   - ✅ Implements circuit breakers for HTTP name resolution with 3 failure threshold
   - ✅ Graceful degradation when name services unavailable (default names)
   - ✅ HTTP client timeouts: 5s for single requests, 10s for batch operations
   - ✅ Follows all HuleEdu architectural patterns and standards
   - ✅ Maintains single responsibility: prompt curation and orchestration

3. **Code Quality**:
   - ✅ Clean separation of concerns (no duplicate analysis logic)
   - ✅ Protocol-based dependency injection with Dishka
   - ✅ Comprehensive error handling with structured errors
   - ✅ Context builder for intelligent prompt curation
   - ✅ All prompt templates preserved from prototype
   - ✅ Type hints and documentation throughout
   - ✅ DDD Name Propagation Refactor compliance (HTTP name resolution)
   - ✅ Circuit breaker patterns for HTTP client resilience

## Implementation Order

1. **Phase 1**: Event contracts and service scaffolding
2. **Phase 2**: Core logic implementation (prompts, context builder, workflows)
3. **Phase 3**: Event processor and service integration
4. **Phase 4**: Testing and deployment preparation

## Key Architectural Insights

### What This Service IS

- **Data Collector**: Gathers all upstream analyses via Result Aggregator
- **Context Builder**: Creates rich context from multiple analysis sources
- **Prompt Curator**: Selects and customizes prompts based on course and context
- **LLM Orchestrator**: Manages feedback and editing generation via LLM Provider

### What This Service IS NOT

- **NOT a Grammar Analyzer**: NLP Service owns grammar analysis
- **NOT a Spellchecker**: Spellchecker Service owns spelling correction
- **NOT a Text Processor**: Upstream services handle text preprocessing
- **NOT an LLM Manager**: LLM Provider Service manages API interactions

### Dependencies and Data Flow

```
1. Spellchecker Service → Completes spelling correction
2. NLP Service → Completes grammar and linguistic analysis
3. CJ Assessment → Completes comparative ranking (optional)
4. Result Aggregator → Aggregates all results
5. AI Feedback Service → Consumes aggregated data
   - Builds context from all analyses
   - Curates prompts with rich context
   - Generates comprehensive feedback
   - Generates edited essay
6. ELS → Receives AI feedback results
```

### Key Design Benefits

- **Single Responsibility**: Only responsible for prompt curation and orchestration
- **No Duplication**: Leverages existing analyses from upstream services
- **Rich Context**: Can provide comprehensive feedback using all available data
- **Future-Proof**: Easy to add Assessment Service data without changes
- **Clean Testing**: Mock aggregated data, test prompt curation logic

## Notes

- The service is designed to be stateless and horizontally scalable
- All prompt templates are preserved from the prototype (lines 100-571, 2704-2735)
- Context builder is the intelligence layer for prompt curation
- Result Aggregator Service acts as the data facade, simplifying orchestration
- The architecture supports easy addition of new analysis types (e.g., AES scores) without code changes
