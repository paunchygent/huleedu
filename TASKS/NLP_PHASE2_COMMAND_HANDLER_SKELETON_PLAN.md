# 🧠 ULTRATHINK: NLP Phase 2 Command Handler Implementation Plan (CORRECTED)

## 📊 IMPLEMENTATION STATUS (Updated: 2025-01-13)

### ✅ COMPLETED
- BatchNlpAnalysisHandler implementation (skeleton with proper error handling)
- LanguageToolServiceClient skeleton with mock responses
- Event models and topic mappings in common_core
- DI wiring and provider configurations
- Event publisher methods for NLP completed events
- NLP Service dependencies updated in pyproject.toml (spacy, wordfreq, lexical-diversity, etc.)
- Language Tool Service requirements fully documented
- NlpMetrics model expanded with all required linguistic metrics
- SpacyNlpAnalyzer full production implementation with:
  - Lexical sophistication (Zipf frequency via wordfreq)
  - Lexical diversity (MTLD/HDD via lexical-diversity)
  - Syntactic complexity (dependency distance via TextDescriptives)
  - Cohesion metrics (sentence similarity via TextDescriptives)
  - Phraseology (PMI/NPMI via gensim)
  - Automatic language detection (langdetect)
  - Fallback skeleton mode for resilience

### 🚧 IN PROGRESS
- Nothing currently in progress

### ⏳ PENDING
- Unit tests for all NLP components
- Integration tests for end-to-end flow
- Language Tool Service creation (separate microservice)
- Docker configuration updates (add spaCy model downloads)
- Performance optimization for <500ms requirement

## ⚠️ CRITICAL VALIDATION UPDATE

**Original plan contained multiple hallucinations. This is the corrected and ALIGNED version based on actual codebase analysis.**

## 🚨 CRITICAL SUCCESS FACTORS (MANDATORY COMPLIANCE)

The implementation MUST adhere to these non-negotiable requirements:

### 1. ✅ Outbox Pattern Compliance
- **MUST** use outbox pattern exclusively for ALL event publishing
- **FORBIDDEN**: Direct Kafka publishing from business logic
- **FORBIDDEN**: Passing `kafka_bus` to handlers or publishers
- **Pattern**: Publisher → OutboxManager → Database → Relay Worker → Kafka

### 2. ✅ Structured Error Handling
- **MUST** use `huleedu_service_libs.error_handling` factories
- **FORBIDDEN**: Generic `Exception` handling without structured errors
- **Required imports**:
  ```python
  from huleedu_service_libs.error_handling import (
      HuleEduError,
      raise_external_service_error,
      raise_processing_error,
      raise_validation_error,
  )
  ```

### 3. ✅ Protocol-Based DI Patterns
- **MUST** define all dependencies as Protocols
- **MUST** use Dishka DI framework with proper scoping
- **FORBIDDEN**: Direct concrete class dependencies in business logic

### 4. ✅ Event Topic Mapping
- **MUST** add `ESSAY_NLP_COMPLETED` to `_TOPIC_MAPPING` in event_enums.py
- **Critical**: Without this, events cannot be published

## Executive Summary

This document outlines the implementation plan for NLP Phase 2 text analysis capabilities. **CRITICAL DISCOVERY**: Phase 2 infrastructure already exists - the task is to modify existing `StudentMatchingHandler` to perform text analysis instead of student matching.

## Architectural Reality Check ✅

**Current Handler Architecture:**
- ✅ **Phase 1**: `EssayStudentMatchingHandler` handles `BATCH_STUDENT_MATCHING_REQUESTED` (working correctly)
- ⚠️ **Phase 2**: `StudentMatchingHandler` handles `BATCH_NLP_INITIATE_COMMAND` (misnamed & wrong logic)

**What Already Exists:**
- ✅ Phase 1 student matching infrastructure (complete and working)
- ✅ Phase 2 event handling infrastructure (routing works)
- ✅ `BatchServiceNLPInitiateCommandDataV1` input event model (complete)
- ✅ DI container with dual handler mapping
- ✅ Kafka consumer subscribed to both Phase 1 and Phase 2 topics

