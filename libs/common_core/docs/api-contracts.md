# API Contracts

HTTP request/response models in `api_models/` directory.

## Purpose

Explicit contracts for synchronous HTTP communication between services. Prevents drift, enforces typing.

## Location

```
common_core/api_models/
├── batch_registration.py      # BOS registration API
├── assessment_instructions.py # CJ assessment instructions
└── language_tool.py            # LanguageTool service models
```

## BatchRegistrationRequestV1

Contract for batch registration via API Gateway → BOS.

```python
from common_core.api_models.batch_registration import BatchRegistrationRequestV1
from common_core.domain_enums import CourseCode
from common_core.metadata_models import StorageReferenceMetadata

class BatchRegistrationRequestV1(BaseModel):
    # Batch configuration
    expected_essay_count: int = Field(gt=0)
    essay_ids: list[str] | None = Field(default=None, min_length=1)
    course_code: CourseCode
    student_prompt_ref: StorageReferenceMetadata | None = None

    # Identity threading (from JWT)
    user_id: str  # Required from JWT sub claim
    org_id: str | None = None  # Optional from JWT org claim

    # Class context
    class_id: str | None = None  # Required for REGULAR batches, None for GUEST

    # CJ assessment configuration
    enable_cj_assessment: bool = False
    cj_default_llm_model: str | None = None
    cj_default_temperature: float | None = Field(default=None, ge=0.0, le=2.0)

    @model_validator(mode="after")
    def validate_essay_count_consistency(self) -> BatchRegistrationRequestV1:
        if self.essay_ids and len(self.essay_ids) != self.expected_essay_count:
            raise ValueError(f"essay_ids length must match expected_essay_count")
        return self
```

**Producer**: API Gateway (enriches with JWT data)
**Consumer**: Batch Orchestrator Service

## Versioning

All API models MUST include version suffix (.v1, .v2):

```python
class MyAPIModelV1(BaseModel):  # ✓ Versioned
    ...

class MyAPIModel(BaseModel):  # ❌ No version suffix
    ...
```

Breaking changes require new version:

```python
# Old version
class RequestV1(BaseModel):
    field_a: str
    field_b: int

# New version with breaking change (removed field_b)
class RequestV2(BaseModel):
    field_a: str
    field_c: float  # New field
```

## Usage: Producer (API Gateway)

```python
from common_core.api_models.batch_registration import BatchRegistrationRequestV1

@app.post("/batches")
async def register_batch(request: ClientRequest, jwt_claims: dict) -> dict:
    # Enrich client request with JWT identity
    bos_request = BatchRegistrationRequestV1(
        expected_essay_count=request.essay_count,
        course_code=request.course_code,
        user_id=jwt_claims["sub"],  # From JWT
        org_id=jwt_claims.get("org_id"),  # From JWT
        class_id=request.class_id,
        enable_cj_assessment=request.enable_cj
    )

    # Forward to BOS via HTTP
    response = await bos_client.post("/register", json=bos_request.model_dump())
    return response
```

## Usage: Consumer (BOS)

```python
from common_core.api_models.batch_registration import BatchRegistrationRequestV1

@app.post("/register")
async def register(request: BatchRegistrationRequestV1) -> dict:
    # FastAPI/Quart validates automatically
    # Identity fields guaranteed present

    batch = await batch_service.create(
        user_id=request.user_id,  # Type-safe
        org_id=request.org_id,
        essay_count=request.expected_essay_count,
        course=request.course_code
    )

    return {"batch_id": batch.id}
```

## Pydantic Validation

API models use Pydantic Field() for validation:

```python
class MyAPIModelV1(BaseModel):
    # Constraints
    count: int = Field(gt=0, le=1000, description="Item count 1-1000")
    email: EmailStr  # Built-in email validation
    temperature: float = Field(ge=0.0, le=2.0)  # Range constraint

    # Optional with defaults
    retry_count: int = Field(default=3, ge=1, le=10)

    # Custom validators
    @field_validator("essay_ids")
    @classmethod
    def validate_unique(cls, v: list[str]) -> list[str]:
        if len(v) != len(set(v)):
            raise ValueError("essay_ids must be unique")
        return v
```

## Related

- `common_core/api_models/` - All HTTP contracts
- `.claude/rules/020-architectural-mandates.mdc` - Contract-only communication
- `.claude/rules/051-pydantic-v2-standards.mdc` - Pydantic patterns
