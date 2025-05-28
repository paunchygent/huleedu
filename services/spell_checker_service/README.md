# HuleEdu Spell Checker Service

## **Service Purpose**

The Spell Checker Service is a Kafka consumer worker service responsible for applying advanced spell checking to individual essays in the HuleEdu processing pipeline. It operates within the **Text Processing** bounded context and provides L2 (Second Language) error correction combined with standard spell checking using pyspellchecker.

## **Key Domain Entities**

- **Essay Text Content**: Individual essay text requiring spell checking
- **L2 Error Dictionary**: Curated Swedish L2 learner error corrections  
- **Spell Correction Results**: Detailed correction information and corrected text

## **Architecture**

### **Service Type**

- **Worker Service**: Kafka consumer with no HTTP API
- **Technology**: aiokafka, aiohttp, pyspellchecker, Python asyncio
- **Dependency Injection**: Dishka with protocol-based abstractions

### **Processing Pipeline**

1. **L2 Pre-correction**: Apply curated Swedish L2 learner error corrections
2. **pyspellchecker**: Standard spell checking using Norvig algorithm
3. **Correction Logging**: Detailed correction analysis and reporting
4. **Result Storage**: Store corrected text via Content Service

## **Events**

### **Consumes**

- `essay.spellcheck.requested.v1` (`SpellcheckRequestedDataV1`)
  - Contains essay entity reference and text storage ID
  - Triggers spell checking workflow

### **Produces**  

- `essay.spellcheck.completed.v1` (`SpellcheckResultDataV1`)
  - Contains correction results and storage references
  - Sent back to Essay Lifecycle Service

### **Consumer Group**

- `spellchecker-service-group-v1.1`

## **Key Features**

### **L2 Error Correction System**

- **Swedish L2 Learner Errors**: Curated dictionary of common second-language errors
- **Advanced Filtering**: Removes unwanted corrections (pluralization, short words)
- **Case Preservation**: Maintains original capitalization patterns
- **Position Tracking**: Accurate character-level correction mapping

### **pyspellchecker Integration**

- **Multi-language Support**: Configurable language models (English default)
- **Norvig Algorithm**: Statistical spell correction with frequency-based suggestions
- **Word Tokenization**: Advanced regex-based word boundary detection
- **Hyphenated Words**: Proper handling of contractions and hyphenated words

### **Correction Logging**

- **Detailed Analysis**: Multi-stage correction tracking (L2 → pyspellchecker)
- **Diff Generation**: Before/after text comparison
- **Correction Statistics**: Count and categorization of corrections made

## **Configuration**

### **Environment Variables**

All configuration uses `SPELL_CHECKER_SERVICE_` prefix:

#### **Core Service Settings**

- `SPELL_CHECKER_SERVICE_LOG_LEVEL`: Logging level (default: INFO)
- `SPELL_CHECKER_SERVICE_ENVIRONMENT`: Environment mode (default: development)
- `SPELL_CHECKER_SERVICE_KAFKA_BOOTSTRAP_SERVERS`: Kafka servers (default: kafka:9092)

#### **Content Service Integration**

- `SPELL_CHECKER_SERVICE_CONTENT_SERVICE_URL`: Content Service API URL

#### **L2 Correction Settings**

- `SPELL_CHECKER_SERVICE_ENABLE_L2_CORRECTIONS`: Enable/disable L2 corrections (default: true)
- `SPELL_CHECKER_SERVICE_L2_EXTERNAL_DATA_PATH`: Override for mounted dictionary volumes

#### **Spell Checker Settings**

- `SPELL_CHECKER_SERVICE_DEFAULT_LANGUAGE`: pyspellchecker language (default: en)
- `SPELL_CHECKER_SERVICE_ENABLE_CORRECTION_LOGGING`: Detailed logging (default: true)

### **Data Files**

#### **Service-Local L2 Dictionaries**

- `data/l2_error_dict/nortvig_master_SWE_L2_corrections.txt`: Full L2 error dictionary
- `data/l2_error_dict/filtered_l2_dictionary.txt`: Filtered, production-ready corrections

## **Local Development**

### **Prerequisites**

- Python 3.11+
- PDM package manager
- Access to HuleEdu monorepo

### **Setup**

```bash
# Install dependencies (from repository root)
pdm install

# Run spell checker service
pdm run run-spellchecker

# Or run from service directory
cd services/spell_checker_service
pdm run start_worker
```

