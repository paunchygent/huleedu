# CJ Assessment Service

## Overview

The CJ Assessment Service is a microservice dedicated to performing Comparative Judgment (CJ) assessment of essays using Large Language Model (LLM) based pairwise comparisons. The service consumes spellchecked essay texts and produces Bradley-Terry scores and rankings through iterative LLM-driven comparisons.

## Architecture

### Service Type

- **Pattern**: Kafka Worker Service (Event-Driven)
- **Framework**: Direct `asyncio` and `aiokafka` for message processing
- **Dependency Injection**: Dishka framework for clean architecture

### Key Internal Modules

- **`core_logic/`**: Core business logic package containing:
  - **`core_assessment_logic.py`**: Orchestrates the complete CJ workflow from request processing to result publication
  - **`pair_generation.py`**: Generates comparison tasks for iterative CJ assessment
  - **`scoring_ranking.py`**: Handles Bradley-Terry scoring using the `choix` library and ranking calculations
- **`protocols.py`**: Defines behavioral contracts using `typing.Protocol` for all major dependencies
- **`implementations/`**: Concrete implementations of all protocols (database, LLM providers, event publishing, content fetching)
- **`event_processor.py`**: Processes individual Kafka messages and delegates to core workflow
- **`worker_main.py`**: Service lifecycle management, DI container setup, Kafka consumer loop

### Dependencies

- **Content Service**: HTTP client for fetching spellchecked essay content
- **LLM Providers**: Multiple provider support (OpenAI, Anthropic, Google, OpenRouter)
- **Database**: SQLite with async SQLAlchemy for CJ-specific data persistence
- **Kafka**: Event consumption and publishing via EventEnvelope pattern

## Event Architecture

### Events Consumed

- **`ELS_CJAssessmentRequestV1`**: Incoming requests from Essay Lifecycle Service containing:
  - BOS batch reference (`entity_ref`)
  - List of essays for CJ assessment (`essays_for_cj`)
  - Assessment metadata (language, course_code, essay_instructions)

### Events Produced

- **`CJAssessmentCompletedV1`**: Successful completion events containing:
  - Final essay rankings with Bradley-Terry scores
  - CJ assessment job reference
  - Processing metadata (total comparisons, convergence status)

- **`CJAssessmentFailedV1`**: Failure events with error information and context

## Configuration

### Key Environment Variables (prefix: `CJ_ASSESSMENT_SERVICE_`)

```bash
# Kafka Configuration
KAFKA_BOOTSTRAP_SERVERS=localhost:9092
CJ_ASSESSMENT_REQUEST_TOPIC=huleedu.els.cj_assessment.requested.v1
CJ_ASSESSMENT_COMPLETED_TOPIC=huleedu.cj_assessment.completed.v1
CJ_ASSESSMENT_FAILED_TOPIC=huleedu.cj_assessment.failed.v1

# External Services
CONTENT_SERVICE_URL=http://localhost:8002
DATABASE_URL_CJ=sqlite+aiosqlite:///./cj_assessment.db

# LLM Provider API Keys
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_API_KEY=...

# CJ Assessment Parameters
MAX_PAIRWISE_COMPARISONS=1000
SCORE_STABILITY_THRESHOLD=0.05
COMPARISONS_PER_STABILITY_CHECK_ITERATION=10

# Observability
METRICS_PORT=9090
LOG_LEVEL=INFO
```

## Database Schema

### Core Tables

#### `cj_batch_uploads`

- **Purpose**: Tracks CJ assessment batches linked to BOS batches
- **Key Fields**:
  - `id` (int, PK): Internal CJ batch identifier
  - `bos_batch_id` (str): Reference to originating BOS batch
  - `status` (enum): Current processing state
  - `expected_essay_count` (int): Number of essays to process

#### `cj_processed_essays`

- **Purpose**: Individual essays prepared for CJ assessment
- **Key Fields**:
  - `els_essay_id` (str, PK): ELS essay identifier (string UUID)
  - `cj_batch_id` (int, FK): Reference to CJ batch
  - `assessment_input_text` (text): Spellchecked essay content
  - `current_bt_score` (float): Bradley-Terry score from comparisons

#### `cj_comparison_pairs`

- **Purpose**: Records of LLM-based pairwise comparisons
- **Key Fields**:
  - `essay_a_els_id` (str, FK): First essay in comparison
  - `essay_b_els_id` (str, FK): Second essay in comparison  
  - `winner` (str): Comparison result ("essay_a", "essay_b", "error")
  - `confidence` (float): LLM confidence rating (1-5)
  - `from_cache` (bool): Whether result came from cache

## Local Development

### Prerequisites

- Python 3.11+
- PDM for dependency management
- Kafka cluster (or Docker Compose setup)
- Access to Content Service

### Setup

```bash
# Install dependencies
pdm install

# Set up environment
cp .env.example .env
# Edit .env with your configuration

# Run the worker
pdm run start_worker
```

### Testing

```bash
# Run unit tests
pdm run pytest

# Run tests with coverage
pdm run pytest --cov=. --cov-report=html

# Run specific test modules
pdm run pytest tests/test_core_assessment_logic.py -v
```

### Development Workflow

1. **Protocol-First Development**: Define behavioral contracts in `protocols.py`
2. **Implementation**: Create concrete implementations in `implementations/`
3. **Dependency Injection**: Wire dependencies in `di.py`
4. **Testing**: Mock protocols for isolated unit testing

### Key Development Commands

```bash
# Format code
pdm run ruff format .

# Lint code
pdm run ruff check .

# Type checking
pdm run mypy .

# Run worker locally
pdm run python worker_main.py
```

## Monitoring and Observability

- **Metrics**: Prometheus metrics exposed on port 9090
- **Logging**: Structured logging via `huleedu_service_libs.logging_utils`
- **Health Checks**: Database connectivity and Kafka producer health
- **Correlation IDs**: Full request tracing across service boundaries

## Integration Points

### Upstream Dependencies

- **Essay Lifecycle Service**: Publishes CJ assessment requests
- **Content Service**: Provides spellchecked essay content via HTTP

### Downstream Consumers

- **Batch Orchestrator Service**: Consumes completion/failure events
- **Future Query Services**: Can use `cj_assessment_job_id` for detailed result queries

## Future Enhancements

- **HTTP Query API**: RESTful interface for CJ result queries
- **Advanced Scoring Models**: Beyond Bradley-Terry (e.g., Plackett-Luce)
- **Multi-Language Support**: Localized assessment prompts
- **Real-time Progress**: WebSocket updates for long-running assessments