**What Needs Correction:**
- 🔄 **RENAME** `StudentMatchingHandler` → `BatchNlpAnalysisHandler`
- 🔄 **REPLACE** student matching logic with NLP analysis logic
- ❌ Output event topic mapping for `ESSAY_NLP_COMPLETED`
- ❌ Output data models for NLP results  
- ❌ spaCy integration
- ❌ Language Tool Service integration

**Integration Flow:**
```
Phase 1: Batch Orchestrator → EssayStudentMatchingHandler → Class Management (unchanged ✅)
Phase 2: Batch Orchestrator → BatchNlpAnalysisHandler → Language Tool Service (grammar)
                                                      → Result Aggregator (new events)
```

**Key Constraints:**
- ✅ **RENAME handler and replace business logic**
- ✅ **PRESERVE Phase 1 student matching (no changes)**
- ✅ Use existing `BatchServiceNLPInitiateCommandDataV1` event model
- ✅ Work within existing dual-handler DI structure
- ❌ No complex linguistic analysis (CEFR assessment later)
- ❌ No overengineered preprocessing pipelines

## Implementation Plan

### Phase 1: Output Event Architecture (Week 1)

**1.1 Add Topic Mapping for Output Events**
```python
# libs/common_core/src/common_core/event_enums.py
# CRITICAL: ADD to _TOPIC_MAPPING dictionary (currently missing):
_TOPIC_MAPPING = {
    # ... existing mappings ...
    ProcessingEvent.ESSAY_NLP_COMPLETED: "huleedu.essay.nlp.completed.v1",  # ADD THIS LINE
    # ... rest of mappings ...
}
```

**1.2 Create Output Data Models (New Models Needed)**
```python
# libs/common_core/src/common_core/nlp_events.py - NEW FILE

class EssayNlpCompletedV1(BaseEventData):
    """NLP analysis completion event for single essay."""
    essay_id: UUID
    text_storage_id: str
    nlp_metrics: NlpMetrics
    grammar_analysis: GrammarAnalysis
    processing_metadata: dict

class NlpMetrics(BaseModel):
    """Basic spaCy-derived metrics - SKELETON."""
    word_count: int
    sentence_count: int
    avg_sentence_length: float
    language_detected: str
    # TODO: Add more metrics as needed

class GrammarAnalysis(BaseModel):
    """Grammar analysis from Language Tool Service."""
    error_count: int
    errors: list[dict]  # TODO: Define error structure
    suggestions: list[dict]  # TODO: Define suggestion structure

# NOTE: INPUT already exists:
# - BatchServiceNLPInitiateCommandDataV1 ✅
# - BATCH_NLP_INITIATE_COMMAND topic mapping ✅
```

**1.3 Protocol Extensions**
```python
# services/nlp_service/protocols.py - ADDITIONS

class NlpAnalyzerProtocol(Protocol):
    """Protocol for spaCy-based text analysis."""
    
    async def analyze_text(
        self,
        text: str,
        language: str = "auto",  # "en" or "sv" 
    ) -> NlpMetrics:
        """Extract basic text metrics using spaCy."""
        ...

class LanguageToolClientProtocol(Protocol):
    """Protocol for Language Tool Service integration."""
    
    async def check_grammar(
        self,
        text: str,
        language: str = "auto",
        http_session: aiohttp.ClientSession,
        correlation_id: UUID,
    ) -> GrammarAnalysis:
        """Get grammar analysis from Language Tool Service."""
        ...

# NOTE: NlpEventPublisherProtocol already exists for Phase 1 ✅
# Will extend existing publisher for new ESSAY_NLP_COMPLETED events
```

### Phase 2: Rename Handler & Replace Logic (Week 2)

