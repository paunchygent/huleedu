# Spell Checker Service Migration Plan

## **Overview**

This document outlines the migration of the proven spell checker prototype (`spell_checker/`) into the service framework (`services/spell_checker_service/`). The goal is to integrate the robust, tested spell checking logic from the prototype while maintaining the event-driven, batch-centric architecture.

## **Current State Analysis**

### **✅ Prototype Implementation (`spell_checker/`)**

- **Complete L2 error correction system** with filtering and validation
- **Pyspellchecker integration** replacing Spark NLP
- **Comprehensive test suite** covering core functionality  
- **Advanced correction logging** for debugging and analysis
- **CLI-based orchestration** via `spell_check_pipeline.py`

### **✅ Service Framework (`services/spell_checker_service/`)**

- **Event-driven architecture** with Kafka integration
- **Dependency injection** using Dishka
- **Protocol-based abstractions** for testability
- **Structured logging** with huleedu-service-libs
- **Stub implementations** waiting for real spell checking logic

## **Migration Strategy**

### **Phase 1: Core Logic Integration** ✅ **COMPLETED**

**Goal**: Replace stub spell checking algorithm with prototype implementation

#### **✅ 1.1. Move Core Spell Checking Modules** _(DONE 2025-05-28)_

- ✅ Copied `l2_dictionary_loader.py` → `services/spell_checker_service/spell_logic/l2_dictionary_loader.py`
- ✅ Copied `l2_filter.py` → `services/spell_checker_service/spell_logic/l2_filter.py`  
- ✅ Copied `correction_logger_util.py` → `services/spell_checker_service/spell_logic/correction_logger.py`
- ✅ Copied L2 error dictionaries to `services/spell_checker_service/data/l2_error_dict/`
- ✅ Updated all logging to use service framework (`create_service_logger` instead of `loguru`)
- ✅ Organized business logic in proper `spell_logic/` subfolder structure

#### **✅ 1.2. Update Core Logic Implementation** _(DONE 2025-05-28)_

**✅ Replaced**: `services/spell_checker_service/core_logic.py::default_perform_spell_check_algorithm()`

**✅ From**: Simple dummy replacements (`"teh" → "the"`)
**✅ To**: Full pipeline implementation with L2 + pyspellchecker

```python
async def default_perform_spell_check_algorithm(
    text: str, 
    essay_id: Optional[str] = None,
    language: str = "en"
) -> Tuple[str, int]:
    """
    Complete spell check pipeline using L2 corrections + pyspellchecker.
    
    Pipeline:
    1. Load/filter L2 error dictionary
    2. Apply L2 corrections to input text  
    3. Run pyspellchecker on L2-corrected text
    4. Log detailed correction information
    5. Return final corrected text + correction count
    """
```

**✅ Verification**: All core logic tests passing (5/5). Real spell checking working:
- "teh" → "the", "recieve" → "receive", "tset" → "set" 
- 3 corrections made vs. 2 expected from dummy implementation

#### **✅ 1.3. Integration Requirements** _(DONE 2025-05-28)_

- ✅ **Configuration**: Added L2 dictionary paths and spell checker settings to `config.py`
- ✅ **Dependencies**: Added `pyspellchecker` to service `pyproject.toml` (following PDM standards)
- ✅ **Logging**: Integrated correction logging with service logger framework
- ✅ **Error Handling**: All operations wrapped in try/catch with proper error reporting
- ✅ **Service Framework**: Maintained full architectural compliance (DI, protocols, async patterns)

**Phase 1 Status**: ✅ **COMPLETE** - Core spell checking logic successfully migrated and functional

### **Phase 2: Service Framework Adaptation** 📋

**Goal**: Adapt prototype logic to work within service architecture

#### **2.1. Protocol Compliance**

- Ensure `SpellLogicProtocol::perform_spell_check()` calls new implementation
- Update `DefaultSpellLogic` to use integrated pipeline
- Maintain existing return type (`SpellcheckResultDataV1`)

#### **2.2. Dependency Management**

