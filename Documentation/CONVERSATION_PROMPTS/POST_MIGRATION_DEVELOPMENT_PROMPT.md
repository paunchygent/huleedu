# HuleEdu Platform Development: Post-Migration Phase

You are Claude Code, tasked with HuleEdu platform development following the successful library restructuring migration. The platform has achieved production readiness with a clean libs/ directory structure and requires systematic development work aligned with strict architectural standards.

## ULTRATHINK MISSION OVERVIEW

**PRIMARY OBJECTIVE**: Execute systematic development tasks on the HuleEdu platform while maintaining architectural integrity, code quality standards, and the established libs/ directory structure achieved through recent migration.

**CONTEXT**: The platform has completed a successful library restructuring migration:
- ✅ libs/common_core/ and libs/huleedu_service_libs/ operational with src layout
- ✅ 11 services built and validated (153/153 tests passing)
- ✅ Event-driven architecture functional (31 Kafka topics)
- ✅ Production deployment approved
- ✅ All documentation updated to reflect new structure

**CURRENT STATE**: Platform ready for ongoing development with identified areas for improvement including error handling standardization, code quality enhancements, and architectural evolution.

## MANDATORY WORKFLOW

### **Step 1: Build Comprehensive Understanding**

#### **Core Architecture Rules (MUST READ FIRST)**
1. **Navigation Index**:
   - `/Users/olofs_mba/Documents/Repos/huledu-reboot/.cursor/rules/000-rule-index.mdc` - Complete rule index
   
2. **Foundational Architecture**:
   - `/Users/olofs_mba/Documents/Repos/huledu-reboot/.cursor/rules/010-foundational-principles.mdc` - Core principles
   - `/Users/olofs_mba/Documents/Repos/huledu-reboot/.cursor/rules/020-architectural-mandates.mdc` - Architectural requirements
   - `/Users/olofs_mba/Documents/Repos/huledu-reboot/.cursor/rules/055-import-resolution-patterns.mdc` - Import standards
   - `/Users/olofs_mba/Documents/Repos/huledu-reboot/.cursor/rules/020.11-service-libraries-architecture.mdc` - Service libraries

3. **Implementation Standards**:
   - `/Users/olofs_mba/Documents/Repos/huledu-reboot/.cursor/rules/050-python-coding-standards.mdc` - Python standards
   - `/Users/olofs_mba/Documents/Repos/huledu-reboot/.cursor/rules/048-structured-error-handling-standards.mdc` - Error handling
   - `/Users/olofs_mba/Documents/Repos/huledu-reboot/.cursor/rules/070-testing-and-quality-assurance.mdc` - Testing standards

#### **Project Configuration & Context**
4. **Project Rules**:
   - `/Users/olofs_mba/Documents/Repos/huledu-reboot/CLAUDE.md` - Project-specific instructions
   - `/Users/olofs_mba/Documents/Repos/huledu-reboot/CLAUDE.local.md` - Development priorities
   - `/Users/olofs_mba/Documents/Repos/huledu-reboot/pyproject.toml` - Root configuration

5. **Migration Documentation**:
   - `/Users/olofs_mba/Documents/Repos/huledu-reboot/documentation/TASKS/LIBRARY_RESTRUCTURE_MIGRATION.md` - Technical implementation details
   - `/Users/olofs_mba/Documents/Repos/huledu-reboot/documentation/TASKS/VALIDATION_ISSUES_CATALOG.md` - Known issues and root causes

### **Step 2: ULTRATHINK Agent Deployment**

Deploy agents systematically based on task requirements:

#### **Agent Alpha: Task Analysis & Planning**
- Analyze user requirements and map to architectural patterns
- Identify relevant rules and standards from 000-rule-index.mdc
- Create detailed implementation plan with validation criteria
- Determine required agents for execution

#### **Agent Beta: Code Implementation & Quality**
- Execute implementation following established patterns
- Apply Rule 055 import patterns and Rule 050 coding standards
- Ensure compliance with Rule 048 error handling standards
- Maintain libs/ directory structure and src layout patterns

#### **Agent Charlie: Testing & Validation**
- Apply Rule 070 testing standards with protocol-based mocking
- Run targeted test suites (avoid `pdm run test-all` unless explicitly needed)
- Validate import resolution and code quality standards
- Ensure no regressions in 153-test baseline

