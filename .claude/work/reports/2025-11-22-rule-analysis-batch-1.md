# Rule Analysis - Batch 1 (000-041)

**Analysis Date**: 2025-11-22  
**Rules Analyzed**: 31 files  
**Purpose**: Distill rule characteristics for Pydantic frontmatter schema design

---

## Executive Summary

Batch 1 (000-041) establishes the foundational and architectural layer of the HuleEdu rule system:

- **1 index rule** (000): Master catalog
- **3 foundation rules** (010, 015, 020): Core architecture
- **20 service-spec rules** (020.1-020.20): Individual service architectures  
- **2 architecture rules** (030, 035-037.1): EDA standards + workflows
- **2 implementation rules** (040-041): Service implementation patterns

**Key Patterns**:
- Service specs dominate (64.5% of batch)
- Strict hierarchical naming (020 → 020.X)
- Sequential workflow chains (035 → 036 → 037 → 037.1)
- Foundation rules use `alwaysApply: true`
- Service rules use `alwaysApply: false` with targeted globs
- **Critical**: Workflow rules 035-037 LACK frontmatter entirely

---

## Rule Inventory

| ID | Type | Scope | Enforcement | Maintenance |
|----|------|-------|-------------|-------------|
| 000-rule-index | index | all | high | evolving |
| 010-foundational-principles | foundation | all | critical | stable |
| 015-project-structure | foundation | all | critical | stable |
| 020-architectural-mandates | architecture | all | critical | stable |
| 020.1-content-service | service-spec | specific | high | evolving |
| 020.2-spellchecker | service-spec | specific | high | evolving |
| 020.3-batch-orchestrator | service-spec | specific | high | evolving |
| 020.4-common-core | service-spec | all | critical | evolving |
| 020.5-essay-lifecycle | service-spec | specific | high | evolving |
| 020.6-file-service | service-spec | specific | high | evolving |
| 020.7-cj-assessment | service-spec | specific | high | dynamic |
| 020.8-batch-conductor | service-spec | specific | high | evolving |
| 020.9-class-management | service-spec | specific | high | evolving |
| 020.10-api-gateway | service-spec | specific | critical | evolving |
| 020.11-service-libraries | service-spec | all | critical | stable |
| 020.12-result-aggregator | service-spec | specific | high | evolving |
| 020.13-llm-provider | service-spec | specific | critical | dynamic |
| 020.14-websocket | service-spec | specific | high | evolving |
| 020.15-nlp-service | service-spec | specific | high | evolving |
| 020.16-email-service | service-spec | specific | high | evolving |
| 020.17-entitlements | service-spec | specific | high | evolving |
| 020.18-language-tool | service-spec | specific | high | evolving |
| 020.19-eng5-runner | service-spec | infrastructure | high | evolving |
| 020.20-cj-llm-prompt | service-spec | specific | high | dynamic |
| 030-eda-standards | architecture | all | critical | stable |
| 035-flow-overview | workflow | cross-service | high | evolving |
| 036-phase1-flow | workflow | cross-service | high | evolving |
| 037-phase2-flow | workflow | cross-service | high | evolving |
| 037.1-cj-phase-flow | workflow | specific | high | dynamic |
| 040-service-impl-guide | implementation | backend | critical | stable |
| 041-http-blueprint | implementation | backend | critical | stable |

---

## Pattern Analysis

### 1. Type Distribution

- **service-spec**: 20 (64.5%)
- **foundation**: 3 (9.7%)
- **workflow**: 4 (12.9%)
- **architecture**: 2 (6.5%)
- **implementation**: 2 (6.5%)
- **index**: 1 (3.2%)

### 2. Hierarchical Structure

```
000 (index)
├─ 010, 015, 020 (foundation/architecture)
│  └─ 020.1 - 020.20 (service specs)
├─ 030 (EDA standards)
├─ 035 (workflow root)
│  ├─ 036 (phase 1)
│  ├─ 037 (phase 2)
│  │  └─ 037.1 (CJ detail)
├─ 040 (implementation)
└─ 041 (HTTP blueprint)
```

### 3. Service Spec Patterns

All 020.X rules follow consistent structure:
1. Service Identity (package, ports, stack, purpose)
2. Architecture/Components
3. API/Event Contracts
4. Configuration
5. Integration Points
6. Production Requirements