- Add L2 correction dependencies to DI container
- Create providers for L2 dictionary loader and filter
- Ensure proper cleanup of resources (dictionaries, temp files)

#### **2.3. Configuration Externalization**

- Move hardcoded paths from prototype to settings
- Support different languages via configuration
- Enable/disable L2 corrections via feature flags

### **Phase 3: Testing Migration** 🧪

**Goal**: Migrate and adapt comprehensive test suite

#### **3.1. Test File Migration**

- Copy `spell_checker/tests/test_l2_dictionary_loader.py` → `services/spell_checker_service/tests/`
- Copy `spell_checker/tests/test_l2_filter.py` → `services/spell_checker_service/tests/`
- Copy `spell_checker/tests/test_spell_check_pipeline.py` → `services/spell_checker_service/tests/test_core_logic_integration.py`

#### **3.2. Test Adaptation**

- Update imports to use service modules
- Adapt CLI-based tests to service context
- Integrate with existing service test fixtures
- Ensure all protocol implementations are tested

#### **3.3. Integration Testing**

- Test complete event processing flow (Kafka → spell check → result publishing)
- Verify L2 + pyspellchecker pipeline works in service context
- Test error handling and failure scenarios
- Performance testing with realistic essay volumes

### **Phase 4: Batch-Centric Integration** 🔗

**Goal**: Enable ELS → spell checker → ELS integration

#### **4.1. Event Handling**

- Update event router to process `EssayLifecycleSpellcheckRequestV1`
- Implement proper correlation ID propagation
- Handle batch context in logging and metrics

#### **4.2. Result Publishing**

- Ensure `SpellcheckResultDataV1` includes all required batch information
- Publish results to correct Kafka topics for ELS consumption
- Include storage references for corrected text

## **Detailed Implementation Instructions**

### **Step 1: Core Module Migration**

```bash
# Copy prototype modules to service
cp spell_checker/l2_dictionary_loader.py services/spell_checker_service/
cp spell_checker/l2_filter.py services/spell_checker_service/
cp spell_checker/correction_logger_util.py services/spell_checker_service/correction_logger.py

# Copy data files to service-local directory (service autonomy)
mkdir -p services/spell_checker_service/data/l2_error_dict
cp -r spell_checker/l2_error_dict/* services/spell_checker_service/data/l2_error_dict/
```

### **Step 2: Update Imports and Dependencies**

**services/spell_checker_service/pyproject.toml**:

```toml
dependencies = [
    # ... existing dependencies ...
    "pyspellchecker>=0.7.0",
]
```

**services/spell_checker_service/config.py**:

```python
class Settings(BaseSettings):
    # ... existing settings ...
    
    # L2 Correction Settings - Service-local paths for autonomy
    L2_MASTER_DICT_PATH: str = "./data/l2_error_dict/nortvig_master_SWE_L2_corrections.txt"
    L2_FILTERED_DICT_PATH: str = "./data/l2_error_dict/filtered_l2_dictionary.txt"
    L2_DATA_DIR: str = "./data/l2_error_dict"  # Base directory for L2 data
    ENABLE_L2_CORRECTIONS: bool = True
    
    # Spell Checker Settings  
    DEFAULT_LANGUAGE: str = "en"
    ENABLE_CORRECTION_LOGGING: bool = True
    
    # Environment-specific overrides (for containerized deployments)
    L2_EXTERNAL_DATA_PATH: Optional[str] = None  # Override for mounted volumes
    
    @property
    def effective_l2_data_dir(self) -> str:
        """Get effective L2 data directory, supporting external mounts."""
        return self.L2_EXTERNAL_DATA_PATH or self.L2_DATA_DIR
    
    @property 
    def effective_master_dict_path(self) -> str:
        """Get effective master dictionary path."""
        if self.L2_EXTERNAL_DATA_PATH:
            return f"{self.L2_EXTERNAL_DATA_PATH}/nortvig_master_SWE_L2_corrections.txt"
        return self.L2_MASTER_DICT_PATH
        
    @property
    def effective_filtered_dict_path(self) -> str:
        """Get effective filtered dictionary path."""
        if self.L2_EXTERNAL_DATA_PATH:
            return f"{self.L2_EXTERNAL_DATA_PATH}/filtered_l2_dictionary.txt"  
        return self.L2_FILTERED_DICT_PATH
```

