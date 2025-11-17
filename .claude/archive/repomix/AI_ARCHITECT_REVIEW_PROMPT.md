# AI Architect Review: CJ Assessment Service Admin Authentication & Authorization

## Context & Objective

I'm implementing authenticated admin endpoints for the CJ Assessment Service as part of Phase 3.2 of the CJ Confidence project. These endpoints will allow operators to manage assessment instructions (grade scales, assignment/course configurations) via both HTTP API and CLI helper tool.

**Current State**: The CJ Assessment Service has no authentication/authorization, and the broader HuleEdu monorepo has no established pattern for admin-only endpoints or role-based access control.

**Goal**: Design an architecturally aligned authentication and authorization solution that follows existing patterns, respects the established security standards, and provides a sustainable pattern for future admin endpoints across services.

---

## How to Use the Attached Repomix Package

### Package Contents

Attached is `repomix-cj-admin-auth-architecture.xml` containing **31 carefully selected files (56K tokens)** that represent the complete authentication and authorization architecture of the HuleEdu monorepo:

1. **JWT Authority** (Identity Service) - Token issuance, user authentication, session management
2. **JWT Validation** (API Gateway) - Token consumption, FastAPI + Dishka DI pattern
3. **Alternative Auth** (Result Aggregator) - Quart-based API key pattern with `@before_request`
4. **Admin Endpoints** (Entitlements Service) - Existing admin routes (currently unprotected)
5. **Target Service** (CJ Assessment Service) - Where admin auth needs to be implemented
6. **Shared Infrastructure** - Error handling, configuration base classes, auth utilities
7. **Architectural Standards** - Security rules, DI patterns, HTTP blueprint conventions, error handling standards
8. **Task Context** - Phase 3.2 requirements, discovery notes, cross-service handoff

### Reading the XML Package

The repomix XML follows this structure:

```xml
<file_summary>
  <!-- Lists all 31 files with their paths and purposes -->
</file_summary>

<repository_structure>
  <!-- Directory tree showing how files relate -->
</repository_structure>

<files>
  <file path="services/identity_service/api/auth_routes.py">
    <!-- Full file content -->
  </file>
  <!-- ... remaining 30 files -->
</files>
```

**Navigation Tips**:
- Search for specific files: `<file path="services/identity_service/config.py">`
- Find patterns: Search for `JWT`, `@before_request`, `raise_authentication_error`, etc.
- Cross-reference: Use the repository structure to understand how files relate
- Top files by token count (most substantial implementations):
  1. `authentication_handler.py` - Complete auth business logic (5K tokens)
  2. `db_access_impl.py` - CJ repository patterns (4K tokens)
  3. `factories.py` - Centralized error handling (3.7K tokens)
  4. `admin_routes.py` - Unprotected admin endpoint example (3.3K tokens)

---

## GitHub Repository Access

