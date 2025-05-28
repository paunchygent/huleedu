# HuleEdu Common Core (`huleedu-common-core`)

## 🎯 Purpose

The **HuleEdu Common Core** package is the central repository for shared data contracts, enumerations, and essential metadata models utilized across all microservices within the HuleEdu ecosystem. Its primary objective is to establish consistency, type safety, and clear communication interfaces between these services.

Centralizing these common definitions helps to:

* Prevent data contract inconsistencies between services.
* Promote reuse of shared data structures.
* Simplify integration and inter-service communication.
* Provide a stable foundation for the event-driven architecture.

## 📦 Package Contents

This package primarily includes:

* **Pydantic Models**:
  * **Event Payloads**: Defines the structure for data within events (e.g., `SpellcheckRequestedDataV1`, `SpellcheckResultDataV1`). These are utilized by the `EventEnvelope`.
  * **Command/Request Models**: Specifies structures for commands and requests between services, such as those from orchestrators to specialized services (e.g., `BatchServiceSpellcheckInitiateCommandDataV1`, `EssayLifecycleSpellcheckRequestV1`).
* **Shared Enumerations (`enums.py`)**:
  * Provides centralized definitions for system-wide statuses (e.g., `EssayStatus`, `BatchStatus`, `ProcessingStage`), event types (`ProcessingEvent`), content types (`ContentType`), and error codes (`ErrorCode`).
  * Includes the `topic_name()` utility for consistent derivation of Kafka topic names from `ProcessingEvent` enums.
* **Standardized Event Structure (`events/envelope.py`)**:
  * Features the `EventEnvelope`, a generic Pydantic model that wraps all event data. This ensures consistent metadata fields such as `event_id`, `event_type`, `event_timestamp`, `source_service`, `correlation_id`, and `schema_version`.
* **Metadata Models (`metadata_models.py`)**:
  * Contains common structures for `EntityReference`, `SystemProcessingMetadata`, `StorageReferenceMetadata`, and other cross-cutting metadata.
* **Pipeline Models (`pipeline_models.py`)**:
  * Includes models like `ProcessingPipelineState` and `PipelineStateDetail` for representing the state and progress of multi-step processing pipelines.

## 🧱 Structure

The source code for `common_core` is organized as follows:

```

common_core/
├── pyproject.toml         # Package definition and dependencies
├── README.md              # This file
└── src/
    └── common_core/
        ├── __init__.py    # Exports key components; handles model rebuilding
        ├── enums.py       # Shared enumerations
        ├── metadata_models.py # Shared Pydantic models for metadata
        ├── pipeline_models.py # Models for processing pipeline state
        ├── batch_service_models.py  # Cmd models: Batch Orchestrator -> ELS
        ├── essay_service_models.py  # Req models: ELS -> Specialized Services
        ├── events/
        │   ├── __init__.py
        │   ├── envelope.py          # Definition of EventEnvelope
        │   ├── base_event_models.py # Base Pydantic models for event data
        │   ├── spellcheck_models.py # Event data for spell checking
        │   └── ai_feedback_events.py# Event data for AI feedback
        └── py.typed           # PEP 561 marker for type checking support

```

This structure includes the package definition, this README, and the source directory (`src/common_core/`) which contains the core Python modules such as `enums.py`, `metadata_models.py`, the `events` subdirectory with `envelope.py` and specific event data models, and the `py.typed` marker file. The main `__init__.py` handles exports and model rebuilding.

## ⚙️ Usage by Services

All microservices within the HuleEdu monorepo depend on `common_core`. They import Pydantic models to:

* Serialize and deserialize event data for Kafka communication.
* Define request and response schemas for inter-service HTTP APIs where applicable.
* Utilize shared enumerations for consistent status codes, event types, etc.

In the development environment, services typically include `common_core` as an editable local path dependency, facilitating rapid iteration.

## ✨ Key Design Principles for `common_core`

* **Stability**: Changes to `common_core` models or enums can impact multiple services. Modifications are implemented carefully, often incorporating versioning for event models (e.g., `*.v1`, `*.v2` in event type strings).
* **Lightweight Dependencies**: Core definition files, particularly `enums.py`, are kept lightweight to minimize import overhead. The package primarily relies on `pydantic` and `typing-extensions`.
* **Clarity and Explicitness**: Models and enumerations are clearly named and fully type-hinted to enhance understanding and maintainability.
* **Type Safety**: The package is fully type-hinted and includes a `py.typed` marker file, enabling robust static type checking with MyPy across all consuming services.
* **Model Rebuilding**: The main `__init__.py` explicitly calls `model_rebuild(raise_errors=True)` on Pydantic models. This ensures that forward references (e.g., string type hints for enums or other models defined later in an import sequence) are correctly resolved when the package is imported.

## 🔧 Development and Maintenance

* When introducing new shared data structures or enums, their applicability across multiple services should be considered.
* Data structures highly specific to a single service's internal logic may be better suited within that service.
* After making changes to `common_core`, it's important to run linters and type checkers. Tests for `common_core` focus on model validation, serialization, and correct resolution of forward references.
* A wheel for `common_core` can be built using the PDM script `build-common-core` from the monorepo root, which executes `pdm build -p common_core`.

```