### **Step 3: Core Logic Replacement**

**services/spell_checker_service/core_logic.py**:

```python
from typing import Optional, Tuple
from .l2_dictionary_loader import load_l2_errors, apply_l2_corrections, create_filtered_l2_dictionary
from .correction_logger import log_essay_corrections
from .config import settings
from spellchecker import SpellChecker
import re

async def default_perform_spell_check_algorithm(
    text: str, 
    essay_id: Optional[str] = None,
    language: str = "en"
) -> Tuple[str, int]:
    """Complete L2 + pyspellchecker pipeline implementation."""
    
    # 1. Load L2 dictionaries using environment-aware configuration
    l2_errors = load_l2_errors(settings.effective_filtered_dict_path)
    
    # 2. Apply L2 corrections
    l2_corrected_text, l2_corrections = apply_l2_corrections(text, l2_errors)
    
    # 3. Initialize pyspellchecker
    spell_checker = SpellChecker(language=language)
    
    # 4. Apply pyspellchecker corrections
    final_text, pyspell_corrections = await _apply_pyspellchecker(
        l2_corrected_text, spell_checker
    )
    
    # 5. Log corrections (if enabled)
    if settings.ENABLE_CORRECTION_LOGGING and essay_id:
        await _log_corrections_async(
            essay_id, text, l2_corrected_text, final_text,
            l2_corrections, pyspell_corrections
        )
    
    total_corrections = len(l2_corrections) + len(pyspell_corrections)
    return final_text, total_corrections
```

### **Step 4: Test Migration**

```bash
# Copy test files
cp spell_checker/tests/test_l2_dictionary_loader.py services/spell_checker_service/tests/
cp spell_checker/tests/test_l2_filter.py services/spell_checker_service/tests/

# Update imports in test files
sed -i 's/from spell_checker.l2_dictionary_loader/from ..l2_dictionary_loader/g' services/spell_checker_service/tests/test_l2_*.py
sed -i 's/from spell_checker.l2_filter/from ..l2_filter/g' services/spell_checker_service/tests/test_l2_*.py
```

### **Step 5: Integration Testing**

**services/spell_checker_service/tests/test_integration.py**:

```python
@pytest.mark.asyncio
async def test_complete_spell_check_pipeline():
    """Test the complete L2 + pyspellchecker pipeline in service context."""
    
    # Test with real L2 errors and pyspellchecker corrections
    test_text = "This is a tset with commited errors and recieve mistakes."
    
    corrected_text, correction_count = await default_perform_spell_check_algorithm(
        test_text, essay_id="test-essay", language="en"
    )
    
    assert "test" in corrected_text  # L2 correction
    assert "committed" in corrected_text  # pyspellchecker correction  
    assert "receive" in corrected_text  # pyspellchecker correction
    assert correction_count >= 3
```

## **Data Placement Rationale**

### **Why Service-Local Data is Superior**

#### **🎯 Service Autonomy Principle**

```
services/spell_checker_service/     # ✅ Self-contained service
├── data/l2_error_dict/            # ✅ Service owns its data
│   ├── nortvig_master_SWE_L2_corrections.txt
│   └── filtered_l2_dictionary.txt
├── core_logic.py                  # ✅ Uses local data
├── config.py                      # ✅ Configurable paths
└── Dockerfile                     # ✅ COPY data/ /app/data/
```

**Benefits:**

- **Independent Deployment**: Service can be deployed without monorepo dependencies
- **Clear Ownership**: Spell checker team owns and maintains L2 dictionaries
- **Version Independence**: Dictionary updates don't affect other services
- **Container Self-Sufficiency**: Docker images are complete and portable

#### **🔧 Configuration Flexibility**