### **Environment Configuration**

Create `.env` file in service directory:

```bash
SPELL_CHECKER_SERVICE_LOG_LEVEL=DEBUG
SPELL_CHECKER_SERVICE_KAFKA_BOOTSTRAP_SERVERS=localhost:9092
SPELL_CHECKER_SERVICE_CONTENT_SERVICE_URL=http://localhost:8000/v1/content
```

## **Testing**

### **Run Tests**

```bash
# All spell checker service tests
pdm run pytest services/spell_checker_service/tests/ -v

# Core logic tests only
pdm run pytest services/spell_checker_service/tests/test_core_logic.py -v

# With coverage
pdm run pytest services/spell_checker_service/tests/ --cov=services.spell_checker_service
```

### **Test Coverage**

- **Core Logic**: L2 corrections, pyspellchecker integration, content fetching/storing
- **Event Processing**: Kafka message handling, protocol compliance  
- **Integration**: End-to-end spell checking workflow
- **Error Handling**: Network failures, invalid input, spell checker errors

### **Test Data**

- Service includes test L2 dictionaries for development
- Mock essay content for unit testing
- Integration tests with realistic spell checking scenarios

## **Service Dependencies**

### **Required Services**

- **Kafka**: Event streaming platform for message processing
- **Content Service**: Text storage and retrieval

### **Optional Services**  

- **Monitoring**: Prometheus metrics collection
- **Logging**: Centralized log aggregation

## **Deployment**

### **Docker**

```bash
# Build service image
docker build -t huleedu-spell-checker-service .

# Run with environment variables
docker run --env-file .env huleedu-spell-checker-service
```

### **Environment-Specific Configuration**

- **Development**: Local file paths, debug logging
- **Production**: Mounted volumes for L2 dictionaries, structured logging
- **Testing**: Mock services, isolated test data

## **Performance Characteristics**

### **Throughput**

- **L2 Corrections**: ~1000 corrections/second
- **pyspellchecker**: Language-dependent, typically 100-500 words/second
- **Memory Usage**: ~50MB base + dictionary caching

### **Scaling**

- **Horizontal**: Multiple consumer instances with same consumer group
- **Dictionary Caching**: In-memory L2 dictionary for performance
- **Language Models**: Lazy loading of pyspellchecker language data

## **Troubleshooting**

### **Common Issues**

#### **L2 Dictionary Not Found**

- Verify `data/l2_error_dict/` directory exists in service folder
- Check `L2_EXTERNAL_DATA_PATH` configuration for containerized deployments
- Ensure dictionary files have correct permissions

#### **pyspellchecker Language Errors**

- Verify language code is supported (en, es, fr, etc.)
- Check network connectivity for language model downloads
- Review logs for initialization errors

#### **Kafka Connection Issues**

- Verify `KAFKA_BOOTSTRAP_SERVERS` configuration
- Check network connectivity to Kafka cluster
- Review consumer group configuration

### **Debugging**

```bash
# Enable debug logging
export SPELL_CHECKER_SERVICE_LOG_LEVEL=DEBUG

# Run with detailed output
pdm run pytest services/spell_checker_service/tests/ -s -vv

# Test specific spell checking
python -c "
import asyncio
from services.spell_checker_service.core_logic import default_perform_spell_check_algorithm
result = asyncio.run(default_perform_spell_check_algorithm('test text with errrors'))
print(result)
"
```

## **Architecture Compliance**

### **Service Autonomy**

- ✅ Self-contained L2 dictionaries (no shared data dependencies)
- ✅ Independent deployment and scaling
- ✅ Service-specific configuration and data management

### **Event-Driven Communication**

- ✅ Kafka-based messaging with EventEnvelope standard
- ✅ Thin events with storage references (no large data in messages)
- ✅ Proper correlation ID propagation

### **Domain-Driven Design**

- ✅ Clear bounded context (Text Processing)
- ✅ Protocol-based dependency injection
- ✅ Explicit data contracts with Pydantic models

## **Recent Updates**

### **2025-05-28: Phase 1 Migration Complete**

- ✅ Migrated L2 + pyspellchecker implementation from prototype
- ✅ Replaced dummy spell checking algorithm with production-ready pipeline
- ✅ Updated business logic organization (spell_logic/ subfolder)
- ✅ All core logic tests passing with real spell checking verification
- ✅ Service framework integration maintained (DI, protocols, async patterns)
