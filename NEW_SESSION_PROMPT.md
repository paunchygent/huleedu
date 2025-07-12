📋 New Session Prompt: Spellchecker Service Error Handling Standardization & Platform Excellence

  ULTRATHINK: Spellchecker Service Error Handling Modernization Session

  Objective: Complete the spellchecker service error handling standardization to achieve 100% HuleEdu platform error handling excellence through systematic migration from basic exception handling to structured HuleEduError pattern with comprehensive observability integration.

  Current Platform Status:
  - ✅ Service Architecture: spellchecker_service fully modernized with implementations/ structure and platform naming consistency
  - ✅ Type Safety: Zero MyPy errors across 495 source files
  - ✅ Code Quality: Zero Ruff violations platform-wide
  - ✅ Test Infrastructure: All 109 tests passing with PostgreSQL testcontainers
  - ⚠️ Remaining Gap: Error handling standardization across platform services (spellchecker_service Phase 1 priority)

  Critical Context: The spellchecker_service represents the foundational Phase 1 migration for platform-wide error handling standardization. Its successful modernization will establish migration patterns for 8 additional services requiring similar transformation.

  Mission: Execute systematic spellchecker service error handling modernization using proven HuleEduError patterns, eliminate all string-based error messages, integrate with observability stack, then validate comprehensive platform consistency.

  ---
  MANDATORY WORKFLOW

  Step 1: Build Core Architectural Knowledge

  You MUST begin by reading these files to understand the error handling modernization requirements and current platform state:

  Essential Context Files:
  - /Users/olofs_mba/Documents/Repos/huledu-reboot/Documentation/TASKS/ERROR_HANDLING_MIGRATION_PLAN.md - Platform-wide error handling migration strategy
  - /Users/olofs_mba/Documents/Repos/huledu-reboot/Documentation/TASKS/SPELLCHECKER_SERVICE_ERROR_HANDLING_MODERNIZATION.md - Service-specific implementation plan
  - /Users/olofs_mba/Documents/Repos/huledu-reboot/CLAUDE.md - Developer rule reference and workflow

  Rule Reference Files (.cursor/rules/ directory):
  Use .cursor/rules/000-rule-index.mdc to navigate to these essential files:
  - 020-architectural-mandates.mdc - Service autonomy and contract standards  
  - 048-structured-error-handling-standards.mdc - HuleEduError patterns and observability integration (CRITICAL)
  - 050-python-coding-standards.mdc - Type safety and code quality requirements
  - 070-testing-and-quality-assurance.mdc - Protocol-based testing standards
  - 080-repository-workflow-and-tooling.mdc - Development workflow standards

  Reference Implementations:
  - /Users/olofs_mba/Documents/Repos/huledu-reboot/services/llm_provider_service/ - Gold standard HuleEduError implementation
  - /Users/olofs_mba/Documents/Repos/huledu-reboot/services/libs/huleedu_service_libs/error_handling/ - Shared error handling infrastructure
  - /Users/olofs_mba/Documents/Repos/huledu-reboot/common_core/src/common_core/error_enums.py - ErrorCode enumerations

  Step 2: Task-Specific Analysis with ULTRATHINK

  ULTRATHINK Phase Analysis:

  Phase 1: Current State Assessment  
  - Analyze spellchecker_service current error handling patterns
  - Identify all files requiring modernization from task document
  - Assess complexity and coordination requirements

  Phase 2: Agentic Implementation Strategy
  - Deploy specialized agents for each modernization component  
  - Coordinate agent activities for systematic migration
  - Ensure all agents use ULTRATHINK methodology

  Phase 3: Validation and Excellence Verification
  - Execute comprehensive testing and validation
  - Verify error handling observability integration
  - Confirm zero functional regression with structured errors

  Step 3: Execution and Documentation

  Documentation Progress: Update task documents with implementation progress
  Test Validation: All functional code changes require comprehensive testing  
  Platform Verification: Ensure changes maintain zero MyPy errors and Ruff violations

  ---
  IMPLEMENTATION TASKS

  ULTRATHINK: Phase 1 - Repository Protocol Modernization (HIGH PRIORITY)

  Objective: Eliminate string-based error returns in repository layer and establish HuleEduError foundation.

  Implementation Requirements:
  - Update repository_protocol.py method signatures to raise HuleEduError instead of string returns
  - Modernize PostgreSQL repository implementation with structured error handling
  - Integrate correlation ID tracking and observability patterns
  - Maintain database operation reliability with improved error visibility

  Agent Deployment Strategy:
  Agent Alpha: Repository Protocol Analysis
  MISSION: Analyze current repository error handling patterns and design HuleEduError migration
  SCOPE: services/spellchecker_service/repository_protocol.py and implementations
  ULTRATHINK REQUIREMENT: Map all error scenarios and design structured ErrorCode patterns
  VALIDATION: Protocol signature compatibility and database error categorization

  ULTRATHINK: Phase 2 - Implementation Layer Modernization (INTEGRATION INTENSIVE)

  Objective: Standardize error handling across all spellchecker service implementations.

  Scope Analysis Required:
  - 5+ implementation files requiring error handling updates
  - Content client, event publisher, result store, spell logic implementations
  - Core logic error propagation patterns
  - Event processor error handling coordination

  Agent Deployment Strategy:
  Agent Beta: Implementation Error Pattern Analysis
  MISSION: Inventory all error handling patterns across spellchecker implementations
  SCOPE: services/spellchecker_service/implementations/ and core_logic.py
  ULTRATHINK REQUIREMENT: Categorize error types and design factory function integration
  OUTPUT: Comprehensive refactoring plan with error categorization

  Agent Gamma: Event Processing Error Integration
  MISSION: Modernize event processor and kafka consumer error handling
  SCOPE: event_processor.py, kafka_consumer.py, worker_main.py
  ULTRATHINK REQUIREMENT: Ensure proper error correlation across Kafka message processing
  VALIDATION: Event processing reliability and error observability

  ULTRATHINK: Phase 3 - Observability Integration (EXCELLENCE VERIFICATION)

  Objective: Verify complete error handling observability integration and platform consistency.

  Validation Requirements:

  Error Handling Validation:
  # All error scenarios use HuleEduError pattern
  # Correlation ID tracking functional across all operations  
  # OpenTelemetry error recording operational
  # Structured error details in logging system

  Functional Testing Validation:
  Agent Delta: Comprehensive Error Scenario Testing
  MISSION: Execute error handling validation across all service operations
  SCOPE: Complete spellchecker service error flows
  ULTRATHINK REQUIREMENT: Test all error scenarios with structured error verification
  COMMANDS:
  - pdm run pytest services/spellchecker_service/tests/ -v --tb=short
  - Verify error correlation ID propagation
  - Validate observability stack error integration
  - Confirm user-facing error message quality

  Platform Excellence Verification:
  - Zero string-based error returns across service
  - Zero tuple return patterns for error handling
  - All errors include correlation ID tracking
  - Complete OpenTelemetry integration functional
  - Zero regression in error user experience

  ---
  AGENT COORDINATION PROTOCOLS

  Mandatory Agent Instructions

  All agents MUST:
  1. Use ULTRATHINK methodology for every task analysis and execution
  2. Reference existing HuleEduError patterns from llm_provider_service
  3. Maintain backward compatibility for user-facing error experience
  4. Validate changes through comprehensive testing
  5. Report status with specific outcomes and integration verification

  Agent Communication Pattern

  Task Assignment Format:
  Agent [Name]: [Mission Description]
  ULTRATHINK REQUIREMENT: [Specific analysis requirement]  
  SCOPE: [Precise boundaries of work]
  VALIDATION: [Required verification steps]
  REFERENCE PATTERNS: [Existing implementations to follow]

  Agent Response Format:
  Agent [Name] Report:
  ULTRATHINK ANALYSIS: [Detailed reasoning and approach]
  EXISTING PATTERNS REVIEWED: [HuleEduError implementations referenced]
  ACTIONS TAKEN: [Specific changes made]
  VALIDATION RESULTS: [Test outcomes and integration verification]
  ISSUES IDENTIFIED: [Any problems or concerns]
  RECOMMENDATIONS: [Next steps or coordination needs]

  Error Handling Modernization Requirements

  **CRITICAL: Claude Must Handle Directly (NOT Delegated to Agents):**
  - **Pattern Understanding**: Study llm_provider_service and cj_assessment_service error handling implementations
  - **Infrastructure Setup**: Create service-specific error factories in huleedu_service_libs/error_handling/
  - **Error Categorization Design**: Define ErrorCode enums and factory function signatures
  - **Architectural Decisions**: Design correlation ID flow and observability integration patterns
  - **HuleEduError Framework Integration**: Understand and implement the complete exception-based pattern

  Use agents for:
  - File-by-file error pattern analysis and inventory
  - Implementation execution of established patterns
  - Comprehensive testing and validation
  - Documentation updates and verification
  - Line-by-line refactoring execution

  **ULTRATHINK Requirement**: Claude must first establish complete understanding of the HuleEdu error handling architecture by reading existing implementations before deploying any agents.

  ---
  CRITICAL SUCCESS CRITERIA

  Phase 1 Success Metrics

  - ✅ Repository protocol signatures modernized to HuleEduError pattern
  - ✅ PostgreSQL repository implementation uses structured error handling
  - ✅ All string-based error returns eliminated
  - ✅ Correlation ID tracking integrated

  Phase 2 Success Metrics

  - ✅ All implementations use HuleEduError factory functions
  - ✅ Event processing error handling modernized
  - ✅ Core logic error propagation standardized
  - ✅ Cross-implementation error consistency achieved

  Phase 3 Success Metrics

  - ✅ OpenTelemetry error recording functional
  - ✅ Structured error logging operational
  - ✅ All error scenarios tested and validated
  - ✅ Zero regression in error user experience

  Platform Error Handling Excellence Achievement

  - ✅ 100% HuleEduError pattern compliance across spellchecker service
  - ✅ Zero string-based error handling exceptions
  - ✅ Complete observability stack integration
  - ✅ Foundation established for 8 remaining service migrations

  ---
  CONTEXT AND CONSTRAINTS

  Current Working Environment

  Working directory: /Users/olofs_mba/Documents/Repos/huledu-reboot
  Git repository: Yes (main branch)
  Platform: darwin
  Python: 3.11 with PDM dependency management
  Docker: Available for service builds and testing

  Platform State

  - Services: 6 microservices with HuleEduApp pattern ✅
  - Database: PostgreSQL with testcontainer integration ✅
  - Messaging: Kafka event-driven architecture ✅  
  - Observability: Prometheus, Grafana, OpenTelemetry ✅
  - Quality: Zero MyPy errors, zero Ruff violations ✅
  - Architecture: Spellchecker service fully modernized ✅

  Error Handling Infrastructure

  - HuleEduError: Complete exception hierarchy available
  - Factory Functions: Comprehensive error creation patterns
  - ErrorCode Enums: Structured error categorization system
  - Observability: OpenTelemetry and logging integration ready

  ---
  READY TO BEGIN

  ## **MANDATORY EXECUTION SEQUENCE**

  **Phase 1: Claude Infrastructure Setup (REQUIRED FIRST)**
  1. Read and understand existing error handling patterns from llm_provider_service and cj_assessment_service
  2. Create spellchecker-specific error factories in huleedu_service_libs/error_handling/
  3. Define ErrorCode enums and categorization framework
  4. Design correlation ID flow and observability integration patterns
  5. Plan database migration strategy for error_message → error_detail transformation

  **Phase 2: Agent Deployment for Implementation (ONLY AFTER PHASE 1)**
  1. Deploy agents to execute established patterns across service files
  2. Use agents for comprehensive testing and validation
  3. Coordinate agent activities for systematic refactoring execution

  **CRITICAL**: Do NOT deploy agents until Claude has established the complete error handling infrastructure and architectural patterns.

  Start with ULTRATHINK analysis focusing on:
  1. **Infrastructure Understanding**: Study llm_provider_service and cj_assessment_service error handling implementations
  2. **Pattern Design**: Create service-specific error factories and categorization framework
  3. **Architectural Planning**: Design correlation ID flow and observability integration
  4. **Implementation Strategy**: Plan systematic refactoring approach with agent coordination

  Expected Outcome: Complete spellchecker service error handling modernization achieving 100% HuleEdu platform error handling excellence with comprehensive observability integration and zero functional regressions.

  MANDATORY: Use the TodoWrite tool to track all tasks and ensure systematic progress through each modernization phase.

  ULTRATHINK: Establish infrastructure foundation, then deploy agents for execution.