```python
# Development: Use service-local data
L2_EXTERNAL_DATA_PATH=None  # Uses ./data/l2_error_dict/

# Production: Use mounted volume
L2_EXTERNAL_DATA_PATH=/mnt/shared/l2_data/

# Testing: Use test-specific data
L2_EXTERNAL_DATA_PATH=/tmp/test_l2_data/
```

#### **📦 Docker Strategy**

```dockerfile
# Dockerfile for spell_checker_service
FROM python:3.11
WORKDIR /app

# Copy service code
COPY . /app/

# Copy L2 data (service-local)
COPY data/ /app/data/

# Service is self-contained
CMD ["python", "worker_main.py"]
```

### **Future Scalability Considerations**

#### **When to Reconsider Data Placement**

**Keep Service-Local When:**

- Only spell checker service uses L2 dictionaries
- Dictionary updates are infrequent
- Dictionary size is manageable (<100MB)
- Team ownership is clear

**Consider Shared Storage When:**

- **Multiple services** need L2 dictionaries (e.g., grammar checker, text preprocessor)
- **Dictionary size** exceeds container size limits (>500MB)
- **Frequent updates** require coordinated rollouts across services
- **Regulatory requirements** mandate centralized data management

#### **Migration Path to Shared Storage**

```python
# Phase 1: Service-local (current)
L2_DATA_SOURCE: str = "local"  # Uses ./data/l2_error_dict/

# Phase 2: Shared volume mount 
L2_DATA_SOURCE: str = "volume"  # Uses mounted /mnt/shared/l2_data/

# Phase 3: External service
L2_DATA_SOURCE: str = "service"  # HTTP calls to L2 Dictionary Service
L2_SERVICE_URL: str = "http://l2-dictionary-service:8000"
```

#### **Shared Storage Options (Future)**

1. **Shared Volume Mount**: Multiple services mount same volume
2. **L2 Dictionary Service**: Dedicated microservice for L2 data
3. **Content Service Extension**: Add L2 endpoints to existing content service
4. **Configuration Service**: Store L2 data as configuration

**Current Recommendation**: Start with service-local, migrate only when proven necessary.

## **Success Criteria**

### **Functional Requirements** ✅

- [ ] L2 error correction pipeline fully integrated
- [ ] Pyspellchecker working in service context
- [ ] All existing service tests pass
- [ ] Migrated tests pass with >95% coverage
- [ ] Correction logging functional
- [ ] Error handling comprehensive

### **Performance Requirements** ⚡

- [ ] Service startup time <5 seconds
- [ ] Essay processing time <2 seconds per essay
- [ ] Memory usage stable under load
- [ ] No memory leaks in L2 dictionary loading

### **Integration Requirements** 🔗

- [ ] Kafka event processing working
- [ ] Proper error event publishing
- [ ] Correlation ID propagation
- [ ] Storage service integration

## **Risk Mitigation**

### **Compatibility Risks**

- **Risk**: Prototype dependencies conflict with service dependencies
- **Mitigation**: Comprehensive dependency testing, version pinning

### **Performance Risks**  

- **Risk**: L2 dictionary loading slows down service startup
- **Mitigation**: Implement dictionary caching, lazy loading

### **Data Risks**

- **Risk**: L2 dictionary paths not found in service context
- **Mitigation**: Relative path resolution, environment-specific configuration

## **Timeline Estimation**

- **Phase 1 (Core Logic)**: 2-3 days
- **Phase 2 (Service Adaptation)**: 1-2 days  
- **Phase 3 (Testing)**: 2-3 days
- **Phase 4 (Integration)**: 1-2 days

**Total Estimated Time**: 6-10 days

## **Next Steps**

1. **Start Phase 1**: Begin core module migration
2. **Run tests early**: Verify prototype tests pass in new location
3. **Incremental testing**: Test each component as it's migrated
4. **Integration testing**: Validate complete pipeline before batch integration
5. **Performance testing**: Ensure service performance meets requirements

---

**This migration will provide the spell checker service with proven, production-ready spell checking capabilities while maintaining the benefits of the event-driven service architecture.**
