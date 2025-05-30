# HuleEdu Spell Checker Service

## **Service Purpose**

The Spell Checker Service is a Kafka consumer worker service responsible for applying advanced spell checking to individual essays in the HuleEdu processing pipeline. It operates within the **Text Processing** bounded context and provides L2 (Second Language) error correction combined with standard spell checking using `pyspellchecker`.

## **Key Domain Entities**

* **Essay Text Content**: Individual essay text requiring spell checking.
* **L2 Error Dictionary**: Curated Swedish L2 learner error corrections.
* **Spell Correction Results**: Detailed correction information and corrected text.

## **Architecture**

### **Service Type**

* **Worker Service**: Kafka consumer with no HTTP API.
* **Technology**: `aiokafka`, `aiohttp`, `pyspellchecker`, Python `asyncio`.
* **Dependency Injection**: Dishka with protocol-based abstractions defined in `protocols.py`.

### **Internal Structure**

The service follows a clean architecture pattern with clear separation of concerns:

* **`worker_main.py`**: Handles the service lifecycle (startup, shutdown), Kafka client management (consumer/producer), signal handling, and the primary message consumption loop. Initializes and manages the Dishka DI container.
* **`event_processor.py`**: Contains `process_single_message()` which handles incoming `ConsumerRecord` objects. It deserializes the `EventEnvelope[SpellcheckRequestedDataV1]`, then orchestrates the fetch-spellcheck-store-publish flow by calling appropriate protocol methods. **Clean Architecture**: Depends ONLY on injected protocol interfaces.
* **`protocols.py`**: Defines `typing.Protocol` interfaces for internal dependencies like content fetching, spell checking logic, result storage, and event publishing.
* **`core_logic.py`**: Provides the fundamental, reusable business logic functions:
  * `default_fetch_content_impl()`: Fetches content via HTTP from the Content Service.
  * `default_store_content_impl()`: Stores content via HTTP to the Content Service.
  * `default_perform_spell_check_algorithm()`: The core spell check logic, implementing the L2 + `pyspellchecker` pipeline.
* **`di.py`**: Contains the Dishka `Provider` (`SpellCheckerServiceProvider`) for setting up and providing dependencies. Imports implementations from `protocol_implementations/`.
* **`protocol_implementations/`**: Directory containing canonical protocol implementations:
  * **`content_client_impl.py`**: HTTP content fetching with constructor-injected dependencies
  * **`result_store_impl.py`**: HTTP content storage with constructor-injected dependencies
  * **`spell_logic_impl.py`**: Spell checking orchestration using `core_logic` functions
  * **`event_publisher_impl.py`**: Kafka event publishing with constructor-injected producer
* **`spell_logic/`**: Sub-package containing modules for L2 dictionary loading (`l2_dictionary_loader.py`), L2 filtering (`l2_filter.py`), and correction logging (`correction_logger.py`).

### **Processing Pipeline**

1. **L2 Pre-correction**: Apply curated Swedish L2 learner error corrections from a filtered dictionary.
2. **`pyspellchecker`**: Standard spell checking using `pyspellchecker` library.
3. **Correction Logging**: Detailed correction analysis and reporting if enabled.
4. **Result Storage**: Store corrected text via Content Service.

## **Events**

### **Consumes**

* **Event Type**: `huleedu.essay.spellcheck.requested.v1`
  * **Topic**: Dynamically determined by `topic_name(ProcessingEvent.ESSAY_SPELLCHECK_REQUESTED)`.
  * **Data Model**: `EventEnvelope[SpellcheckRequestedDataV1]`.
  * Contains essay entity reference and text storage ID.
  * Triggers the spell checking workflow.

### **Produces**

* **Event Type String in Envelope**: `huleedu.spellchecker.essay.concluded.v1` (defined as `KAFKA_EVENT_TYPE_SPELLCHECK_COMPLETED` in `event_processor.py`).
  * **Topic**: Dynamically determined by `topic_name(ProcessingEvent.ESSAY_SPELLCHECK_RESULT_RECEIVED)`.
  * **Data Model**: `EventEnvelope[SpellcheckResultDataV1]`.
  * Contains correction results and storage references.

