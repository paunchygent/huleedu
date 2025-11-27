---
type: epic
id: EPIC-003
title: AI Feedback Service
status: draft
phase: 3
sprint_target: TBD
created: 2025-11-27
last_updated: 2025-11-27
---

# EPIC-003: AI Feedback Service

## Summary

Implement the AI Feedback Service as a pure Kafka worker that generates comprehensive teacher feedback and edited essays using aggregated upstream analyses. The service consumes spellcheck results, NLP metrics, and CJ rankings to curate intelligent prompts for LLM-based feedback generation.

**Business Value**: Final pipeline stage that transforms all prior essay analyses into actionable teacher feedback and student-ready edited essays.

**Scope Boundaries**:
- **In Scope**: Feedback generation, edited essay generation, context building from upstream data
- **Out of Scope**: Grammar analysis (NLP Service), spelling correction (Spellchecker), LLM API management (LLM Provider)

## User Stories

### US-003.1: Batch Feedback Generation
**As a** batch orchestrator
**I want to** trigger AI feedback generation for completed batches
**So that** essays receive comprehensive feedback after all analyses complete.

**Acceptance Criteria**:
- [ ] Service consumes `BatchAIFeedbackRequestedV1` from Kafka
- [ ] Fetches aggregated analysis data from RAS
- [ ] Generates feedback for all essays in batch
- [ ] Publishes `BatchAIFeedbackCompletedV1` on completion

### US-003.2: Context-Aware Feedback
**As a** teacher receiving feedback
**I want** feedback to reflect all prior analysis (grammar, spelling, ranking)
**So that** feedback is comprehensive and consistent with other assessments.

**Acceptance Criteria**:
- [ ] Context builder summarizes NLP grammar analysis
- [ ] Context builder identifies spelling patterns
- [ ] Context includes CJ ranking position if available
- [ ] Prompts incorporate all context intelligently

### US-003.3: Edited Essay Generation
**As a** student receiving feedback
**I want** an edited version of my essay incorporating teacher feedback
**So that** I can see how to improve my writing.

**Acceptance Criteria**:
- [ ] Edited essay generated after feedback
- [ ] Grammar context informs editing decisions
- [ ] Both feedback and edited essay stored in Content Service

## Technical Architecture

### Service Pattern
- **Type**: Pure Kafka Worker (no HTTP APIs)
- **Template**: CJ Assessment Service architecture
- **DI**: Dishka with Protocol-based injection

### Data Flow
```
ELS → BatchAIFeedbackRequestedV1 → AI Feedback Service
AI Feedback → RAS (fetch aggregated data)
AI Feedback → Identity Service (resolve teacher name)
AI Feedback → CMS (resolve student names)
AI Feedback → LLM Provider (generate feedback/edits)
AI Feedback → Content Service (store results)
AI Feedback → BatchAIFeedbackCompletedV1 → ELS
```

### Core Modules
- `event_processor.py`: Batch orchestration
- `core_logic/context_builder.py`: Build FeedbackContext from analyses
- `core_logic/prompt_manager.py`: Course-specific prompt selection
- `core_logic/llm_workflows.py`: Feedback and editing generation

## Related ADRs
- ADR-0011: AI Feedback Data Aggregation Strategy
- ADR-0012: AI Feedback Pure Kafka Worker Pattern
- ADR-0013: AI Feedback Name Resolution Strategy
- ADR-0014: AI Feedback Context Builder Pattern

## Dependencies
- Result Aggregator Service operational with aggregated essay endpoint
- LLM Provider Service operational
- Content Service operational
- NLP Service and Spellchecker complete before AI Feedback triggered

## Notes
- Service does NOT perform grammar analysis (NLP Service responsibility)
- Service does NOT manage LLM APIs (LLM Provider responsibility)
- Prompt templates preserved from prototype implementation
- Context builder is the intelligence layer for prompt curation
