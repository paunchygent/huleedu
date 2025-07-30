🧠 ULTRATHINK: Creating Comprehensive NLP Service Student Matching Plan

  ---
  NLP Service - Student Matching Feature Plan

  STATUS: FORMAL PLANCREATED: 2025-01-30COMPLEMENTS: TASKS/NLP_SKELETON.md

  Executive Summary

  This document formalizes the implementation plan for the NLP Service's
  Phase 1 student matching feature. Building upon the existing service
  skeleton, this plan details the two-stage approach (Extraction →
  Matching) with extreme focus on robustness and testing.

  Architecture Overview

  Two-Stage Processing Pipeline

  graph LR
      A[Essay Text] --> B[Stage 1: Extraction Pipeline]
      B --> C[ExtractedIdentifiers]
      C --> D[Stage 2: Roster Matching]
      E[Class Roster] --> D
      D --> F[StudentMatchSuggestions]
      F --> G[Essay Author Match Event]

  Key Design Principles

  1. Pipeline Pattern: Multiple extraction strategies tried in order
  2. Early Exit: Stop extraction when confidence threshold met
  3. Configurable Thresholds: All magic numbers in settings
  4. Swedish Name Support: First-class citizen from day one
  5. Comprehensive Testing: 95%+ coverage for matching algorithms

  Detailed Implementation Plan

  1. Data Models (Pydantic)

  # services/nlp_service/matching_algorithms/models.py
  """Data models for the extraction and matching pipeline."""

  from __future__ import annotations
  from pydantic import BaseModel, Field
  from typing import Literal

  class ExtractedIdentifier(BaseModel):
      """A single piece of information extracted from text."""
      value: str = Field(description="The extracted string (e.g., a name or
   email)")
      source_strategy: str = Field(description="The strategy that extracted
   this value")
      confidence: float = Field(ge=0.0, le=1.0, description="Extraction 
  confidence")
      location_hint: str = Field(default="", description="Where in text it 
  was found")

  class ExtractionResult(BaseModel):
      """Consolidated output from the extraction pipeline."""
      possible_names: list[ExtractedIdentifier] =
  Field(default_factory=list)
      possible_emails: list[ExtractedIdentifier] =
  Field(default_factory=list)
      metadata: dict[str, any] = Field(default_factory=dict,
  description="Extra info")

      def is_empty(self) -> bool:
          """Check if any identifiers were extracted."""
          return not self.possible_names and not self.possible_emails

      def highest_confidence_name(self) -> ExtractedIdentifier | None:
          """Get the name with highest extraction confidence."""
          if not self.possible_names:
              return None
          return max(self.possible_names, key=lambda x: x.confidence)

  class NameComponents(BaseModel):
      """Parsed name components for matching."""
      first_name: str
      last_name: str
      middle_names: list[str] = Field(default_factory=list)
      full_name: str

      @classmethod
      def from_full_name(cls, full_name: str) -> "NameComponents":
          """Parse a full name into components (Swedish-aware)."""
          # Implementation in swedish_name_parser.py

  class MatchReason(str, Enum):
      """Reasons for student match."""
      EMAIL_EXACT = "email_exact"
      EMAIL_FUZZY = "email_fuzzy"
      NAME_EXACT = "name_exact"
      NAME_FUZZY = "name_fuzzy"
      NAME_PARTIAL = "name_partial"
      FIRST_LAST_MATCH = "first_last_match"

  2. Configuration Updates

  # services/nlp_service/config.py additions
  class Settings(BaseSettings):
      # ... existing settings ...

      # Student Matching Configuration
      EXTRACTION_CONFIDENCE_THRESHOLD: float = Field(
          default=0.7,
          description="Confidence to exit extraction pipeline early"
      )
      EXTRACTION_MAX_STRATEGIES: int = Field(
          default=3,
          description="Max strategies to try before giving up"
      )

      # Roster Matching Thresholds
      MATCH_NAME_FUZZY_THRESHOLD: float = Field(
          default=0.7,
          description="Minimum similarity for fuzzy name match"
      )
      MATCH_EMAIL_FUZZY_THRESHOLD: float = Field(
          default=0.9,
          description="Minimum similarity for fuzzy email match"
      )
      MATCH_NAME_EXACT_CONFIDENCE: float = Field(
          default=0.95,
          description="Confidence score for exact name matches"
      )
      MATCH_EMAIL_EXACT_CONFIDENCE: float = Field(
          default=0.98,
          description="Confidence score for exact email matches"
      )

      # Extraction Patterns (configurable)
      HEADER_PATTERNS: list[str] = Field(
          default=[
              r"Name:\s*(.+)",
              r"Student:\s*(.+)",
              r"Author:\s*(.+)",
              r"By:\s*(.+)",
              r"Submitted by:\s*(.+)",
              r"Written by:\s*(.+)",
              r"Namn:\s*(.+)",  # Swedish
          ]
      )

      EMAIL_CONTEXT_WINDOW: int = Field(
          default=50,
          description="Characters to search around email for name"
      )

  3. Directory Structure

  services/nlp_service/
  ├── matching_algorithms/
  │   ├── __init__.py
  │   ├── models.py                     # Data models (above)
  │   ├── extraction/
  │   │   ├── __init__.py
  │   │   ├── base_extractor.py        # Abstract base
  │   │   ├── examnet_extractor.py     # Exam.net 4-paragraph
  │   │   ├── header_extractor.py      # Pattern-based headers
  │   │   ├── email_anchor_extractor.py # Email proximity
  │   │   ├── signature_extractor.py   # End of essay
  │   │   └── extraction_pipeline.py   # Orchestrator
  │   ├── matching/
  │   │   ├── __init__.py
  │   │   ├── base_matcher.py          # Abstract base
  │   │   ├── email_matcher.py         # Email matching logic
  │   │   ├── name_matcher.py          # Name fuzzy matching
  │   │   ├── swedish_name_parser.py   # Name parsing
  │   │   ├── confidence_calculator.py # Scoring logic
  │   │   └── roster_matcher.py        # Main orchestrator
  │   └── utils/
  │       ├── __init__.py
  │       ├── text_normalizer.py       # Clean text, handle encoding
  │       └── string_similarity.py     # Fuzzy matching helpers
  ├── implementations/               # (Already exists)
  │   ├── content_client_impl.py
  │   ├── roster_client_impl.py
  │   ├── roster_cache_impl.py
  │   └── event_publisher_impl.py

  4. Extraction Pipeline Implementation

  # matching_algorithms/extraction/extraction_pipeline.py
  class ExtractionPipeline:
      """Orchestrates multiple extraction strategies."""

      def __init__(
          self,
          strategies: list[BaseExtractor],
          settings: Settings,
      ):
          self.strategies = strategies
          self.confidence_threshold =
  settings.EXTRACTION_CONFIDENCE_THRESHOLD
          self.max_strategies = settings.EXTRACTION_MAX_STRATEGIES

      async def extract(
          self,
          text: str,
          filename: str | None = None,
          metadata: dict[str, any] | None = None,
      ) -> ExtractionResult:
          """Run strategies until threshold met or exhausted."""
          result = ExtractionResult()
          strategies_tried = 0

          for strategy in self.strategies:
              if strategies_tried >= self.max_strategies:
                  break

              try:
                  strategy_result = await strategy.extract(text, filename,
  metadata)
                  result = self._merge_results(result, strategy_result)

                  # Check if we have high confidence results
                  if self._should_exit_early(result):
                      logger.info(f"Exiting early after 
  {strategy.__class__.__name__}")
                      break

              except Exception as e:
                  logger.warning(f"Strategy {strategy.__class__.__name__} 
  failed: {e}")

              strategies_tried += 1

          return result

  5. Roster Matching Implementation

  # matching_algorithms/matching/roster_matcher.py
  class RosterMatcher:
      """Matches extracted info against class roster."""

      def __init__(
          self,
          name_matcher: NameMatcher,
          email_matcher: EmailMatcher,
          confidence_calculator: ConfidenceCalculator,
          settings: Settings,
      ):
          self.name_matcher = name_matcher
          self.email_matcher = email_matcher
          self.confidence_calculator = confidence_calculator
          self.settings = settings

      async def match_student(
          self,
          extracted: ExtractionResult,
          roster: list[StudentInfo],
      ) -> list[StudentMatchSuggestion]:
          """Match extracted info against roster."""
          all_suggestions = []

          # Email matching (highest priority)
          for identifier in extracted.possible_emails:
              email_matches = await self.email_matcher.match(
                  identifier.value,
                  roster,
              )
              all_suggestions.extend(email_matches)

          # Name matching
          for identifier in extracted.possible_names:
              name_matches = await self.name_matcher.match(
                  identifier.value,
                  roster,
              )
              all_suggestions.extend(name_matches)

          # Deduplicate and sort by confidence
          return self._deduplicate_and_rank(all_suggestions)

  6. Event Processing Integration

  # event_processor.py updates
  async def process_single_message(
      msg: ConsumerRecord,
      # ... existing parameters ...
      extraction_pipeline: ExtractionPipeline,  # From DI
      roster_matcher: RosterMatcher,           # From DI
      content_client: ContentClientProtocol,   # From DI
      roster_client: ClassRosterClientProtocol, # From DI
      roster_cache: RosterCacheProtocol,       # From DI
      outbox_repository: OutboxRepository,     # From DI
  ) -> bool | None:
      """Process NLP batch command with student matching."""
      # ... parse command ...

      for essay_ref in command_data.essays_to_process:
          # 1. Fetch essay content
          essay_text = await content_client.fetch_content(
              storage_id=essay_ref.text_storage_id,
              http_session=http_session,
              correlation_id=correlation_id,
          )

          # 2. Get roster (with caching)
          roster = await roster_cache.get_roster(essay_ref.class_id)
          if not roster:
              roster = await roster_client.get_class_roster(
                  class_id=essay_ref.class_id,
                  http_session=http_session,
                  correlation_id=correlation_id,
              )
              await roster_cache.set_roster(essay_ref.class_id, roster)

          # 3. Extract identifiers
          extracted = await extraction_pipeline.extract(
              text=essay_text,
              filename=essay_ref.filename,
          )

          # 4. Match against roster
          suggestions = await roster_matcher.match_student(
              extracted=extracted,
              roster=roster,
          )

          # 5. Determine match status
          match_status = determine_match_status(suggestions)

          # 6. Publish via outbox
          await publish_match_result(
              essay_id=essay_ref.essay_id,
              suggestions=suggestions,
              match_status=match_status,
              outbox_repository=outbox_repository,
          )

  7. Testing Strategy

  Unit Test Structure

  tests/unit/
  ├── extraction/
  │   ├── test_examnet_extractor.py      # 95%+ coverage
  │   ├── test_header_extractor.py       # 95%+ coverage
  │   ├── test_email_anchor_extractor.py # 95%+ coverage
  │   └── test_extraction_pipeline.py    # 95%+ coverage
  ├── matching/
  │   ├── test_email_matcher.py          # 95%+ coverage
  │   ├── test_name_matcher.py           # 95%+ coverage
  │   ├── test_swedish_name_parser.py    # Edge cases!
  │   └── test_roster_matcher.py         # 95%+ coverage
  └── utils/
      └── test_string_similarity.py      # 95%+ coverage

  Test Data Requirements

  # tests/fixtures/essay_samples.py
  ESSAY_SAMPLES = {
      "examnet_standard": "...",          # Real exam.net format
      "examnet_malformed": "...",        # Missing paragraphs
      "word_upload": "...",              # Title page format
      "swedish_names": "...",            # Å, Ä, Ö, compound names
      "no_identifiers": "...",           # No extractable info
      "multiple_matches": "...",         # Ambiguous case
  }

  # tests/fixtures/roster_samples.py
  ROSTER_SAMPLES = {
      "standard_class": [...],           # 20-30 students
      "swedish_names": [...],            # Complex Swedish names
      "similar_names": [...],            # Johan Andersson x3
      "international": [...],            # Mixed name origins
  }

  8. Dependencies Update

  # services/nlp_service/pyproject.toml
  [project]
  dependencies = [
      # ... existing ...
      "thefuzz[speedup]>=0.22.1",  # Fuzzy string matching
      # Future: "spacy>=3.7.0" for NER
  ]

  [dependency-groups]
  dev = [
      # ... existing ...
      "faker>=28.0.0",  # Generate test data
  ]

  9. Performance Requirements

  - Extraction: <50ms per essay
  - Roster Matching: <50ms per essay
  - Total Processing: <100ms per essay (excluding API calls)
  - Memory: <100MB for 1000 concurrent essays

  10. Monitoring & Metrics

  # metrics.py additions
  extraction_strategy_counter = Counter(
      "nlp_extraction_strategy_used_total",
      "Count of extraction strategies used",
      ["strategy", "success"],
  )

  match_confidence_histogram = Histogram(
      "nlp_match_confidence_score",
      "Distribution of match confidence scores",
      buckets=(0.1, 0.3, 0.5, 0.7, 0.8, 0.9, 0.95, 0.99, 1.0),
  )

  extraction_duration_histogram = Histogram(
      "nlp_extraction_duration_seconds",
      "Time spent in extraction pipeline",
      ["strategy"],
  )

  Success Criteria

  1. Extraction Coverage: >80% of essays have identifiable information
  extracted
  2. Matching Accuracy: >90% correct matches when information exists
  3. False Positive Rate: <5% incorrect high-confidence matches
  4. Performance: <100ms total processing time per essay
  5. Test Coverage: >95% for all matching algorithm code
  6. Swedish Name Support: 100% of test cases pass

  Risk Mitigation

  1. Risk: Poor extraction from new essay formats
    - Mitigation: Extensible pipeline, easy to add strategies
  2. Risk: False positives in matching
    - Mitigation: Configurable thresholds, confidence scores
  3. Risk: Performance degradation with large rosters
    - Mitigation: Caching, optimized fuzzy matching
  4. Risk: Swedish name edge cases
    - Mitigation: Dedicated parser, comprehensive test suite

  Implementation Timeline

  1. Week 1: Core models and extraction strategies
  2. Week 2: Matching algorithms and Swedish name support
  3. Week 3: Integration and performance optimization
  4. Week 4: Comprehensive testing and edge cases

  ---
  This plan provides a concrete, testable, and robust foundation for the
  student matching feature while maintaining flexibility for future
  enhancements.