### **Consumer Group**

* `spellchecker-service-group-v1.1` (configurable via `CONSUMER_GROUP` setting).

## **Key Features**

### **L2 Error Correction System**

* **Swedish L2 Learner Errors**: Curated dictionary of common second-language errors.
* **Advanced Filtering**: Removes unwanted corrections (pluralization, short words) via `spell_logic/l2_filter.py`.
* **Case Preservation**: Maintains original capitalization patterns during L2 application.
* **Position Tracking**: Accurate character-level correction mapping.

### **`pyspellchecker` Integration**

* **Multi-language Support**: Configurable language models (English default).
* **Word Tokenization**: Advanced regex-based word boundary detection.
* **Hyphenated Words**: Proper handling of contractions and hyphenated words.

### **Correction Logging**

* **Detailed Analysis**: Multi-stage correction tracking (L2 → `pyspellchecker`) via `spell_logic/correction_logger.py`.
* **Diff Generation**: Before/after text comparison.
* **Correction Statistics**: Count and categorization of corrections made.

## **Configuration**

Configuration is managed via `config.py` using `pydantic-settings`, loading from environment variables and `.env` files. All environment variables should be prefixed with `SPELL_CHECKER_SERVICE_`.

### **Core Service Settings**

* `SPELL_CHECKER_SERVICE_LOG_LEVEL`: Logging level (default: INFO).
* `SPELL_CHECKER_SERVICE_ENVIRONMENT`: Environment mode (default: development).
* `SPELL_CHECKER_SERVICE_KAFKA_BOOTSTRAP_SERVERS`: Kafka servers (default: kafka:9092).
* `SPELL_CHECKER_SERVICE_CONSUMER_GROUP`: Kafka consumer group ID.
* `SPELL_CHECKER_SERVICE_PRODUCER_CLIENT_ID`: Kafka producer client ID.
* `SPELL_CHECKER_SERVICE_CONSUMER_CLIENT_ID`: Kafka consumer client ID.

### **Content Service Integration**

* `SPELL_CHECKER_SERVICE_CONTENT_SERVICE_URL`: Content Service API URL.

### **L2 Correction Settings**

* `SPELL_CHECKER_SERVICE_ENABLE_L2_CORRECTIONS`: Enable/disable L2 corrections (default: true).
* `SPELL_CHECKER_SERVICE_L2_MASTER_DICT_PATH`: Path to the master L2 dictionary.
* `SPELL_CHECKER_SERVICE_L2_FILTERED_DICT_PATH`: Path to the filtered L2 dictionary used in production.
* `SPELL_CHECKER_SERVICE_L2_DATA_DIR`: Base directory for L2 data.
* `SPELL_CHECKER_SERVICE_L2_EXTERNAL_DATA_PATH`: Override for mounted dictionary volumes in containers.

### **Spell Checker Settings**

* `SPELL_CHECKER_SERVICE_DEFAULT_LANGUAGE`: `pyspellchecker` language (default: en).
* `SPELL_CHECKER_SERVICE_ENABLE_CORRECTION_LOGGING`: Enable/disable detailed correction logging (default: true).
* `SPELL_CHECKER_SERVICE_CORRECTION_LOG_OUTPUT_DIR`: Directory for saving correction logs.

### **Data Files**

The service expects L2 dictionary data to be available. Default paths are relative to the service's root directory (e.g., `data/l2_error_dict/`).

* `data/l2_error_dict/nortvig_master_SWE_L2_corrections.txt`: Full L2 error dictionary.
* `data/l2_error_dict/filtered_l2_dictionary.txt`: Filtered, production-ready corrections loaded by default.

## **Local Development**

### **Prerequisites**