You have access to the HuleEdu monorepo on GitHub: **[https://github.com/olofspangberg/huledu-reboot](https://github.com/olofspangberg/huledu-reboot)**

### When to Access GitHub

**Use the repomix package FIRST** for all analysis - it contains the essential auth architecture. Access GitHub only if you need:

- Additional rule files beyond the 5 included (`.claude/rules/*.md`)
- Test implementations to understand validation patterns
- Migration files for database schema context
- Service README files for operational documentation
- Additional API route examples from other services

### Useful GitHub Paths

```
.claude/rules/000-rule-index.md          # Complete rule inventory
.claude/rules/050-python-coding-standards.md
.claude/rules/075-test-creation-methodology.md
services/*/tests/                         # Test patterns
services/*/README.md                      # Service documentation
libs/common_core/src/common_core/         # Shared contracts
```

---

## Current Architecture Analysis

Based on comprehensive codebase exploration, here's what exists:

### JWT Authority (Identity Service)

**Token Issuance**:
- **Dev**: HS256 with symmetric secret (`JWT_DEV_SECRET`)
- **Production**: RS256 with private key signing (`JWT_RS256_PRIVATE_KEY_PATH`)
- **Claims Structure**:
  ```python
  {
    "sub": "user_id",           # User identifier
    "org_id": "org_123",        # Organization (optional)
    "email": "user@example.com",
    "roles": ["user", "admin"], # ⚠️ NOT VALIDATED ANYWHERE
    "exp": timestamp,
    "iss": "huleedu-identity-service",
    "aud": "huleedu-platform"
  }
  ```

**Key Files**:
- `services/identity_service/config.py` - JWT settings
- `services/identity_service/implementations/token_issuer_impl.py` - HS256 implementation
- `services/identity_service/api/auth_routes.py` - Login, refresh, introspect endpoints

### JWT Validation (API Gateway - FastAPI Pattern)

**Implementation**: Dishka DI providers for automatic auth injection

```python
# services/api_gateway_service/app/auth_provider.py
@provide(scope=Scope.REQUEST, provides=str)
def provide_user_id(token: BearerToken, settings: Settings) -> str:
    payload = decode_and_validate_jwt(token, settings)
    return payload["sub"]  # Route won't execute if invalid
```

**Usage in Routes**:
```python
@router.get("/batches")
async def list_batches(user_id: FromDishka[str]):
    # user_id is auto-validated, request fails before reaching here if invalid
```

**Key Files**:
- `services/api_gateway_service/app/jwt_utils.py` - JWT decode/validation logic
- `services/api_gateway_service/app/auth_provider.py` - DI provider implementation

**⚠️ Challenge**: This pattern is **FastAPI-specific**. CJ Assessment uses **Quart**.

### Alternative Auth (Result Aggregator - Quart Pattern)

**Implementation**: Blueprint `@before_request` hook for API key validation

```python
# services/result_aggregator_service/api/query_routes.py
@query_bp.before_request
async def authenticate_request():
    security = await dishka.get(SecurityServiceProtocol)
    api_key = request.headers.get("X-Internal-API-Key")
    service_id = request.headers.get("X-Service-ID")

    if not await security.validate_service_credentials(api_key, service_id):
        return jsonify({"error": "Invalid credentials"}), 401
```

**Key Files**:
- `services/result_aggregator_service/api/query_routes.py` - Blueprint with auth hook
- `services/result_aggregator_service/implementations/security_impl.py` - Validation logic

**✅ Advantage**: This is a **Quart-native pattern** directly applicable to CJ Assessment.

### Admin Endpoints (Entitlements Service)

**Current State**: Admin routes exist but are **completely unprotected**

```python
# services/entitlements_service/api/admin_routes.py
@admin_bp.post("/credits/adjust")
async def adjust_credits(...):
    # ⚠️ NO AUTH CHECK - anyone can call this
```

**Note**: Code comment says "Only available in non-production environments" but this is **not enforced programmatically**.

### Auth Error Handling

**Centralized Factories** (follows rule 048):

```python
# libs/huleedu_service_libs/src/huleedu_service_libs/error_handling/factories.py
raise_authentication_error(
    service="cj_assessment_service",
    operation="validate_admin_token",
    message="Invalid or expired token",
    correlation_id=correlation_id,
    reason="jwt_expired"
)
# Returns ErrorCode.AUTHENTICATION_ERROR (HTTP 401)

raise_authorization_error(
    service="cj_assessment_service",
    operation="register_anchor",
    message="Admin access required",
    correlation_id=correlation_id,
    required_role="admin"
)
# Returns ErrorCode.AUTHORIZATION_ERROR (HTTP 403)
```

**Error Response Structure**:
```json
{
  "error": {
    "error_code": "AUTHORIZATION_ERROR",
    "message": "Admin access required",
    "service": "cj_assessment_service",
    "operation": "register_anchor",
    "correlation_id": "uuid-here",
    "details": {
      "required_role": "admin"
    }
  }
}
```

### Critical Gaps

1. **No role-based authorization** - The `roles` claim exists in JWTs but is never checked
2. **No Quart + JWT pattern** - API Gateway validates JWTs but uses FastAPI
3. **No admin enforcement pattern** - Entitlements has admin routes but no guards
4. **No service-specific auth** - Result Aggregator's API key pattern doesn't translate to user auth

---

## Architectural Decisions Requiring Guidance

### 1. JWT Authority Choice

**Question**: Should CJ Assessment validate tokens from the existing Identity Service, or use a separate auth mechanism?

**Options**:

**A. Reuse Identity Service JWT (Recommended?)**
- **Pro**: Unified platform auth, users already have tokens
- **Pro**: Consistent with API Gateway pattern
- **Con**: Requires validating `roles` claim (currently unused)
- **Con**: Need to add JWT validation to Quart (pattern doesn't exist)

**B. Separate Admin Secret/Key**
- **Pro**: Simple to implement (like Result Aggregator)
- **Pro**: Isolated from user auth concerns
- **Con**: Another credential to manage
- **Con**: Doesn't scale if we want user-specific admin actions later

**C. Internal Service API Key (Result Aggregator Pattern)**
- **Pro**: Established pattern in codebase
- **Pro**: Works for CLI tool easily
- **Con**: No user attribution
- **Con**: Doesn't support future multi-admin scenarios

**Recommendation Needed**: Which approach aligns best with the monorepo's evolution path?

---

### 2. Role-Based Access Implementation

**Question**: How should we validate admin privileges?

**Current State**: Identity Service includes `roles: ["user", "admin"]` in JWT payload, but **no service validates this**.

**Options**:

**A. Check `roles` Claim Directly**
```python
if "admin" not in payload.get("roles", []):
    raise_authorization_error(...)
```
- **Pro**: Simple, uses existing claim structure
- **Con**: Sets precedent without broader RBAC discussion
- **Con**: Hardcoded role strings

**B. Introduce Capability/Permission Model**
```python
# New JWT claim: permissions: ["cj:manage_instructions", "entitlements:adjust_credits"]
if "cj:manage_instructions" not in payload.get("permissions", []):
    raise_authorization_error(...)
```
- **Pro**: More granular, service-namespaced
- **Pro**: Scales to fine-grained permissions
- **Con**: Requires Identity Service changes
- **Con**: More complex for simple use case

**C. Service-Specific Admin Flag**
```python
# New JWT claim: admin_services: ["cj_assessment", "entitlements"]
if "cj_assessment" not in payload.get("admin_services", []):
    raise_authorization_error(...)
```
- **Pro**: Service-scoped, explicit
- **Con**: Identity Service must know about all services

**Recommendation Needed**: Which pattern provides the right balance of simplicity and future flexibility?

---

### 3. Quart Authentication Pattern

**Question**: How should Quart services validate JWTs?

**Current Patterns**:
- **API Gateway**: FastAPI + Dishka DI providers (can't directly translate to Quart)
- **Result Aggregator**: Quart + `@before_request` hook (but for API keys, not JWT)

**Options**:

**A. Blueprint `@before_request` Hook (Result Aggregator Pattern)**
```python
@admin_bp.before_request
async def require_admin():
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    payload = decode_and_validate_jwt(token, settings, correlation_id)

    if "admin" not in payload.get("roles", []):
        raise_authorization_error(...)

    g.admin_user_id = payload["sub"]
```

- **Pro**: Established Quart pattern in codebase
- **Pro**: Centralized at blueprint level
- **Con**: All blueprint routes require auth (might want mixed public/admin)

**B. Custom Decorator Pattern (NEW)**
```python
def require_admin_role(f):
    @wraps(f)
    async def decorated_function(*args, **kwargs):
        token = request.headers.get("Authorization", "").replace("Bearer ", "")
        payload = decode_and_validate_jwt(token, settings, correlation_id)

        if "admin" not in payload.get("roles", []):
            raise_authorization_error(...)

        return await f(*args, **kwargs)
    return decorated_function

@admin_bp.post("/instructions")
@require_admin_role
async def create_instruction(...):
    ...
```

- **Pro**: Per-route flexibility
- **Pro**: Explicit auth requirement visible in route definition
- **Con**: New pattern (no existing example)
- **Con**: More boilerplate per route

**C. Adapt Dishka DI for Quart (EXPERIMENTAL)**
```python
# Quart + Dishka is less mature, but possible
@provide(scope=Scope.REQUEST, provides=AdminUser)
async def provide_admin_user(request: Request, settings: Settings) -> AdminUser:
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    payload = decode_and_validate_jwt(token, settings)

    if "admin" not in payload.get("roles", []):
        raise_authorization_error(...)

    return AdminUser(user_id=payload["sub"], roles=payload["roles"])
```

- **Pro**: Matches API Gateway pattern conceptually
- **Pro**: Testable via DI
- **Con**: Quart's Dishka integration is less documented
- **Con**: May conflict with existing CJ Assessment DI setup

**Recommendation Needed**: Which pattern best balances codebase consistency, Quart compatibility, and maintainability?

---

### 4. Environment-Based Access Control

**Question**: Should admin endpoints be restricted by environment?

**Context**: Entitlements Service has comment "Only available in non-production environments" but doesn't enforce it.

**Options**:

**A. Auth Only (No Environment Gating)**
- Admin endpoints available in all environments
- Security via JWT validation + role check
- Network policies handle production access (VPC, firewall)

**B. Config-Based Gating**
```python
# services/cj_assessment_service/config.py
ENABLE_ADMIN_ENDPOINTS: bool = Field(default=True)

# services/cj_assessment_service/app.py
if settings.ENABLE_ADMIN_ENDPOINTS:
    app.register_blueprint(admin_bp)
```
- **Pro**: Explicit control via environment variables
- **Con**: Must remember to deploy with correct config

**C. Environment Detection + Gating**
```python
# services/cj_assessment_service/app.py
if not settings.is_production():
    app.register_blueprint(admin_bp)
else:
    logger.warning("Admin endpoints disabled in production")
```
- **Pro**: Automatic based on HULEEDU_ENVIRONMENT
- **Con**: Inflexible if production admin access is needed

**Recommendation Needed**: What level of environment-based control aligns with operational security principles?

---

### 5. CLI Helper Authentication

**Question**: How should the Typer CLI (`cj-admin`) authenticate to admin endpoints?

**Context**: Building `services/cj_assessment_service/cli_admin.py` (similar to `scripts/cj_experiments_runners/eng5_np/cli.py`) for commands like:
```bash
pdm run cj-admin instructions create --assignment-id 123 --grade-scale A-F
pdm run cj-admin instructions list --grade-scale A-F
pdm run cj-admin anchors register --essay-id 456 --grade C
```

**Options**:

**A. JWT via Identity Service Login**
```python
# CLI prompts for credentials, gets JWT, uses for subsequent requests
class AdminCLI:
    def __init__(self):
        self.token = self.login()  # Interactive or from env var

    def login(self) -> str:
        username = os.getenv("ADMIN_USERNAME") or click.prompt("Username")
        password = os.getenv("ADMIN_PASSWORD") or click.prompt("Password", hide_input=True)
        # Call Identity Service /auth/login
        return response.json()["access_token"]
```

- **Pro**: Reuses existing auth infrastructure
- **Pro**: User attribution in audit logs
- **Con**: Requires Identity Service to be running
- **Con**: More complex for simple scripting

**B. Pre-Generated Admin Token (Environment Variable)**
```python
# Operator generates long-lived admin token, stores in .env
ADMIN_JWT_TOKEN = os.getenv("CJ_ADMIN_TOKEN")
if not ADMIN_JWT_TOKEN:
    raise click.ClickException("CJ_ADMIN_TOKEN environment variable required")
```

- **Pro**: Simple for scripting and automation
- **Pro**: No interactive flow needed
- **Con**: Token management/rotation responsibility on operator
- **Con**: Risk of token leakage in env files

**C. Internal API Key (Simplest)**
```python
# CLI uses X-Internal-API-Key header like Result Aggregator
headers = {"X-Internal-API-Key": settings.INTERNAL_API_KEY}
```

- **Pro**: Simplest implementation
- **Pro**: Established pattern in Result Aggregator
- **Con**: No user attribution
- **Con**: Conflicts with JWT approach for HTTP API

**Recommendation Needed**: Should CLI and HTTP API use the same auth mechanism, or different approaches?

---

### 6. JWT Validation Settings Location

**Question**: Where should CJ Assessment store JWT validation config?

**Current Patterns**:
- **Identity Service**: Has JWT issuance config (secret, algorithm, issuer, audience)
- **API Gateway**: Has JWT validation config (mirrors Identity settings for validation)

**Options**:

**A. Add to CJ Assessment Settings (Duplication)**
```python
# services/cj_assessment_service/config.py
class Settings(SecureServiceSettings):
    JWT_SECRET_KEY: SecretStr = Field(...)
    JWT_ALGORITHM: str = "HS256"
    JWT_ISSUER: str = "huleedu-identity-service"
    JWT_AUDIENCE: str = "huleedu-platform"
```

- **Pro**: Service is self-contained
- **Pro**: Follows API Gateway pattern
- **Con**: Config duplication across services
- **Con**: Must keep in sync with Identity Service

**B. Shared JWT Validation Settings (NEW Library)**
```python
# libs/huleedu_service_libs/src/huleedu_service_libs/auth/jwt_settings.py
class JWTValidationSettings(BaseSettings):
    JWT_SECRET_KEY: SecretStr = Field(...)
    JWT_ALGORITHM: str = "HS256"
    # ...

# services/cj_assessment_service/config.py
class Settings(SecureServiceSettings, JWTValidationSettings):
    pass
```

- **Pro**: DRY, single source of truth
- **Pro**: Future services benefit
- **Con**: New pattern, no existing example
- **Con**: Adds coupling via shared library

**C. Service Discovery / Config Service (Future)**
- Not implemented currently, aspirational

**Recommendation Needed**: Accept duplication (API Gateway pattern) or invest in shared settings?

---

## Expected Deliverables

### 1. Architectural Recommendations

For each decision point above, provide:

- **Recommended Approach**: Which option to pursue
- **Rationale**: Why it aligns with HuleEdu architecture principles
- **Rule Alignment**: How it respects the existing standards (rules 047, 042, 041, 048, 020)
- **Implementation Notes**: Key technical considerations
- **Migration Path**: If this introduces new patterns, how should existing services (like Entitlements) migrate?

### 2. Implementation Blueprint

Provide a high-level structure (not full code) for:

**A. Settings Extension**
```python
# services/cj_assessment_service/config.py
class Settings(SecureServiceSettings):
    # What JWT-related fields to add?
    # What admin-specific config (if any)?
```

**B. Authentication Mechanism**
```python
# services/cj_assessment_service/api/admin_routes.py
# Blueprint setup
# @before_request hook OR decorator pattern
# JWT validation logic placement
```

**C. Authorization Check**
```python
# How to validate roles/permissions?
# Where to extract user_id for audit logging?
```

**D. Error Handling**
```python
# Usage of raise_authentication_error vs raise_authorization_error
# Where to get correlation_id in Quart context
```

**E. CLI Integration**
```python
# services/cj_assessment_service/cli_admin.py
# How CLI obtains and uses credentials
# Environment variable expectations
```

### 3. Pattern Documentation

Since this will be the **first Quart + JWT + role-based auth** implementation, provide guidance on:

- Should this become a new rule file? (e.g., `.claude/rules/047.1-quart-jwt-authentication.md`)
- Key patterns that future services should follow
- Testing strategy (how to test auth logic in isolation)

### 4. Risk Assessment

Identify potential issues:

- Security risks (token leakage, privilege escalation)
- Operational risks (credential management, token rotation)
- Technical debt (patterns that may need refactoring later)
- Migration impact (does Entitlements Service need immediate updates?)

---

## Constraints & Preferences

### Must Follow

1. **Rule 047** (Security Configuration Standards) - All security config must use SecureServiceSettings, SecretStr, environment-aware patterns
2. **Rule 048** (Structured Error Handling) - Must use `raise_authentication_error` and `raise_authorization_error` factories
3. **Rule 042** (Async Patterns & DI) - Dishka DI for all dependencies, async/await throughout
4. **Rule 041** (HTTP Service Blueprint) - Quart blueprints in `api/` directory, proper middleware registration
5. **Rule 020** (Architectural Mandates) - DDD, clean code, strict service boundaries

### User Preferences (CLAUDE.md)

- "I hate sloppy vibe-coding. Everything must be according to plan and my projects' patterns and architecture."
- "Respect the codebase patterns. There are well-established conventions in my implemented services to mirror."
- "All future error handling must be structured and use my error_handling and observability stack."
- "I build from the inside out: always beginning in pure backend and then moving outwards to the frontend."
- "I only build microservices with a strict DDD and Clean Code approach (inversion of control: protocols, implementations, Dishka DI)"

### Project Constraints

- **No vibe coding**: Solution must be architecturally sound, not expedient hacks
- **Pattern consistency**: Should mirror existing patterns unless creating justified new pattern
- **DRY but pragmatic**: Avoid duplication, but not at cost of excessive coupling
- **Testability**: Auth logic must be testable in isolation (unit tests, integration tests)
- **Developer experience**: CLI tool should be ergonomic for operators

---

## Review Process

### Step 1: Read the Repomix Package
- Start with the file_summary to orient yourself
- Focus on the "Top 5 Files by Token Count" (most substantial)
- Cross-reference between related files (e.g., Identity config → API Gateway validation)

### Step 2: Access GitHub for Additional Context (Optional)
- Review additional rule files if needed (`.claude/rules/000-rule-index.md` lists all)
- Check test patterns (`services/*/tests/`) to understand validation approaches
- Read service READMEs for operational context

### Step 3: Analyze Architectural Gaps
- Identify what's missing (role validation, Quart JWT pattern, admin guards)
- Assess which existing patterns are applicable vs. need adaptation
- Consider evolution path (will other services need similar admin auth?)

### Step 4: Formulate Recommendations
- For each of the 6 decision points, provide clear recommendation with rationale
- Ensure alignment with the 5 core architectural rules
- Balance simplicity (for Phase 3.2 delivery) with sustainability (for future growth)

### Step 5: Provide Implementation Blueprint
- High-level structure, not full implementation
- Show how pieces fit together (Settings → JWT validation → Blueprint → Error handling → CLI)
- Highlight integration points with existing code

### Step 6: Document Patterns for Future Use
- Suggest whether new rule file is warranted
- Identify reusable components (shared JWT validation utility?)
- Note any technical debt introduced that should be addressed later

---

## Success Criteria

Your review should enable me to:

1. **Implement with confidence** - Clear architectural direction, no ambiguity on approach
2. **Follow established patterns** - Recommendations that respect existing conventions
3. **Set sustainable precedent** - If introducing new patterns, they should be broadly applicable
4. **Pass rule compliance** - Adherence to rules 047, 048, 042, 041, 020
5. **Enable future work** - Pattern that scales to other services needing admin auth

---

## Timeline & Context

**Phase 3.2 Deliverable**: Admin endpoint implementation is the critical blocker for CJ Confidence Phase 3 data capture experiments.

**Downstream Impact**: Once admin auth is in place:
- Operators can seed assessment instructions via CLI
- ENG5 NP runner can register anchors for batch processing
- Phase 3.3 validation can proceed with proper grade scale data

**Other Stakeholders**: Entitlements Service also needs admin auth - your recommendations should consider this as a pilot implementation that others will follow.

---

Thank you for your thorough architectural review. Your expertise will help establish a robust, pattern-aligned authentication solution that serves as a foundation for admin capabilities across the HuleEdu platform.
