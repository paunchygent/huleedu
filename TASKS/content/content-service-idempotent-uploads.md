---
id: content-service-idempotent-uploads
title: Content Service Idempotent Uploads
type: task
status: research
priority: medium
domain: content
owner_team: agents
created: '2025-11-21'
last_updated: '2025-11-21'
service: content_service
owner: ''
program: ''
related: []
labels: []
---

# TODO report – TASK-CONTENT-SERVICE-IDEMPOTENT-UPLOADS

Generated: 2025-11-14 18:51:21 UTC

| File | Line | Note |
| --- | --- | --- |
| `services/cj_assessment_service/api/anchor_management.py` | 99 | switch to hashed lookup-or-create flow |
| `services/cj_assessment_service/implementations/content_client_impl.py` | 133 | compute a content hash and call |
| `services/content_service/api/content_routes.py` | 55 | replace random ID assignment with |
| `services/file_service/core_logic.py` | 92 | hash raw uploads and reuse existing blobs |
| `services/file_service/core_logic.py` | 294 | dedupe extracted plaintext uploads via hash. |
| `services/file_service/implementations/content_service_client_impl.py` | 46 | compute content hash and reuse existing |
