# Epic: Pre-emptive Raw File Storage (PIPELINE_HARDENING_V1.1)

**Objective**: Refactor the File Service to persist the raw, unmodified file blob before any processing occurs. This establishes an immutable source of truth, enabling robust reprocessing and decoupling storage from interpretation.

---

## Task 2.1: Enhance `ContentType` Enum

**Motivation**: We must formalize the different types of content our system stores. Using a `ContentType` enum instead of "magic strings" like "raw_upload" makes the system's data contracts explicit, self-documenting, and type-safe.

- **File to Edit**: 📂 `common_core/src/common_core/enums.py`
- **Action**: Add `RAW_UPLOAD_BLOB` and `EXTRACTED_PLAINTEXT` to the `ContentType` enum. This clearly distinguishes between the original file and its processed text version.

```python
# common_core/src/common_core/enums.py

class ContentType(str, Enum):
    ORIGINAL_ESSAY = "original_essay"  # This may be deprecated in favor of the new, more specific types
    CORRECTED_TEXT = "corrected_text"
    PROCESSING_LOG = "processing_log"
    NLP_METRICS_JSON = "nlp_metrics_json"
    STUDENT_FACING_AI_FEEDBACK_TEXT = "student_facing_ai_feedback_text"
    AI_EDITOR_REVISION_TEXT = "ai_editor_revision_text"
    AI_DETAILED_ANALYSIS_JSON = "ai_detailed_analysis_json"
    GRAMMAR_ANALYSIS_JSON = "grammar_analysis_json"
    CJ_RESULTS_JSON = "cj_results_json"
    
    # ➕ ADD THESE NEW VARIANTS
    RAW_UPLOAD_BLOB = "raw_upload_blob"
    EXTRACTED_PLAINTEXT = "extracted_plaintext"
```

---

## Task 2.2: Update Event Contracts

**Motivation**: Downstream services need to know the location of the original, untouched file for traceability and potential reprocessing. Both success and failure events must carry this reference.

- **File to Edit**: 📂 `common_core/src/common_core/events/file_events.py`
- **Action**: Add the `raw_file_storage_id: str` field to the `EssayContentProvisionedV1` and `EssayValidationFailedV1` Pydantic models.

```python
# common_core/src/common_core/events/file_events.py

from pydantic import BaseModel, Field
# ... other imports

class EssayContentProvisionedV1(BaseModel):
    # ... existing fields (event, batch_id, original_file_name, etc.)
    
    # ➕ ADD THIS FIELD
    raw_file_storage_id: str = Field(
        description="Storage ID of the original, unmodified raw file blob."
    )
    
    # This field remains, but now specifically refers to the *processed* text
    text_storage_id: str = Field(
        description="Content Service storage ID for the extracted and validated text."
    )
    # ... other fields (file_size_bytes, etc.)


class EssayValidationFailedV1(BaseModel):
    # ... existing fields (event, batch_id, etc.)

    # ➕ ADD THIS FIELD (using a consistent name)
    raw_file_storage_id: str = Field(
        description="Storage ID of the raw file blob that failed validation."
    )
    
    validation_error_code: str
    # ... other fields
```

---

## Task 2.3: Update `ContentServiceClientProtocol`

**Motivation**: Before changing the implementation, the service's internal contract (the protocol) must be updated. This enforces a contract-first approach and ensures that any component depending on this protocol is aware of the change.

- **File to Edit**: 📂 `services/file_service/protocols.py`
- **Action**: Modify the `store_content` method signature to include the new `content_type` parameter.

```python
# services/file_service/protocols.py

from common_core.enums import ContentType # ➕ Import the enum
from typing import Protocol

class ContentServiceClientProtocol(Protocol):
    # 🔄 MODIFY THIS SIGNATURE
    async def store_content(self, content_bytes: bytes, content_type: ContentType) -> str:
        """
        Store content in Content Service and return storage ID.

        Args:
            content_bytes: Raw binary content to store.
            content_type: The type of content being stored (e.g., raw blob, extracted text).
        """
        ...
```

---

## Task 2.4: Refactor `core_logic.py` to Implement New Flow

**Motivation**: This is the core implementation change. The logic will now follow the robust "store raw first" pattern, ensuring the original artifact is always saved before any potentially fallible processing steps occur.

- **File to Edit**: 📂 `services/file_service/core_logic.py`
- **Action**: Replace the `process_single_file_upload` function with the new, refined logic.

