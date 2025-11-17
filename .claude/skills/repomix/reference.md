# Repomix Package Builder - Detailed Reference

Comprehensive guide for creating targeted repomix packages optimized for AI code analysis.

## Table of Contents

1. [Package Templates](#package-templates)
2. [File Selection Guidance](#file-selection-guidance)
3. [Workflow Steps](#workflow-steps)
4. [Best Practices](#best-practices)
5. [Integration with Project Standards](#integration-with-project-standards)

---

## Package Templates

### 1. Metadata Flow Analysis

**Use Case**: Trace how data/metadata flows between services through events and API calls.

**File Categories**:
- Event contracts (`libs/common_core/src/common_core/events/`)
- Service implementations (request originators and result processors)
- Internal models and queue models
- Protocols and DI configurations
- Event enums and topic definitions

**Example Includes**:
```bash
libs/common_core/src/common_core/events/cj_assessment_events.py,
libs/common_core/src/common_core/events/llm_provider_events.py,
libs/common_core/src/common_core/event_enums.py,
services/cj_assessment_service/implementations/llm_interaction_impl.py,
services/llm_provider_service/implementations/queue_processor_impl.py,
services/cj_assessment_service/protocols.py,
services/llm_provider_service/protocols.py
```

**Output Naming**: `repomix-{feature}-{flow-type}-flow.xml`
- Example: `repomix-metadata-population-task.xml`
- Example: `repomix-cj-llm-integration-flow.xml`

---

### 2. Code Review Package

**Use Case**: Comprehensive review of implementation, tests, patterns, and compliance with standards.

**File Categories**:
- Core implementation files (main logic + tests)
- Event contracts (if event-driven)
- Service patterns (DI, protocols, config)
- Documentation (handoff.md, readme-first.md, task docs)
- Infrastructure (idempotency, logging, error handling)
- Critical rules (042-async-patterns, 048-error-handling, 051-pydantic, 052-event-contracts, 075-testing)

**Example Includes**:
```bash
.claude/research/scripts/eng5_np_batch_runner.py,
.claude/research/scripts/test_eng5_np_batch_runner.py,
services/cj_assessment_service/kafka_consumer.py,
libs/common_core/src/common_core/events/*.py,
services/cj_assessment_service/event_processor.py,
.claude/work/session/handoff.md,
.claude/work/session/readme-first.md,
TASKS/TASK-*.md,
.claude/rules/042-async-patterns-and-di.md,
.claude/rules/048-structured-error-handling-standards.md,
.claude/rules/075-test-creation-methodology.md
```

**Output Naming**: `repomix-{component}-{purpose}-review.xml`
- Example: `repomix-eng5-kafka-review.xml`
- Example: `repomix-batch-runner-implementation-review.xml`

---

### 3. Architecture Analysis

**Use Case**: Understand system design, service boundaries, DDD layers, and cross-cutting concerns.

**File Categories**:
- Service boundaries (protocols.py, di.py, app.py)
- Event-driven patterns (event_processor, kafka_consumer)
- DDD layers (domain models, repositories, core logic)
- Cross-cutting concerns (observability, error handling, idempotency)
- Architectural rules (020-architectural-mandates, 030-eda-standards, 037-phase-processing)

**Example Includes**:
```bash
services/*/protocols.py,
services/*/di.py,
services/*/kafka_consumer.py,
services/*/event_processor.py,
libs/common_core/src/common_core/events/*.py,
.claude/rules/020-architectural-mandates.md,
.claude/rules/030-event-driven-architecture-eda-standards.md,
.claude/rules/042-async-patterns-and-di.md
```

**Output Naming**: `repomix-{scope}-architecture-analysis.xml`
- Example: `repomix-cj-assessment-architecture-analysis.xml`
- Example: `repomix-event-driven-architecture-analysis.xml`

---

### 4. Minimal Context

**Use Case**: Quick context package with just essential documentation and key implementation files.

**File Categories**:
- Task documentation (TASKS/*.md)
- Handoff and README files (.claude/work/session/handoff.md, .claude/work/session/readme-first.md)
- Primary implementation file(s)
- Relevant event contracts (if applicable)

**Example Includes**:
```bash
.claude/work/session/handoff.md,
.claude/work/session/readme-first.md,
TASKS/TASK-{specific-task}.md,
{primary-implementation-file}.py
```

**Output Naming**: `repomix-{task-name}-context.xml`
- Example: `repomix-cj-assessment-context.xml`

---

## File Selection Guidance

### HuleEdu Monorepo Structure

```
huledu-reboot/
├── services/                    # Microservices
│   ├── cj_assessment_service/
│   ├── llm_provider_service/
│   ├── essay_lifecycle_service/
│   └── [other services]/
├── libs/                        # Shared libraries
│   ├── common_core/            # Event contracts, enums, domain models
│   └── huleedu_service_libs/   # Service utilities (DI, logging, idempotency)
├── .claude/                     # Claude Code artifacts
│   ├── rules/                  # Architectural standards
│   ├── research/               # Analysis scripts and data
│   ├── repomix_packages/       # Generated packages (output location)
│   ├── work/session/
│   │   ├── handoff.md          # Current project state
│   │   └── readme-first.md     # Critical context
├── TASKS/                       # Task documentation
├── Documentation/               # Schemas, architecture docs
└── test_uploads/                # Test data and fixtures
```

### Common Include Patterns

**Event-Driven Flow Analysis**:
```
libs/common_core/src/common_core/events/*.py,
libs/common_core/src/common_core/event_enums.py,
services/{service}/event_processor.py,
services/{service}/kafka_consumer.py
```

**Service Implementation Deep Dive**:
```
services/{service}/*.py,
services/{service}/implementations/*.py,
services/{service}/cj_core_logic/*.py,
services/{service}/tests/unit/*.py,
services/{service}/tests/integration/*.py
```

**Shared Infrastructure**:
```
libs/huleedu_service_libs/src/huleedu_service_libs/idempotency_v2.py,
libs/huleedu_service_libs/src/huleedu_service_libs/logging_utils.py,
libs/huleedu_service_libs/src/huleedu_service_libs/error_handling/*.py
```

**Rules and Standards**:
```
.claude/rules/000-rule-index.md,
.claude/rules/020-architectural-mandates.md,
.claude/rules/042-async-patterns-and-di.md,
.claude/rules/048-structured-error-handling-standards.md,
.claude/rules/051-pydantic-v2-standards.md,
.claude/rules/052-event-contract-standards.md,
.claude/rules/075-test-creation-methodology.md
```

---

## Workflow Steps

### 1. Understand Task Objective

Ask clarifying questions:
- What is the analysis goal? (review, debugging, documentation, architecture study)
- Which services or components are involved?
- Is this focused on a specific feature, bug, or integration flow?
- Are there specific files or patterns the user already knows are relevant?

### 2. Select Package Template

Map the objective to one of the templates:
- **Metadata Flow**: Cross-service data propagation questions
- **Code Review**: Implementation quality, testing, standards compliance
- **Architecture Analysis**: System design, patterns, boundaries
- **Minimal Context**: Quick overview or initial exploration

### 3. Build Include List

Based on the template and monorepo structure:
1. Start with core categories (events, implementations, protocols)
2. Add service-specific files based on task scope
3. Include relevant documentation (handoff, task docs, README)
4. Add infrastructure files if relevant (logging, error handling, DI)
5. Include applicable rules from `.claude/rules/`

### 4. Generate Filename

Format: `repomix-{feature/service}-{purpose}.xml`

Components:
- `{feature/service}`: Short identifier (e.g., `eng5`, `cj-assessment`, `metadata-population`)
- `{purpose}`: Analysis type (e.g., `review`, `flow`, `context`, `architecture-analysis`)

### 5. Execute Repomix Command

```bash
repomix --style xml \
  --no-gitignore \
  --output .claude/repomix_packages/{filename}.xml \
  --include "file1,file2,file3,..."
```

### 6. Report Statistics

After generation, inform user of:
- Total files included
- Total tokens (important for AI context window planning)
- Top files by token count
- Output location and file size

---

## Best Practices

### General Principles

1. **Start Small**: For exploratory analysis, start with minimal context and expand as needed
2. **Avoid Noise**: Exclude test fixtures, migrations, and large data files unless specifically needed
3. **Include Context**: Always include `.claude/work/session/handoff.md` and `.claude/work/session/readme-first.md` for critical project context
4. **Match Patterns**: Follow existing naming conventions visible in `.claude/repomix_packages/`
5. **Verify Files Exist**: Before executing, ensure suggested files exist in the repository
6. **Token Budget**: For AI analysis, target 70K-100K tokens for comprehensive reviews, <30K for focused analysis

### File Selection Strategies

**For Metadata Flow Analysis**:
- Include both ends of the communication (requester and responder)
- Add event contracts that define the message schemas
- Include any transformation or mapping logic
- Add protocols to show interface contracts

**For Code Review**:
- Always include tests alongside implementation
- Add relevant rule files to check compliance
- Include DI/protocol files to understand dependencies
- Add task documentation for context

**For Architecture Analysis**:
- Focus on boundaries (protocols, DI, app initialization)
- Include event processors and consumers for event-driven patterns
- Add architectural rule files
- Skip implementation details unless illustrating a pattern

### Token Budget Management

**Target Ranges**:
- **Quick Context**: 20-30K tokens (~7-10 files)
  - Task docs, HANDOFF, key implementation
- **Standard Review**: 60-80K tokens (~25-35 files)
  - Implementation + tests + events + some rules
- **Deep Analysis**: 80-100K tokens (~30-40 files)
  - Comprehensive coverage of a feature or service

**Optimization Tips**:
- Large JSON/CSV files: Exclude unless needed for data structure examples
- Test fixtures: Usually safe to exclude
- Multiple similar files: Pick representative examples
- Generated code: Skip migrations, build artifacts

---

## Integration with Project Standards

### Alignment with HuleEdu Codebase

- **Artifact Organization**: Follows `.claude/` artifact pattern
- **Gitignore Compliance**: `.claude/repomix_packages/` is properly excluded
- **Monorepo Structure**: Respects services/, libs/, .claude/ hierarchy
- **Task Documentation**: Compatible with existing TASKS/ workflow
- **DDD & Event-Driven**: Supports analysis of domain boundaries and event flows

### Relationship to Other Claude Code Features

**Skills**:
- This skill focuses on package generation
- Works alongside documentation, planning, and review skills

**Slash Commands**:
- `/repomix` provides interactive workflow
- User can trigger explicitly when needed
- Skill activates passively when context suggests it

**Agents**:
- Agents handle complex multi-step workflows
- This skill supports single-purpose package creation
- Can be invoked by agents as part of larger workflows

---

## Related Resources

- **examples.md**: Real-world usage examples from HuleEdu development
- **SKILL.md**: Quick reference and activation criteria
- **`.claude/commands/repomix.md`**: Interactive slash command interface
- **`.claude/rules/000-rule-index.md`**: Index of all architectural rules
- **`.claude/work/session/handoff.md`**: Current project state and context