**2.1 Rename Handler and Replace Business Logic**
```python
# services/nlp_service/command_handlers/batch_nlp_analysis_handler.py  
# RENAME from student_matching_handler.py and replace logic

# Import structured error handling
from huleedu_service_libs.error_handling import (
    HuleEduError,
    raise_external_service_error,
    raise_processing_error,
    raise_validation_error,
)

class BatchNlpAnalysisHandler(CommandHandlerProtocol):
    """Handler for Phase 2 NLP analysis - RENAMED from StudentMatchingHandler."""

    def __init__(
        self,
        # KEEP some existing dependencies:
        content_client: ContentClientProtocol,
        event_publisher: NlpEventPublisherProtocol, 
        outbox_repository: OutboxRepositoryProtocol,
        # REMOVED: kafka_bus - NEVER pass directly to handler (outbox pattern)
        tracer: "Tracer | None" = None,
        # ADD new Phase 2 dependencies:
        nlp_analyzer: NlpAnalyzerProtocol,
        language_tool_client: LanguageToolClientProtocol,
    ) -> None:
        """Initialize - CLEAN UP for NLP analysis purpose."""
        # Keep relevant assignments
        self.content_client = content_client
        self.event_publisher = event_publisher
        self.outbox_repository = outbox_repository
        # NO kafka_bus assignment - publisher uses outbox internally
        self.tracer = tracer
        # ADD new assignments
        self.nlp_analyzer = nlp_analyzer
        self.language_tool_client = language_tool_client

    async def can_handle(self, event_type: str) -> bool:
        """UNCHANGED - handles BATCH_NLP_INITIATE_COMMAND events."""
        return event_type == topic_name(ProcessingEvent.BATCH_NLP_INITIATE_COMMAND)

    async def handle(
        self,
        msg: ConsumerRecord,
        envelope: EventEnvelope, 
        http_session: aiohttp.ClientSession,
        correlation_id: UUID,
        span: "Span | None" = None,
    ) -> bool:
        """Process NLP analysis batch - COMPLETELY NEW LOGIC (not student matching)."""
        
        try:
            # Parse command (SAME pattern)
            command_data = BatchServiceNLPInitiateCommandDataV1.model_validate(envelope.data)
            
            logger.info(
                f"Processing Phase 2 NLP analysis for batch {command_data.batch_id} "
                f"with {len(command_data.essays_to_process)} essays",
                extra={
                    "batch_id": command_data.batch_id,
                    "essay_count": len(command_data.essays_to_process),
                    "correlation_id": str(correlation_id),
                },
            )
            
            # NEW: NLP analysis logic (not student matching)
            for essay_ref in command_data.essays_to_process:
                try:
                    # Fetch content (SAME pattern as existing)
                    essay_text = await self.content_client.fetch_content(
                        storage_id=essay_ref.text_storage_id,
                        http_session=http_session,
                        correlation_id=correlation_id,
                    )
                    
                    # REPLACE: Instead of student matching, do text analysis
                    nlp_metrics = await self.nlp_analyzer.analyze_text(
                        text=essay_text,
                        language=command_data.language,  # Use provided language
                    )
                    
                    grammar_analysis = await self.language_tool_client.check_grammar(
                        text=essay_text,
                        language=command_data.language,
                        http_session=http_session,
                        correlation_id=correlation_id,
                    )
                    
                    # PUBLISH per-essay results using OUTBOX pattern
                    await self.event_publisher.publish_essay_nlp_completed(
                        # NO kafka_bus parameter - publisher uses outbox internally
                        essay_id=essay_ref.essay_id,
                        text_storage_id=essay_ref.text_storage_id,
                        nlp_metrics=nlp_metrics,
                        grammar_analysis=grammar_analysis,
                        correlation_id=correlation_id,
                    )
                    
                    logger.info(
                        "Successfully processed Phase 2 NLP analysis for essay %s",
                        essay_ref.essay_id,
                        extra={
                            "essay_id": essay_ref.essay_id,
                            "batch_id": command_data.batch_id,
                            "correlation_id": str(correlation_id),
                        },
                    )
                    
                except HuleEduError:
                    # Already structured error - re-raise
                    raise
                except aiohttp.ClientError as e:
                    # External service error - use structured error
                    raise_external_service_error(
                        service="nlp_service",
                        operation="process_essay_nlp",
                        external_service="content_service_or_language_tool",
                        message=f"Failed to process essay {essay_ref.essay_id}: {str(e)}",
                        correlation_id=correlation_id,
                        essay_id=essay_ref.essay_id,
                        batch_id=command_data.batch_id,
                    )
                except Exception as essay_error:
                    # Processing error - use structured error
                    raise_processing_error(
                        service="nlp_service",
                        operation="analyze_essay",
                        stage="nlp_analysis",
                        message=f"Failed to analyze essay {essay_ref.essay_id}: {str(essay_error)}",
                        correlation_id=correlation_id,
                        essay_id=essay_ref.essay_id,
                        batch_id=command_data.batch_id,
                    )
                    
                    # Add failed result for this essay (same pattern as Phase 1)
                    failed_result = EssayNlpAnalysisResult(
                        essay_id=essay_ref.essay_id,
                        text_storage_id=essay_ref.text_storage_id,
                        nlp_metrics=NlpMetrics(
                            word_count=0,
                            sentence_count=0,
                            avg_sentence_length=0.0,
                        ),
                        grammar_analysis=GrammarAnalysis(
                            error_count=0,
                            errors=[],
                            suggestions=[],
                        ),
                        processing_metadata={
                            "error": str(essay_error),
                            "status": "FAILED",
                        },
                    )
                    analysis_results.append(failed_result)
                    # Continue processing other essays instead of failing the entire batch
                    continue
            
            # Publish results (same pattern as Phase 1)
            if analysis_results:
                processing_summary = {
                    "total_essays": len(command_data.essays_to_process),
                    "processed": processed_count,
                    "failed": len(command_data.essays_to_process) - processed_count,
                }
                
                await self.event_publisher.publish_batch_nlp_analysis_results(
                    # NO kafka_bus parameter - publisher uses outbox internally
                    batch_id=command_data.batch_id,
                    analysis_results=analysis_results,
                    processing_summary=processing_summary,
                    correlation_id=correlation_id,
                )
                
                logger.info(
                    "Published batch NLP analysis results for batch %s to Result Aggregator",
                    command_data.batch_id,
                    extra={
                        "batch_id": command_data.batch_id,
                        "total_results": len(analysis_results),
                        "processing_summary": processing_summary,
                        "correlation_id": str(correlation_id),
                    },
                )
            
            logger.info(
                f"Completed Phase 2 NLP analysis for batch {command_data.batch_id}: "
                f"{processed_count}/{len(command_data.essays_to_process)} essays processed",
                extra={
                    "batch_id": command_data.batch_id,
                    "processed_count": processed_count,
                    "total_count": len(command_data.essays_to_process),
                    "correlation_id": str(correlation_id),
                },
            )
            
            return processed_count > 0  # Return True if at least one essay was processed
            
        except ValidationError as e:
            # Validation error - use structured error
            raise_validation_error(
                service="nlp_service",
                operation="parse_nlp_command",
                field="envelope.data",
                message=f"Invalid NLP command format: {e.errors()}",
                correlation_id=correlation_id,
            )
        except HuleEduError:
            # Already structured error - re-raise
            raise
        except Exception as e:
            # Unexpected error - use structured error
            raise_processing_error(
                service="nlp_service",
                operation="handle_nlp_command",
                stage="command_processing",
                message=f"Unexpected error processing NLP batch: {str(e)}",
                correlation_id=correlation_id,
            )
```

