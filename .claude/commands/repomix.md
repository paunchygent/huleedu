---
description: Generate targeted repomix XML packages for AI code analysis and review
---

# Repomix Package Generator

Create optimized repomix packages for code analysis, review, and documentation.

## Usage

Invoke with `/repomix` to start the interactive workflow.

**Output location**: All packages saved to `.claude/repomix_packages/`

## What type of package do you need?

Please specify one of the following, or describe your custom requirements:

### Quick Templates

**1. `/repomix metadata-flow`**
- Trace data/metadata flow between services
- Includes: Event contracts, service implementations, protocols, DI configs
- Use for: Debugging cross-service integrations, understanding event propagation

**2. `/repomix code-review`**
- Comprehensive implementation review
- Includes: Core logic + tests, event contracts, service patterns, docs, rules
- Use for: Code quality review, architectural compliance, testing coverage

**3. `/repomix architecture`**
- System design and patterns analysis
- Includes: Service boundaries, DDD layers, event-driven patterns, architectural rules
- Use for: Understanding system structure, identifying patterns, refactoring planning

**4. `/repomix context`**
- Minimal essential context
- Includes: Task docs, HANDOFF.md, README_FIRST.md, key implementation files
- Use for: Quick onboarding, initial exploration

**5. `/repomix custom`**
- Interactive file selection
- Guided workflow for specific needs
- Use for: Specialized analysis, specific file combinations

## Workflow

### For Pre-defined Templates

If you selected a template above, provide:

1. **Scope**: Which services/components?
   - Example: `cj_assessment_service`, `llm_provider_service`
   - Example: `eng5_np_batch_runner`
   - Example: All event-driven services

2. **Feature/Task**: What's the focus?
   - Example: `metadata-population`
   - Example: `kafka-consumer-integration`
   - Example: `batch-processing`

3. **Additional Context**: Any specific files to include/exclude?

### For Custom Packages

If you selected custom, I'll guide you through:

1. Analysis objective (what are you trying to understand?)
2. Relevant services and components
3. Specific file patterns or paths
4. Documentation needs
5. Rule files to include

## Package Naming

Generated packages follow the pattern:
```
repomix-{feature}-{purpose}.xml
```

Examples:
- `repomix-cj-assessment-context.xml`
- `repomix-metadata-population-task.xml`
- `repomix-eng5-kafka-review.xml`

## Common File Patterns

### Event-Driven Flow
```
libs/common_core/src/common_core/events/*.py
libs/common_core/src/common_core/event_enums.py
services/{service}/event_processor.py
services/{service}/kafka_consumer.py
```

### Service Deep Dive
```
services/{service}/**/*.py
services/{service}/protocols.py
services/{service}/di.py
services/{service}/config.py
services/{service}/tests/**/*.py
```

### Shared Infrastructure
```
libs/huleedu_service_libs/src/huleedu_service_libs/*.py
libs/common_core/src/common_core/**/*.py
```

### Documentation & Standards
```
.claude/HANDOFF.md
.claude/README_FIRST.md
TASKS/*.md
.claude/rules/*.md
```

## Token Budget Guidance

Target token counts for different analysis depths:

- **Quick Context**: 20-30K tokens (~7-10 files)
- **Standard Review**: 60-80K tokens (~25-35 files)
- **Deep Analysis**: 80-100K tokens (~30-40 files)

Most AI models support up to 200K tokens, but 70-90K provides excellent detail without overwhelming context.

## Example Invocations

**Metadata Flow Analysis**:
```
/repomix metadata-flow
Scope: cj_assessment_service, llm_provider_service
Feature: metadata-population
```

**Code Review**:
```
/repomix code-review
Scope: eng5_np_batch_runner
Feature: kafka-integration
```

**Architecture Study**:
```
/repomix architecture
Scope: All assessment services
Feature: event-driven-patterns
```

## Best Practices

1. **Start Small**: Begin with context template, expand as needed
2. **Be Specific**: Clear scope = better file selection
3. **Include Context**: Always include HANDOFF.md and README_FIRST.md
4. **Exclude Noise**: Skip test fixtures, data files, migrations unless needed
5. **Verify Output**: Check token count and file list before sharing

## After Generation

I will provide:
- Total files included
- Total token count
- Top files by token count
- Output file path and size
- Suggestions for expansion/refinement (if needed)

---

**Ready to generate a package? Choose a template above or describe your custom needs.**
