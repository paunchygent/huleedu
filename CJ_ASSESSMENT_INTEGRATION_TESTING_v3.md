# 🔄 LLM Provider Service Cache Refactor Task

MANDATORY PRE-TASK READING

You MUST read these files in EXACT order before proceeding:

1. Core Architecture Rules

.cursor/rules/010-foundational-principles.mdc          #
Zero tolerance for architectural deviation
.cursor/rules/020-architectural-mandates.mdc           #
Service communication patterns, DI requirements
  .cursor/rules/030-event-driven-architecture-eda-standards.md
  c  # Kafka event patterns
  .cursor/rules/042-async-patterns-and-di.mdc           #
  Dishka patterns, async context managers
  .cursor/rules/051-pydantic-v2-standards.mdc           #
  Event envelope patterns
  .cursor/rules/070-testing-and-quality-assurance.mdc   #
  Protocol-based testing
  .cursor/rules/080-repository-workflow-and-tooling.mdc # PDM
  commands, development workflow

2. Task Context & Current Implementation

documentation/TASKS/LLM_CALLER_SERVICE_IMPLEMENTATION_v2.md

# Full task details & refactor plan

  services/llm_provider_service/README.md

# Service documentation

  services/llm_provider_service/config.py

# Current cache configuration

  services/llm_provider_service/protocols.py

# LLMCacheManagerProtocol interface

  services/llm_provider_service/implementations/llm_orchestrat
  or_impl.py  # Cache integration point
  services/llm_provider_service/implementations/resilient_cach
  e_manager_impl.py  # Current cache logic
  services/llm_provider_service/implementations/redis_cache_re
  pository_impl.py   # Redis implementation
  services/llm_provider_service/implementations/local_cache_ma
  nager_impl.py      # Local cache fallback

3. Service Context & Dependencies

services/cj_assessment_service/README.md              #
Understand CJ methodology requirements
common_core/src/common_core/enums.py                  #
EnvironmentType enum
common_core/src/common_core/events/envelope.py        #
EventEnvelope pattern

CRITICAL UNDERSTANDING CHECKPOINTS

Before writing ANY code, you MUST be able to answer these
questions correctly:

1. Psychometric Understanding

- Why does caching identical responses break CJ Assessment
  methodology?
- What is Bradley-Terry modeling and why does it require
  judgment variation?
- How does perfect consistency create an invalid
  "super-rater"?

2. Service Contract Understanding

- Why is serving cached responses to paying users a contract
   violation?
- What is the difference between caching for resilience vs
  caching for serving?
- When is caching acceptable and when is it forbidden?

3. Current Implementation Understanding

- Where in llm_orchestrator_impl.py is the cache checked?
  (Line numbers)
- What is the cache key generation logic in
  redis_cache_repository_impl.py?
- How does resilient_cache_manager_impl.py handle Redis
  failures?
- Why does checking cache BEFORE circuit breaker defeat the
  purpose?

4. Architecture Alignment

- What is the HuleEdu pattern for environment-aware
  configuration?
- How must protocols be modified according to rule 042?
- What is the correct async context manager pattern for
  queue resources?
- How should Kafka events be published for queue status
  changes?

TASK SPECIFICATION

Goal: Refactor the LLM Provider Service cache system from
response-caching to queue-based resilience.

Key Requirements:

1. Production: NO response caching - every request gets
fresh LLM response
2. Outages: Queue requests with "processing" status - never
serve cached responses
3. Development: Cache available ONLY with explicit opt-in
flag
4. Preserve: Psychometric validity for CJ Assessment,
service integrity for AI Feedback

Implementation Phases:

1. Add queue infrastructure (Redis-backed for production,
in-memory for dev)
2. Refactor cache to development-only mode
3. Implement async processing with TTLs
4. Update API contract for queue status
5. Integrate with consuming services

EXPECTED APPROACH

1. First: Demonstrate understanding by explaining the
current flow and why it's wrong
2. Second: Propose protocol changes following HuleEdu
patterns
3. Third: Implement queue manager with proper DI and async
patterns
4. Fourth: Refactor orchestrator to use queue instead of
  cache for production
5. Fifth: Add comprehensive tests following protocol-based
  mocking

SUCCESS CRITERIA

Your implementation MUST:

- Follow all HuleEdu architectural patterns exactly
- Use proper Dishka DI with protocol definitions
- Implement environment-aware behavior using common_core
  enums
- Include comprehensive tests with protocol mocking
- Document all changes in service README
- Ensure zero cached responses in production

Remember: This is about preserving the psychometric validity
of assessments and the integrity of a paid service.
Technical elegance must serve these business requirements.