### Phase 3: Service Integrations (Week 3)

**3.1 spaCy Analyzer Implementation (Skeleton)**
```python
# services/nlp_service/implementations/nlp_analyzer_impl.py

class SpacyNlpAnalyzer:
    """Basic spaCy-based text analysis - SKELETON."""
    
    def __init__(self):
        """Initialize spaCy models - SKELETON setup."""
        # TODO: Load models lazily
        self.nlp_en = None  # Will load spacy.load("en_core_web_sm")  
        self.nlp_sv = None  # Will load spacy.load("sv_core_news_sm")
        self._models_loaded = False
        
    async def _ensure_models_loaded(self):
        """Lazy load spaCy models."""
        if not self._models_loaded:
            # TODO: Implement model loading
            # self.nlp_en = spacy.load("en_core_web_sm")
            # self.nlp_sv = spacy.load("sv_core_news_sm")
            self._models_loaded = True
        
    async def analyze_text(self, text: str, language: str = "auto") -> NlpMetrics:
        """SKELETON: Basic spaCy analysis."""
        
        await self._ensure_models_loaded()
        
        # TODO: Language detection if auto
        # TODO: Select appropriate spaCy model
        # TODO: Process text with spaCy
        # TODO: Extract basic metrics
        
        # SKELETON return basic metrics
        words = text.split()
        sentences = text.split('.')
        
        return NlpMetrics(
            word_count=len(words),
            sentence_count=len(sentences),
            avg_sentence_length=len(words) / max(len(sentences), 1),
        )
```

