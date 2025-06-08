# 🎯 Implementation Task Outline — File Registration, Upload & Validation Improvements

Below is a **developer-facing work document** that merges your current flow with all recommended adjustments.
Copy it into `docs/tasks/file-pipeline-hardening.md` (or equivalent) so each sub-team can pick up its part.

---

## 0. Legend

| Symbol | Meaning               |
| ------ | --------------------- |
| ✅      | already exists — keep |
| ➕      | new code / object     |
| 🔄     | modify existing code  |
| ⚙️     | ops / infra work      |
| 📈     | metrics / logging     |
| 🧪     | tests                 |

---

## 1. Storage & Extraction Ordering (🔄 File Service)

| Step | Task                                                                                     | Snippet / Pointer                                                                                   |
| ---- | ---------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------- |
| 1.1  | 🔄 Persist **raw bytes first**, then stream to extractor.                                | `python<br>raw_id = await blob_store.put(file_content)<br>text   = await extractor.extract(raw_id)` |
| 1.2  | 🔄 Update per-file success event to carry `raw_storage_id` as well if useful downstream. | —                                                                                                   |
| 1.3  | 🧪 Unit: ensure re-extracting the same `raw_id` returns identical text.                  |                                                                                                     |

---

## 2. Event Idempotency (➕ All publishers / consumers)

| Step | Task                                                                                                   | Details                                   |
| ---- | ------------------------------------------------------------------------------------------------------ | ----------------------------------------- |
| 2.1  | ➕ Generate deterministic `event_id = sha256(batch_id + essay_id + phase + outcome)` for every publish. | Use helper in `common_core.events.utils`. |
| 2.2  | 🔄 Consumers add de-dup table (e.g. Redis SET) before processing; skip if `event_id` seen.             |                                           |
| 2.3  | 🧪 Chaos test: replay a success event twice → downstream state changes once.                           |                                           |

---

## 3. Back-pressure & DLQ (⚙️ Kafka / orchestrator)

| Task | Notes                                                                                           |   |
| ---- | ----------------------------------------------------------------------------------------------- | - |
| 3.1  | Set `max.poll.records` or `prefetch` limit on Spellcheck consumer group to throttle.            |   |
| 3.2  | Create **dead-letter topic** `essay.processing.dlq`. On N retries publish failed message there. |   |
| 3.3  | 📈 Expose Prometheus metric `dlq_messages_total`.                                               |   |

---

## 4. Error Taxonomy Refinement (🔄 Extractor + Validator)

| Code              | New error codes                                        |
| ----------------- | ------------------------------------------------------ |
| Extractor         | `UNSUPPORTED_FORMAT`, `CORRUPTED_FILE`, `TIMEOUT`      |
| Validator         | keep `EMPTY_CONTENT`, `CONTENT_TOO_SHORT/LONG`         |
| Update dashboards | 📈 Split `essay_validation_failed_total` by new codes. |

---

## 5. Command/Event Vocabulary Audit (🔄 Everywhere)

* **Rule**: *Commands* = *imperative present*, *Events* = *past tense fact*.
* Rename (code & topic):

  * `SpellcheckInitiateCommand` → **`SpellcheckInitiate`** (command)
  * `SpellCheckCompletedV1` (already event) — keep
* Search-replace in producers, consumers, docs.

---

## 6. Batch Completeness v2 (➕ File Service, 🔄 ELS)

### 6.1 New event schema

```python
class EssayUploadFinishedV1(BaseModel):
    event          : Literal["essay.upload.finished"] = "essay.upload.finished"
    batch_id       : str
    expected_count : int            # files in this HTTP request
    upload_ts      : datetime
    correlation_id : UUID | None
```

### 6.2 Emitter (File Service)

*After last `for file in files` in `upload_batch_files`:*

```python
await event_publisher.publish_upload_finished(
    EssayUploadFinishedV1(
        batch_id=batch_id,
        expected_count=len(uploaded_files),
        upload_ts=datetime.now(timezone.utc),
        correlation_id=main_correlation_id,
    ),
    main_correlation_id,
)
```

### 6.3 ELS tracker updates

| Field                              | Add to `BatchExpectation` |
| ---------------------------------- | ------------------------- |
| `received_count_from_uploads: int` | initial 0                 |

| Handler                  | Pseudocode                                                                                                               |
| ------------------------ | ------------------------------------------------------------------------------------------------------------------------ |
| `handle_upload_finished` | `python<br>be.received_count_from_uploads += evt.expected_count<br>if be.received >= be.expected_from_bos: emit_ready()` |

*Timeout logic unchanged.*

---

## 7. Observability

| Task | How                                                                                                      |
| ---- | -------------------------------------------------------------------------------------------------------- |
| 7.1  | 📈 Add structured log keys `{corr_id, batch_id, essay_id, phase, status, duration_ms}` via logger extra. |
| 7.2  | 📈 Metrics: `essay_validation_failed_total{error_code}` and `batch_completion_seconds{status}`.          |

---

## 8. Test Matrix (🧪 automated E2E)

| Case                          | Expected                                                   |
| ----------------------------- | ---------------------------------------------------------- |
| Happy: 3 good + 1 empty       | `BatchEssaysReady.ready_essays = 3`                        |
| Overflow: expected 7, send 9  | 7 slots assigned, 2 `ExcessContentProvisioned`.            |
| Underflow: expected 7, send 5 | Timeout after T sec → `BatchReadinessTimeout missing_n=2`. |
| Duplicate publish             | State changes exactly once.                                |

---

## 9. Front-End Drop Handler (reference)

```ts
async function onDrop(files: FileList) {
  // register
  const reg = await fetch("/v1/batches/register", {
    method:"POST",
    headers:{ "Content-Type":"application/json" },
    body: JSON.stringify({ expected_essay_count: files.length, ... })
  });
  const { batch_id, correlation_id } = await reg.json();

  // upload
  const fd = new FormData();
  fd.append("batch_id", batch_id);
  Array.from(files).forEach(f => fd.append("files", f));
  await fetch("/v1/files/batch", {
    method:"POST",
    headers:{ "X-Correlation-ID": correlation_id },
    body: fd
  });
}
```

---

## 10. Roll-out Steps (chronological)

1. **Merge** new event model in `common_core`.
2. Implement File Service emitter (6.2).
3. Update ELS tracker & handler (6.3).
4. Introduce refined error codes (4).
5. Add idempotent `event_id` helper and consumer dedup (2).
6. Deploy to staging; run E2E matrix (8).
7. Wire Prometheus alerts for DLQ & batch timeouts.
8. Gradual prod deploy (canary → full).

---

*End of task document.*