**Variations**:
- Libraries (020.4, 020.11): No ports/APIs
- Containers (020.19): Deployment focus
- Reference (020.20): Mapping document

### 4. Frontmatter Inconsistencies

**Has Frontmatter**: 000, 010, 015, 020, 020.X (all service specs), 030, 037.1, 040, 041

**Missing Frontmatter**: 035, 036, 037 (workflow overview rules)

**Pattern**: Numbered decimal rules (X.Y) have frontmatter, but parent workflow rules don't.

---

## Frontmatter Schema Insights

### Required Fields

1. **id**: Rule identifier (e.g., "020.7-cj-assessment-service")
2. **description**: One-line summary (max 200 chars)
3. **type**: Literal["index", "foundation", "architecture", "service-spec", "workflow", "implementation"]
4. **scope**: Literal["all", "backend", "specific-service", "cross-service", "infrastructure"]
5. **enforcement**: Literal["critical", "high", "medium", "low"]
6. **artifacts**: list[Literal["code", "config", "contracts", "documentation"]]
7. **maintenance**: Literal["stable", "evolving", "dynamic"]

### Optional Fields

1. **globs**: list[str] - File patterns
2. **alwaysApply**: bool - Universal application
3. **depends_on**: list[str] - Rule ID dependencies
4. **service_name**: str - For service-spec rules
5. **service_type**: Literal["HTTP", "Worker", "Hybrid", "Library", "Container"]
6. **ports**: dict[str, int] - Port mappings
7. **stack**: list[str] - Technology components
8. **has_checklist**: bool
9. **includes_examples**: bool
10. **parent_rule**: str - For hierarchical rules

### Pydantic Model Proposal

```python
from typing import Literal
from pydantic import BaseModel, Field, field_validator
import re

class RuleFrontmatter(BaseModel):
    # Required
    id: str
    description: str
    type: Literal["index", "foundation", "architecture", "service-spec", "workflow", "implementation"]
    scope: Literal["all", "backend", "specific-service", "cross-service", "infrastructure"]
    enforcement: Literal["critical", "high", "medium", "low"]
    artifacts: list[Literal["code", "config", "contracts", "documentation"]]
    maintenance: Literal["stable", "evolving", "dynamic"]
    
    # Optional
    globs: list[str] = Field(default_factory=list)
    alwaysApply: bool = False
    depends_on: list[str] = Field(default_factory=list)
    service_name: str | None = None
    service_type: Literal["HTTP", "Worker", "Hybrid", "Library", "Container"] | None = None
    ports: dict[str, int] = Field(default_factory=dict)
    stack: list[str] = Field(default_factory=list)
    has_checklist: bool = False
    includes_examples: bool = False
    parent_rule: str | None = None
    
    @field_validator('id')
    def validate_id(cls, v):
        if not re.match(r'^\d{3}(\.\d+)?(-[a-z-]+)?$', v):
            raise ValueError("Invalid rule ID format")
        return v
```

---

## Cross-References Found

- 020 → 042.1 (transactional outbox - batch 2)
- 035 → 051, 052 (not in batch 1)
- 037.1 → 020.7, 020.13
- 041 → 015

**Insight**: Forward references exist, requiring cross-batch dependency validation.

---

## Recommendations for Batch 2

### Watch For

1. **Missing frontmatter backfill**: Should 035-037 get frontmatter?
2. **Forward references**: Validate 042.1, 051, 052 existence
3. **Glob consistency**: Establish when globs are required
4. **Status tracking**: Some services marked "OPERATIONAL" - add to frontmatter?

### Schema Adjustments

1. Add `version`/`last_updated` fields
2. Add `status` for service rules
3. Strengthen dependency validation
4. Add framework tags (Quart vs FastAPI)
5. Extract checklists as separate artifacts

---

## Conclusion

Batch 1 reveals a highly structured but inconsistent system:

- **Service specs** dominate with consistent structure
- **Foundation rules** use `alwaysApply: true`
- **Workflow rules** lack frontmatter (needs investigation)
- **Dependencies** are implicit, not frontmatter-based
- **Standardization** needed across all rule types

**Next Steps**:
1. Analyze batch 2 (042-085) for validation
2. Design comprehensive Pydantic schema
3. Create frontmatter validation tooling
4. Backfill missing frontmatter (if appropriate)