**3.2 Language Tool Service Client (Skeleton)**
```python
# services/nlp_service/implementations/language_tool_client_impl.py

class LanguageToolServiceClient:
    """Client for Language Tool Service integration - SKELETON."""
    
    def __init__(self, language_tool_service_url: str):
        """Initialize client with service URL."""
        self.service_url = language_tool_service_url.rstrip('/')
        
    async def check_grammar(
        self,
        text: str,
        language: str = "auto",
        http_session: aiohttp.ClientSession,
        correlation_id: UUID,
    ) -> GrammarAnalysis:
        """SKELETON: Call Language Tool Service."""
        
        # TODO: Implement HTTP POST to Language Tool Service
        # When implementing, use structured error handling:
        # try:
        #     async with http_session.post(...) as response:
        #         ...
        # except aiohttp.ClientError as e:
        #     raise_external_service_error(
        #         service="nlp_service",
        #         operation="check_grammar",
        #         external_service="language_tool_service",
        #         message=str(e),
        #         correlation_id=correlation_id,
        #     )
        
        # SKELETON return empty analysis
        return GrammarAnalysis(
            error_count=0,
            errors=[],
            suggestions=[],
        )
```

**3.3 Event Publisher Implementation**
```python
# services/nlp_service/implementations/event_publisher_impl.py - ADDITIONS

class DefaultNlpEventPublisher(NlpEventPublisherProtocol):
    """Publisher that ALWAYS uses outbox for transactional safety."""
    
    def __init__(self, outbox_manager: OutboxManager, source_service_name: str):
        """Initialize with outbox manager ONLY - no direct Kafka."""
        self.outbox_manager = outbox_manager
        self.source_service_name = source_service_name
        # NO kafka_bus attribute - outbox pattern only!
    
    async def publish_essay_nlp_completed(
        self,
        # NO kafka_bus parameter - outbox only
        essay_id: str,
        text_storage_id: str,
        nlp_metrics: NlpMetrics,
        grammar_analysis: GrammarAnalysis,
        correlation_id: UUID,
    ) -> None:
        """Publish essay NLP completion - ALWAYS via outbox."""
        
        # Create event data
        event_data = EssayNlpCompletedV1(
            essay_id=essay_id,
            text_storage_id=text_storage_id,
            nlp_metrics=nlp_metrics,
            grammar_analysis=grammar_analysis,
            processing_metadata={"timestamp": datetime.utcnow().isoformat()},
        )
        
        # Create envelope
        envelope = EventEnvelope(
            event_type=topic_name(ProcessingEvent.ESSAY_NLP_COMPLETED),
            source_service=self.source_service_name,
            correlation_id=correlation_id,
            schema_version="1.0.0",
            data=event_data,
        )
        
        # ALWAYS use outbox for transactional safety
        await self.outbox_manager.publish_to_outbox(
            aggregate_type="essay",
            aggregate_id=str(essay_id),
            event_type=topic_name(ProcessingEvent.ESSAY_NLP_COMPLETED),
            event_data=envelope,  # Pass original Pydantic envelope
            topic=topic_name(ProcessingEvent.ESSAY_NLP_COMPLETED),
        )
```

### Phase 4: Update Existing DI Wiring (Week 4)