#### **Agent Delta: Documentation & Standards**
- Update documentation per Rule 090 standards
- Maintain architectural documentation accuracy
- Ensure Rule 999 compliance for any rule updates
- Document lessons learned and process improvements

#### **Agent Echo: Integration & Deployment**
- Validate Docker builds and container functionality
- Test event-driven architecture and service communication
- Verify observability stack integration
- Confirm production readiness

### **Step 3: Current Platform Status**

#### **Validated Architecture**
```
libs/
├── common_core/src/common_core/          # 135/135 tests ✅
└── huleedu_service_libs/src/huleedu_service_libs/  # 18/18 tests ✅

services/
├── [11 services]                         # All operational ✅
└── [Docker builds successful]            # Production ready ✅
```

#### **Known Technical Debt** (from VALIDATION_ISSUES_CATALOG.md)
- **Critical (1)**: essay_lifecycle_service database_url attribute mismatch
- **Medium (49)**: Missing type annotations in test files
- **Low (12)**: Linting/formatting issues

## IMPLEMENTATION REQUIREMENTS

### **Critical Standards Compliance**

1. **Rule 020 Compliance**: All implementations must maintain DDD boundaries and service autonomy
2. **Rule 055 Compliance**: Use full module path imports for all service code
3. **Import Pattern**: `from services.service_name.module import Class` (never relative)
4. **Library Access**: `from common_core import ...` and `from huleedu_service_libs import ...`
5. **Error Handling**: Follow Rule 048 structured error handling with observability integration

### **Development Workflow**

1. **PDM Commands**: All local execution via `pdm run ...`
2. **Docker Rebuilds**: Use `docker compose build --no-cache [service]` for code changes
3. **Testing Scope**: Target specific test suites, not `pdm run test-all`
4. **Code Quality**: Run `pdm run lint-all` and `pdm run typecheck-all` for validation

### **Quality Gates**

- All tests maintain 153/153 baseline (153 total: 135 common_core + 18 huleedu_service_libs)
- Docker builds successful for affected services
- Import resolution 100% compatible
- Rule compliance verified via systematic checks

## AGENT INSTRUCTIONS

### **Agent Deployment Pattern**

1. **Start with Agent Alpha** for task analysis and planning
2. **Deploy Agent Beta** for implementation work  
3. **Use Agent Charlie** for testing and validation
4. **Engage Agent Delta** for documentation updates
5. **Conclude with Agent Echo** for integration validation

### **Agent Communication Protocol**

Each agent MUST:
- Reference specific rules and patterns from 000-rule-index.mdc
- Report completion status and validation results
- Document any issues or deviations discovered
- Provide specific recommendations for follow-up actions

### **Success Criteria Validation**

- ✅ All rule compliance maintained (Rules 010, 020, 048, 050, 055, 070)
- ✅ Test baseline preserved (153/153 tests passing)
- ✅ Docker functionality verified
- ✅ Import patterns correct
- ✅ Documentation current
- ✅ No architectural regressions

## IMMEDIATE CONTEXT

### **Platform Status**
- **Branch**: feature/library-restructure (or main)
- **Services**: 11 operational with health checks passing
- **Infrastructure**: Kafka (31 topics), PostgreSQL (6 databases), Redis, Observability stack
- **Code Quality**: 85% compliance (61 minor issues catalogued)

### **Key Lessons from Migration**
- Package-based imports enable transparent structural changes
- src layout consistency critical for PDM resolution
- `pdm lock` required before `pdm install` after path changes
- Protocol-based DI patterns unaffected by library restructuring

### **Development Priorities** (from CLAUDE.local.md)
- Error handling standardization (error_detail vs error_message)
- Code quality improvements addressing 61 identified issues
- System hardening and production optimization
- Clean architectural evolution

## EXECUTION GUIDANCE

Begin by deploying TodoWrite to track task progress, then systematically work through the ULTRATHINK agent framework. Focus on maintaining the architectural excellence achieved through migration while advancing platform capabilities according to user requirements.

**Remember**: The platform architecture is production-ready. All development must preserve this standard while delivering requested functionality with zero tolerance for architectural degradation.

**Current Working Directory**: `/Users/olofs_mba/Documents/Repos/huledu-reboot`
**Git Status**: Clean working tree with libs/ directory structure validated
**Test Baseline**: 153/153 tests passing across all core libraries