```python
# services/file_service/core_logic.py

# ➕ Add new imports
import hashlib
from common_core.enums import ContentType
# ... other imports

# 🔄 Replace the entire function
async def process_single_file_upload(
    # ... function signature remains the same
    batch_id: str,
    file_content: bytes,
    file_name: str,
    main_correlation_id: uuid.UUID,
    text_extractor: TextExtractorProtocol,
    content_validator: ContentValidatorProtocol,
    content_client: ContentServiceClientProtocol,
    event_publisher: EventPublisherProtocol,
) -> dict:
    logger.info(f"Processing file {file_name} for batch {batch_id}")
    raw_storage_id = None
    try:
        # STEP 1: Store the raw, unmodified file blob first.
        raw_storage_id = await content_client.store_content(
            file_content, content_type=ContentType.RAW_UPLOAD_BLOB
        )
        logger.info(f"Stored raw file blob for {file_name}, raw_storage_id: {raw_storage_id}")

        # STEP 2: Extract text content.
        text = await text_extractor.extract_text(file_content, file_name)

        # STEP 3: Validate the extracted text.
        validation_result = await content_validator.validate_content(text, file_name)
        if not validation_result.is_valid:
            logger.warning(f"Content validation failed for {file_name}: {validation_result.error_message}")
            
            # STEP 3a: Publish a failure event, now including the raw_storage_id.
            failure_event = EssayValidationFailedV1(
                batch_id=batch_id,
                original_file_name=file_name,
                raw_file_storage_id=raw_storage_id, # Include the raw file reference
                validation_error_code=validation_result.error_code or "UNKNOWN_ERROR",
                # ... other fields
            )
            await event_publisher.publish_essay_validation_failed(failure_event, main_correlation_id)
            return {"status": "validation_failed", "raw_storage_id": raw_storage_id}

        # STEP 4: Store the processed (extracted) text.
        text_storage_id = await content_client.store_content(
            text.encode("utf-8"), content_type=ContentType.EXTRACTED_PLAINTEXT
        )
        logger.info(f"Stored extracted text for {file_name}, text_storage_id: {text_storage_id}")

        # STEP 5: Publish the success event with BOTH storage IDs.
        success_event = EssayContentProvisionedV1(
            batch_id=batch_id,
            original_file_name=file_name,
            raw_file_storage_id=raw_storage_id,
            text_storage_id=text_storage_id,
            file_size_bytes=len(file_content),
            content_md5_hash=hashlib.md5(file_content).hexdigest(),
            # ... other fields
        )
        await event_publisher.publish_essay_content_provisioned(success_event, main_correlation_id)

        return {
            "status": "processing_success",
            "raw_storage_id": raw_storage_id,
            "text_storage_id": text_storage_id,
        }
    except Exception as e:
        # ... (error handling logic remains similar but should also publish failure event with raw_id if available)
```

---

## Task 2.5 & 2.6: Test Implementation

**Motivation**: We must validate the new logic at both the unit and end-to-end levels.

- **Files to Edit/Create**:
  - 🧪 `services/file_service/tests/test_core_logic.py`
  - 🧪 `tests/functional/test_e2e_file_workflows.py`

- **Actions**:
  - **Unit Test (Task 2.5)**: Create a test that mocks the `ContentServiceClientProtocol` and verifies the call order and arguments.

    ```python
    # services/file_service/tests/test_core_logic.py
    from unittest.mock import AsyncMock, call
    from common_core.enums import ContentType

    @pytest.mark.asyncio
    async def test_process_single_file_stores_raw_blob_first(mocker):
        # ... setup mocks for protocols ...
        mock_content_client = AsyncMock(spec=ContentServiceClientProtocol)
        mock_content_client.store_content.side_effect = ["raw_id_123", "text_id_456"]

        # ... call process_single_file_upload ...

        # Assert that store_content was called twice with the correct content types
        assert mock_content_client.store_content.call_count == 2
        mock_content_client.store_content.assert_has_calls([
            call(mocker.ANY, content_type=ContentType.RAW_UPLOAD_BLOB),
            call(mocker.ANY, content_type=ContentType.EXTRACTED_PLAINTEXT)
        ])
    ```

  - **E2E Test (Task 2.6)**: Modify an existing E2E test to validate the final event payload in Kafka.

    ```python
    # tests/functional/test_e2e_file_workflows.py
    # Inside an existing test like test_file_upload_publishes_content_provisioned_event

    # ... after collecting events ...
    content_data = event_info["data"]["data"] # Drill down into the payload

    # ➕ ADD THESE ASSERTIONS
    assert "raw_file_storage_id" in content_data
    assert "text_storage_id" in content_data
    assert content_data["raw_file_storage_id"] is not None
    assert content_data["raw_file_storage_id"] != content_data["text_storage_id"]

    print(f"✅ Event validated with raw_id: {content_data['raw_file_storage_id']} "
          f"and text_id: {content_data['text_storage_id']}")
    ```