**4.1 Update DI Providers for Renamed Handler**
```python
# services/nlp_service/di.py - UPDATE EXISTING PROVIDERS

# UPDATE existing provider to match renamed handler
@provide(scope=Scope.APP)
def provide_batch_nlp_handler(
    self,
    # KEEP relevant dependencies:
    content_client: ContentClientProtocol,
    event_publisher: NlpEventPublisherProtocol,
    outbox_repository: OutboxRepositoryProtocol,
    # NO kafka_bus - handler doesn't need it (outbox pattern)
    tracer: Tracer,
    # ADD new Phase 2 dependencies:
    nlp_analyzer: NlpAnalyzerProtocol,
    language_tool_client: LanguageToolClientProtocol,
) -> BatchNlpAnalysisHandler:
    """UPDATE provider for renamed handler with clean dependencies."""
    return BatchNlpAnalysisHandler(
        # Relevant args only
        content_client=content_client,
        event_publisher=event_publisher,
        outbox_repository=outbox_repository,
        # NO kafka_bus parameter - removed per outbox pattern
        tracer=tracer,
        # NEW args
        nlp_analyzer=nlp_analyzer,
        language_tool_client=language_tool_client,
    )

# ADD new providers for new dependencies
@provide(scope=Scope.APP)
def provide_nlp_analyzer(self) -> NlpAnalyzerProtocol:
    """Provide spaCy-based NLP analyzer."""
    return SpacyNlpAnalyzer()

@provide(scope=Scope.APP)
def provide_language_tool_client(
    self, 
    settings: Settings
) -> LanguageToolClientProtocol:
    """Provide Language Tool Service client."""
    return LanguageToolServiceClient(settings.LANGUAGE_TOOL_SERVICE_URL)

# UPDATE command handlers mapping  
@provide(scope=Scope.APP)
def provide_command_handlers(
    self,
    essay_student_matching_handler: EssayStudentMatchingHandler,  # Phase 1 unchanged
    batch_nlp_handler: BatchNlpAnalysisHandler,  # Phase 2 renamed
) -> dict[str, CommandHandlerProtocol]:
    """Update command handlers mapping for renamed Phase 2 handler."""
    return {
        "phase1_student_matching": essay_student_matching_handler,  # unchanged
        "phase2_batch_nlp": batch_nlp_handler,  # updated type
    }
```

**4.2 Event Processor Integration**
```python
# services/nlp_service/event_processor.py - NO CHANGES NEEDED

# REALITY: process_single_message() receives handlers from DI container
# The function signature is:
# async def process_single_message(
#     msg: ConsumerRecord,
#     command_handlers: dict[str, CommandHandlerProtocol],  # ← Injected from DI
#     http_session: aiohttp.ClientSession,
#     tracer: "Tracer | None" = None,
# ) -> bool:

# NO MODIFICATIONS REQUIRED - existing code works because:
# 1. DI already provides command_handlers dictionary 
# 2. StudentMatchingHandler already handles BATCH_NLP_INITIATE_COMMAND
# 3. Handler routing logic already works via can_handle() method
```

**4.3 Configuration Updates**
```python
# services/nlp_service/config.py - ADDITIONS

class Settings(BaseSettings):
    # ... existing settings
    
    # Language Tool Service Configuration (proper env pattern)
    LANGUAGE_TOOL_SERVICE_URL: str = Field(
        default="http://language-tool-service:8080",
        env="NLP_SERVICE_LANGUAGE_TOOL_URL"
    )
    
    # spaCy Configuration  
    SPACY_MODEL_EN: str = Field(
        default="en_core_web_sm",
        env="NLP_SERVICE_SPACY_MODEL_EN"
    )
    SPACY_MODEL_SV: str = Field(
        default="sv_core_news_sm",
        env="NLP_SERVICE_SPACY_MODEL_SV"
    )
```

## File Structure

**New Files to Create:**
```
libs/common_core/src/common_core/
└── nlp_events.py                          # NEW - Output data models

services/nlp_service/
├── command_handlers/
│   └── batch_nlp_analysis_handler.py      # RENAMED from student_matching_handler.py
└── implementations/
    ├── nlp_analyzer_impl.py               # NEW - spaCy integration
    └── language_tool_client_impl.py       # NEW - Language Tool client
```

**Files to Modify:**
```
libs/common_core/src/common_core/event_enums.py           # ADD - topic mapping
services/nlp_service/protocols.py                         # EXTEND - new protocols
services/nlp_service/di.py                                # UPDATE - providers for renamed handler
services/nlp_service/config.py                           # EXTEND - new settings
services/nlp_service/implementations/event_publisher_impl.py  # EXTEND - new method
```

**Files That Remain Unchanged (Phase 1 + Infrastructure):**
```
services/nlp_service/command_handlers/essay_student_matching_handler.py  # ✅ Phase 1 unchanged
services/nlp_service/event_processor.py    # ✅ Already works
services/nlp_service/kafka_consumer.py     # ✅ Already subscribes to correct topics  
services/nlp_service/worker_main.py        # ✅ Already handles DI correctly
# ... all Phase 1 student matching infrastructure remains untouched
```

## Dependencies

