# TASK: Content Service Idempotent Uploads & Lifecycle Hygiene

**Status**: TODO  
**Priority**: HIGH  
**Blocking**: None  
**Created**: 2025-11-14  
**Owner Team**: agents  

---

## Context

Repeated anchor registrations currently call `ContentClient.store_content` for every request, even when the file already exists. This pattern creates duplicate blobs, leaves stale `text_storage_id` objects unreferenced, and makes it difficult to understand which anchor version is active. The CJ anchor remediation work highlighted the need for deterministic linkage between CJ references and Content Service storage, plus an explicit cleanup strategy.

This task formalizes the work required inside the Content Service stack and all upload clients (CJ CLI, admin APIs, workers) to make uploads idempotent, version anchors intentionally, and clean up orphaned blobs.

---

## Problem Statement

1. **Duplicate blobs** – Every anchor registration uploads a new blob, even if the content already exists, wasting storage and making audits harder.
2. **No version lineage** – CJ references simply overwrite `text_storage_id`, so we lose the historical context of anchor updates and cannot tell which blob is safe to delete.
3. **No lifecycle cleanup** – Obsolete blobs remain forever in Content Service because nothing tracks whether they are still referenced after a CJ update.

---

## Goals & Requirements

### 1. Idempotent uploads across all clients

- Before any service/CLI calls `store_content`, hash the payload (SHA-256 or equivalent).
- Extend Content Service with a "lookup-or-create" endpoint/API that returns the existing `text_storage_id` when a matching hash is found; only create a blob when the hash is new.
- Update all uploaders (anchor registration API, ENG5 runner, other services) to use the new idempotent API.

### 2. Versioned anchor references

- When content truly changes, create a new version row that records:
  - `anchor_id`, `version_number`, `text_storage_id`, `content_hash`, timestamps, and an optional `deprecated_at`.
  - Keep an explicit status flag (`active`, `deprecated`) so CJ logic can always resolve the latest active anchor while preserving history for audits.
  - Provide an admin/CLI workflow to intentionally roll back or promote versions.

### 3. Lifecycle cleanup job

- Build a periodic Content Service worker (or extend existing cleanup jobs) that:

  - Scans for blobs not referenced by any active anchor version for longer than a configurable grace period.

  - Deletes the orphaned blobs and emits metrics/logging for observability.

- Ensure deletions are safe by double-checking references just before removal and by documenting the grace period policy.

---

## Deliverables

1. **Design doc / ADR** describing the hashing scheme, lookup-or-create API shape, versioning schema changes, and cleanup strategy.

2. **Content Service changes** implementing the new API, storage schema, and cleanup worker.

3. **Client updates** (CJ anchor API, ENG5 runner CLI, any other content uploaders) to compute hashes, call the new API, and record version metadata.

4. **Tests & tooling** covering hash collisions, version promotion/demotion flows, and cleanup safety checks.

5. **Runbook updates** documenting how to register anchors, inspect versions, and monitor cleanup metrics.

---

## Success Criteria

- Uploading the same anchor content twice reuses the original `text_storage_id` (confirmed via integration tests and CLI runs).
- CJ anchor references clearly show version lineage and allow rollbacks without manual DB surgery.
- Orphaned blobs are automatically removed after the grace period, with observability dashboards tracking deletions.
- Documentation instructs engineers on how to add anchors, update them intentionally, and verify cleanup.

---

## References

- `TASK-FIX-CJ-ANCHOR-FINALIZATION-AND-MONITORING.md`
- `TASK-FIX-ANCHOR-ESSAY-INFRASTRUCTURE.md`
- `scripts/cj_experiments_runners/eng5_np/cli.py`
- `services/cj_assessment_service/api/anchor_management.py`