* Python 3.11+
* PDM package manager
* Access to HuleEdu monorepo and running Kafka & Content Service instances.

### **Setup & Running**

1. **Install Dependencies** (from repository root):

    ```bash
    pdm install
    ```

2. **Configure Environment**:
    Create a `.env` file in the `services/spell_checker_service/` directory with necessary configurations (see example below or `config.py` for all options).
    Example `.env`:

    ```env
    SPELL_CHECKER_SERVICE_LOG_LEVEL=DEBUG
    SPELL_CHECKER_SERVICE_KAFKA_BOOTSTRAP_SERVERS=localhost:9093 # Adjust if your Kafka is elsewhere
    SPELL_CHECKER_SERVICE_CONTENT_SERVICE_URL=http://localhost:8001/v1/content # Adjust port for content_service
    ```

3. **Run the Worker**:
    From the `services/spell_checker_service/` directory:

    ```bash
    pdm run start_worker
    ```

    Or from the monorepo root:

    ```bash
    pdm run run-spellchecker
    ```

    (The PDM script `run-spellchecker` in the root `pyproject.toml` is `pdm run -p services/spell_checker_service start_worker`). The service's local `pyproject.toml` maps `start_worker` to `python worker_main.py`.

## **Testing**

### **Run Tests**

* **All service tests** (from monorepo root):

    ```bash
    pdm run pytest services/spell_checker_service/tests/ -v
    ```

* **Core logic integration tests only** (from monorepo root):

    ```bash
    pdm run pytest services/spell_checker_service/tests/spell_logic/test_core_logic_integration.py -v
    ```

* **With coverage** (from monorepo root):

    ```bash
    pdm run pytest services/spell_checker_service/tests/ --cov=services.spell_checker_service
    ```

### **Test Coverage**

* **Core Spell Logic (`spell_logic/`)**: L2 corrections, L2 filtering, `pyspellchecker` integration, and core algorithm (`default_perform_spell_check_algorithm`).
* **Event Processing (`event_processor.py`)**: Kafka message handling, protocol compliance with mocked dependencies.
* **Contract Compliance (`test_contract_compliance.py`)**: Ensures published events adhere to Pydantic schemas and correlation IDs are propagated.
* **Error Handling**: Tests for network failures, invalid input, and internal spell checker errors.

## **Service Dependencies**

### **Required Services**

* **Kafka**: Event streaming platform for message processing.
* **Content Service**: For fetching original essay text and storing corrected text.

## **Deployment**

### **Docker**

The service is containerized using the `services/spell_checker_service/Dockerfile`.
The Docker image is built and run as part of the `docker-compose.yml` setup.

* Build command (via PDM from root): `pdm run docker-build`
* Run command (via PDM from root): `pdm run docker-up`

## **Recent Updates**

* **Refactoring (Phase 1.2 Δ-3)**: The original `worker.py` has been refactored into `worker_main.py`, `event_processor.py`, and `core_logic.py` to improve modularity and adhere to file size limits.
* **DI with Dishka (Phase 1.2 Δ-2)**: The service now uses Dishka for dependency injection, with providers defined in `di.py` and behavioral contracts in `protocols.py`.
* **Full Spell Check Pipeline**: Integrated the L2 + `pyspellchecker` pipeline from the prototype into `core_logic.default_perform_spell_check_algorithm`.
* **Comprehensive Tests**: Migrated and updated tests for the core spell checking logic and event processing.
* **✅ Architectural Debt Remediation (2025-05-30)**: Completed major refactoring to eliminate SRP violations and implement clean architecture:
  * **Created `protocol_implementations/` directory** with canonical protocol implementations
  * **Replaced `event_router.py` with `event_processor.py`** for clean message processing
  * **Eliminated code duplication** between `di.py` and message processing
  * **Implemented proper dependency injection** with constructor injection patterns
  * **Maintained 100% test coverage** through all architectural changes
  * **All 71 tests pass** with the new clean architecture