**Add to pyproject.toml:**
```toml
dependencies = [
    # ... existing dependencies
    "spacy>=3.4.0",
    # Models to be installed separately:
    # python -m spacy download en_core_web_sm
    # python -m spacy download sv_core_news_sm
]
```

## Testing Strategy

**Unit Tests (Skeleton):**
```python
# tests/unit/test_batch_nlp_analysis_handler.py
async def test_handler_processes_batch_successfully():
    """Test command handler processes batch correctly."""
    
async def test_handler_handles_individual_essay_failures():
    """Test partial failure handling."""

# tests/unit/test_spacy_nlp_analyzer.py  
async def test_basic_text_metrics():
    """Test basic spaCy metrics extraction."""
    
# tests/unit/test_language_tool_client.py
async def test_grammar_analysis_integration():
    """Test Language Tool Service integration."""
```

**Integration Tests (Skeleton):**
```python
# tests/integration/test_phase2_nlp_flow.py
async def test_end_to_end_nlp_analysis():
    """Test complete Phase 2 NLP analysis flow."""
```

## Success Criteria

**Phase 1 Complete:** 
- ✅ Event contracts defined in common_core
- ✅ Protocol interfaces defined
- ✅ Command handler skeleton created

**Phase 2 Complete:**
- ✅ Handler processes batches (skeleton implementation)
- ✅ spaCy integration foundation ready
- ✅ Language Tool Service client skeleton
- ✅ Error handling mirrors Phase 1

**Phase 3 Complete:**
- ✅ DI container wiring complete
- ✅ Event processor routes Phase 2 events
- ✅ Basic unit tests pass
- ✅ Integration with existing infrastructure

**Phase 4 Complete:**
- ✅ Service processes Phase 2 events end-to-end
- ✅ Results published to Result Aggregator
- ✅ Metrics and logging functional
- ✅ Ready for spaCy/Language Tool implementation

## Key Architectural Corrections & Alignments ✅

**✅ ALIGNED: Outbox Pattern Compliance:**
- **REMOVED** all `kafka_bus` parameters from handlers and publishers
- **ENFORCED** OutboxManager-only pattern in event publisher
- **FOLLOWS** transactional safety principles from rule 042.1

**✅ ALIGNED: Structured Error Handling:**
- **REPLACED** generic exceptions with `huleedu_service_libs.error_handling` factories
- **ADDED** proper error categorization (validation, external service, processing)
- **INCLUDED** correlation_id tracking in all errors

**✅ ALIGNED: Protocol-Based DI:**
- **DEFINED** clear Protocol interfaces for all new dependencies
- **REMOVED** concrete class dependencies from business logic
- **FOLLOWS** Dishka DI patterns with proper scoping

**✅ ALIGNED: Event Architecture:**
- **EXPLICIT** topic mapping addition for `ESSAY_NLP_COMPLETED`
- **PROPER** EventEnvelope construction with schema_version
- **CORRECT** Pydantic model passing to outbox

**✅ CORRECTED: Handler Architecture:**
- **RENAME** `StudentMatchingHandler` → `BatchNlpAnalysisHandler` 
- **REPLACE** student matching logic with NLP analysis logic
- **PRESERVE** Phase 1 (`EssayStudentMatchingHandler`) completely unchanged
- **CLEAN UP** dependencies (remove unused Phase 1 deps, add Phase 2 deps)

**✅ CORRECTED: What Actually Needs Implementation:**
- Handler rename and business logic replacement (with proper error handling)
- Output event topic mapping for `ESSAY_NLP_COMPLETED` (explicit addition)
- Output data models for NLP results
- spaCy integration implementation (skeleton with proper patterns)
- Language Tool Service client implementation (with structured errors)

**🚨 CRITICAL: All Hallucinations Corrected & Aligned:**
- ✅ **NO** direct Kafka usage (outbox pattern only)
- ✅ **NO** generic error handling (structured errors only)
- ✅ **PRESERVE** Phase 1 student matching (completely unchanged)
- ✅ **FOLLOW** all HuleEdu architectural mandates

## Language Tool Service Implementation Requirements

### Service Architecture Decision
**Create as Separate Microservice** following HuleEdu's bounded context principles:
- **Location**: `services/language_tool_service/`
- **Technology**: Java-based Language Tool with Python FastAPI/Quart wrapper
- **Pattern**: Similar to LLM Provider Service architecture
- **Port**: 8085 (avoiding conflicts with existing services)

