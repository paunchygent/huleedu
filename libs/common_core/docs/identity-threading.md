# Identity Threading

user_id and org_id propagation through entire request chain for entitlements and credit attribution.

## Fields

```python
user_id: str  # Required - JWT sub claim, identifies user
org_id: str | None  # Optional - JWT org claim, org-first attribution
```

## Flow

```
Client Request
  ↓
API Gateway (extracts from JWT)
  ├─→ user_id = jwt["sub"]
  ├─→ org_id = jwt.get("org_id")
  ↓
Batch Orchestrator Service (stores in batch record)
  ↓
Event to Essay Lifecycle Service (includes user_id, org_id)
  ↓
Events to Processing Services (CJ, NLP, etc - all include user_id, org_id)
  ↓
Entitlements Service (checks quotas, records usage)
```

## API Gateway Extraction

```python
@app.post("/batches")
async def register_batch(request: ClientRequest, jwt: dict) -> dict:
    bos_request = BatchRegistrationRequestV1(
        user_id=jwt["sub"],          # Required from JWT
        org_id=jwt.get("org_id"),    # Optional from JWT
        # ... other fields
    )
    response = await bos_client.post("/register", json=bos_request.model_dump())
    return response
```

## Event Propagation

All events that trigger resource consumption MUST include user_id/org_id:

```python
# BOS → ELS command
command = BatchServiceCJAssessmentInitiateCommandDataV1(
    user_id=batch.user_id,  # From batch record
    org_id=batch.org_id,
    essays_to_process=[...],
    # ... other fields
)

# ELS → CJ Assessment request
request = ELS_CJAssessmentRequestV1(
    user_id=command.user_id,  # Propagate
    org_id=command.org_id,
    essays_for_cj=[...],
    # ... other fields
)
```

## Entitlements Integration

Processing services emit resource consumption events:

```python
# CJ Assessment Service after LLM usage
consumption_event = ResourceConsumptionReportedV1(
    user_id=request.user_id,       # From request
    org_id=request.org_id,
    resource_type="llm_tokens",
    amount=tokens_used,
    timestamp=datetime.now(UTC)
)

await kafka_bus.publish(
    topic_name(ProcessingEvent.RESOURCE_CONSUMPTION_REPORTED),
    wrap_event(consumption_event)
)
```

Entitlements Service consumes these events, attributes usage:

```python
# Entitlements Service
async def handle_resource_consumption(event: ResourceConsumptionReportedV1):
    # Deduct from org quota if org_id present
    if event.org_id:
        await self.deduct_org_quota(event.org_id, event.resource_type, event.amount)
    else:
        # Deduct from user quota
        await self.deduct_user_quota(event.user_id, event.resource_type, event.amount)
```

## Org-First Attribution

When org_id present: quota deducted from organization, not individual user.

```python
# Decision logic
if request.org_id:
    quota_source = f"org:{request.org_id}"
    # Check org quota, deduct from org
else:
    quota_source = f"user:{request.user_id}"
    # Check user quota, deduct from user
```

## Storage in Database

Batch/job records store identity for audit and attribution:

```python
# BOS batch table
class Batch(Base):
    id: Mapped[str]
    user_id: Mapped[str]        # NOT NULL
    org_id: Mapped[str | None]  # NULL for individual users
    # ...
```

## Correlation with JWT

API Gateway validates JWT, extracts claims:

```python
jwt_payload = validate_jwt_token(request.headers["Authorization"])
user_id = jwt_payload["sub"]     # Standard JWT subject claim
org_id = jwt_payload.get("org_id")  # Custom claim for org context

# Inject into all downstream requests
```

## Required in All Contracts

All contracts that trigger processing MUST include:

- BatchRegistrationRequestV1
- ELS_CJAssessmentRequestV1
- Batch command events (spellcheck, NLP, etc.)
- Resource consumption events

Models without user_id/org_id cannot be attributed to quotas.

## Related

- `common_core/api_models/batch_registration.py` - API contract with identity
- `common_core/events/cj_assessment_events.py` - Event with identity
- `.claude/rules/020-architectural-mandates.md` - Identity threading mandate