### Implementation Requirements

#### 1. Service Structure
```
services/language_tool_service/
├── Dockerfile          # Multi-stage: Java + Python wrapper
├── README.md
├── pyproject.toml      # Python dependencies for HTTP wrapper
├── config.py           # Service configuration with BaseSettings
├── app.py              # Quart/FastAPI HTTP wrapper
├── di.py               # Dishka DI container setup
├── protocols.py        # Protocol interfaces
├── api/
│   ├── __init__.py
│   ├── grammar_routes.py   # POST /v1/check endpoint
│   └── health_routes.py    # Health checks with DatabaseHealthChecker
├── implementations/
│   ├── __init__.py
│   ├── language_tool_wrapper.py  # Java process management
│   └── outbox_manager.py         # Outbox pattern if needed
├── metrics.py          # Prometheus metrics
└── tests/
```

#### 2. Required Patterns (MANDATORY)
- **Dishka DI Container**: All dependencies via protocols
- **Structured Error Handling**: Use `huleedu_service_libs.error_handling`
- **Observability**: Full stack integration (logging, tracing, metrics)
- **Health Endpoints**: `/healthz` with dependency checks
- **Metrics Endpoint**: `/metrics` for Prometheus
- **Configuration**: Environment-based via Pydantic BaseSettings

#### 3. API Contract
```python
# POST /v1/check
{
    "text": str,
    "language": str,  # "en", "sv", "auto"
    "correlation_id": UUID
}

# Response
{
    "errors": [
        {
            "rule_id": str,
            "message": str,
            "short_message": str,
            "offset": int,
            "length": int,
            "replacements": list[str],
            "category": str,  # "grammar", "spelling", "style"
            "severity": str   # "error", "warning", "info"
        }
    ],
    "error_count": int,
    "errors_per_100_words": float,
    "category_breakdown": dict[str, int],
    "language": str,
    "processing_time_ms": int
}
```

#### 4. Docker Configuration
```dockerfile
# Multi-stage Dockerfile
FROM openjdk:11-jre-slim as java-base
RUN apt-get update && apt-get install -y wget unzip
RUN wget https://languagetool.org/download/LanguageTool-stable.zip
RUN unzip LanguageTool-stable.zip

FROM python:3.11-slim
COPY --from=java-base /LanguageTool-* /opt/languagetool/
RUN apt-get update && apt-get install -y openjdk-11-jre-headless
# Python app setup with PDM...
```

#### 5. Integration with NLP Service
- HTTP client implementation in `LanguageToolServiceClient`
- Circuit breaker pattern for resilience
- Timeout handling (30s max)
- Fallback to empty grammar analysis on failure
- Structured error propagation

## Advanced NLP Metrics Implementation

### Required Linguistic Metrics (STRICT REQUIREMENTS)
1. **Lexical sophistication**: mean Zipf, % tokens Zipf<3 (wordfreq)
2. **Lexical diversity**: MTLD/HDD (lexical_diversity)
3. **Syntactic complexity**: mean dependency distance (TextDescriptives), phrasal/clausal indices
4. **Cohesion**: first/second-order sentence similarity (TextDescriptives)
5. **Grammar accuracy**: From Language Tool Service
6. **Phraseology**: avg PMI/npmi of essay bigrams/trigrams (gensim/textacy)

### Dependencies to Add
```toml
# services/nlp_service/pyproject.toml
dependencies = [
    # ... existing ...
    "spacy>=3.7.0",
    "wordfreq>=3.0.0",
    "lexical-diversity>=0.1.1",
    "textdescriptives>=2.8.0",
    "langdetect>=1.0.9",
    "gensim>=4.3.0",  # For phraseology metrics
]
```

## Next Steps After Implementation

1. **Phase 1**: Implement real spaCy analysis with specified metrics
2. **Phase 2**: Create Language Tool Service following HuleEdu patterns
3. **Phase 3**: Integration testing with full pipeline
4. **Phase 4**: Performance optimization for <500ms requirement
5. **Phase 5**: Comprehensive unit and integration tests

This plan ensures full compliance with HuleEdu architectural patterns while implementing the exact linguistic metrics required.