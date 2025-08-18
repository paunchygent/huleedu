# Identity Service — Implementation Status, Alignment, and Next Steps

Related source task: `TASKS/IDENTITY_ENTITLEMENTS_EMAIL_SERVICE_SCAFFOLD_AND_EVENT_CONTRACTS.md`

This report documents what has been implemented for the Identity Service, why it was implemented, how it aligns with HuleEdu rules and the original task, what remains to be done, and a QC/pain‑point checklist for the next session.

---

## Executive Summary

- Identity is now scaffolded as a Quart HTTP service with Dishka DI and the TRUE OUTBOX PATTERN for event publishing.
- Core security building blocks are in place: Argon2id password hashing (dev→prod ready), Postgres-backed repositories, RS256 TokenIssuer with JWKS exposure (production) and HS256‑like dev fallback.
- Common contracts and topics were added to `common_core` to enable identity/email/entitlements event exchanges, as requested by the source task.
- **COMPLETED: Database migration infrastructure fully operational, all tables created, complete monorepo integration, 100% type safety compliance.**

---

## Scope Traceability to Source Task

From `IDENTITY_ENTITLEMENTS_EMAIL_SERVICE_SCAFFOLD_AND_EVENT_CONTRACTS.md`:

- “Identity (User) Service: authentication, user lifecycle, roles/tenancy, JWT/JWKS”
  - Implemented: service scaffold, DI, Argon2id hasher, Postgres `users` + `refresh_sessions`, RS256 issuer + JWKS endpoint, dev HS256 fallback.
  - Pending: full user lifecycle endpoints (email verification, password reset), roles/tenancy policies, refresh/logout endpoints, event emissions.

- “Event contracts (Pydantic) for all interactions, topic naming, and gateway integration”
  - Implemented in `common_core`: identity/email/entitlements models + new `ProcessingEvent` members + topic mappings.
  - Pending: gateway RS256 validation switch + end-to-end event flows from Identity.

- “Outbox: Use huleedu_service_libs.outbox for business‑critical events”
  - Implemented: outbox table + DI wiring and relay worker; identity publisher scaffold ready to emit events.

---

## Recent Progress (Phase 2B - Database Migration Resolution)

**Completed 2025-08-18:**

### Database Infrastructure Resolution
- **FIXED: Alembic migration infrastructure** - Resolved broken `script.py.mako` template, updated `alembic.ini` to match HuleEdu patterns
- **CREATED: email_verification_tokens table** - Full schema with indexes, foreign keys, cascade constraints  
- **CREATED: password_reset_tokens table** - Matching schema pattern for password reset workflow
- **VERIFIED: All database operations functional** - Migration tracking at head revision `c9ba97ebc0f1`

### Service Integration Completion  
- **ADDED: identity_service to root pyproject.toml** - Dev dependencies, pytest testpaths, mypy overrides
- **FIXED: PDM integration** - All alembic commands work from correct directory structure
- **RESOLVED: Monorepo integration** - Service fully integrated following established patterns

### Type Safety & Code Quality
- **RESOLVED: 12 mypy errors across 7 files** - 100% type check compliance (887 source files)
- **FIXED: Event schema alignment** - LoginSucceededV1/LoginFailedV1 match common_core contracts
- **CORRECTED: Configuration types** - Database URL attribute resolution, proper type narrowing
- **ADDED: Return type annotations** - API routes, token issuers, well-known endpoints

**Status: Database migration blockers resolved. Ready for endpoint implementation.**

---

## What Was Implemented

### 1) Common Core Contracts and Topics

- Files added:
  - `libs/common_core/src/common_core/identity_models.py` — `UserRegisteredV1`, `EmailVerificationRequestedV1`, `EmailVerifiedV1`, `PasswordResetRequestedV1`, `LoginSucceededV1`, `LoginFailedV1`, `JwksPublicKeyV1`, `JwksResponseV1`.
  - `libs/common_core/src/common_core/emailing_models.py` — `NotificationEmailRequestedV1`, `EmailSentV1`, `EmailDeliveryFailedV1`.
  - `libs/common_core/src/common_core/entitlements_models.py` — `SubjectRefV1`, plans/usage/credits/ACL events.
  - `libs/common_core/src/common_core/event_enums.py` — Added Identity/Email/Entitlements enums and exact topic mappings documented in the source task.
  - `libs/common_core/src/common_core/__init__.py` — Re-exports for ergonomic imports.

### 2) Identity Service Scaffold

- Quart application: `services/identity_service/app.py`
  - Registers blueprints; startup wires Dishka container and Outbox relay worker, tracing middleware.
- DI: `services/identity_service/di.py`
  - Core provider (settings, HTTP, Redis, DB engine, OutboxProvider).
  - Identity implementations: `Argon2idPasswordHasher`, `PostgresUserRepo`, `PostgresSessionRepo`, `DefaultIdentityEventPublisher`, and environment‑aware `TokenIssuer` (RS256 in production, dev fallback otherwise). Also provides `JwksStore`.
- Routes:
  - `services/identity_service/api/auth_routes.py` — Minimal `POST /v1/auth/register`, `POST /v1/auth/login`, and `GET /v1/auth/me` (dev). Login verifies Argon2id hash, issues access + refresh, persists refresh session.
  - `services/identity_service/api/well_known_routes.py` — `GET /.well-known/jwks.json` serving keys from `JwksStore`.
- Security:
  - Hasher: `services/identity_service/implementations/password_hasher_impl.py` — Argon2id.
  - Token issuer (dev): `services/identity_service/implementations/token_issuer_impl.py` — HS256‑like placeholder.
  - Token issuer (prod): `services/identity_service/implementations/token_issuer_rs256_impl.py` — RS256 signing using configured private key; registers public JWK in `JwksStore`.
  - JWKS store: `services/identity_service/implementations/jwks_store.py`.
- Persistence:
  - Models: `services/identity_service/models_db.py` — `User`, `RefreshSession`, and `EventOutbox` with performant indexes.
  - Repos: `services/identity_service/implementations/user_repository_sqlalchemy_impl.py` — Postgres repos for users and sessions (async, simple lifecycle ops).
- Outbox pattern:
  - `services/identity_service/implementations/outbox_manager.py` — service wrapper; DI provides `EventRelayWorker` via `OutboxProvider`.
  - Publisher scaffold: `services/identity_service/implementations/event_publisher_impl.py` — emits `IDENTITY_USER_REGISTERED` via outbox (extend for more events).
- Config & Migrations:
  - Config: `services/identity_service/config.py` — `.env`‑aware DB URL (Rule 085), prod/dev separation.
  - Alembic: `services/identity_service/alembic/*` — Async env + initial migration creating `users`, `refresh_sessions`, and `event_outbox` with indexes.
- PDM project (no pinning): `services/identity_service/pyproject.toml`
  - Minimal dependencies; Docker overrides; standard scripts.

---

## Alignment With HuleEdu Rules

- Rule 015 Project Structure: HTTP routes in `api/`, app <150 LoC, no unused folders added.
- Rule 042 Async Patterns & DI: Dishka providers, APP scope for infra, REQUEST scope suitable for sessions.
- Rule 042.1 Transactional Outbox: Outbox provider and relay worker; event publishing through outbox.
- Rule 048 Structured Error Handling: Publisher/outbox managers align; future endpoints should wrap errors using service libs.
- Rule 053 SQLAlchemy: async models, proper timestamp types, UUID usage; JSON field handling; partial indexes for outbox.
- Rule 085 Database Migration Standards: `.env` discovery, alembic async env, no hardcoded secrets, monorepo venv commands.
- Rule 081/083 PDM: Minimal configuration, no version pinning; Docker overrides match repo standard.

---

## What Remains (Identity)

1) Endpoints and flows **[Database tables ready]**

- Email verification: issue token (table: `email_verification_tokens`), `EmailVerificationRequestedV1` event; verify endpoint; `EmailVerifiedV1` event.
- Password reset: request token (table: `password_reset_tokens`) and event; reset endpoint.
- Refresh/logout: rotate or revoke refresh tokens; `SessionRepo` integration.
- "Me" endpoint: gateway-validated user context (RS256), or dev helper under `/dev` path.

2) Event publishing (via outbox) **[Schemas aligned]**

- Implement and call publishers for: `IDENTITY_USER_REGISTERED`, `IDENTITY_EMAIL_VERIFICATION_REQUESTED`, `IDENTITY_EMAIL_VERIFIED`, `IDENTITY_PASSWORD_RESET_REQUESTED`, `IDENTITY_LOGIN_SUCCEEDED`, `IDENTITY_LOGIN_FAILED`.
- Ensure correlation ID propagation on responses and event envelopes.

3) RS256 + JWKS hardening

- Key generation/rotation policy, kid management, and persistence (vs. file path).
- JWKS cache headers and gateway cache coordination.

4) Repositories and session sharing

- Expose session sharing at service layer for multi‑operation transactions + outbox event storage in the same commit where needed.

5) Observability & QA

- Prometheus counters/histograms and structured logs across auth flows.
- Unit tests: hasher, issuer (with test key), repos (test DB), JWKS route.
- Integration tests: Alembic migration; outbox relay end‑to‑end.

6) Gateway integration (dev→prod switch)

- Switch API Gateway auth to JWKS RS256 in prod; HS256 fallback in dev.
- Propagate `X-Correlation-ID` end‑to‑end.

7) Packaging & Docker Compose

- Add Dockerfile/dev docker support, map DB port **5442**, container name `huleedu_identity_db`.
- Compose wiring for Identity + relay worker readiness.

---

## Open Questions (QC) for Next Session

- Topics/contracts
  - Confirm event topic usage and consumers for: login success/failed, email verification requested/verified, password reset requested.
- Auth & roles
  - Confirm role model granularity for MVP (e.g., `teacher`, `admin`) and how org tenancy should be encoded in JWT vs. looked up.
- Refresh tokens
  - Desired expiry/rotation policy and blacklist behavior; device/session metadata requirements.
- Email verification & password reset
  - Token transport (email provider), expiry durations, and verification UX dependencies.
- JWKS/RS256
  - Who manages key rotation and how often; do we need multiple active keys (grace period)? Storage of keys (KMS, secret manager?).
- Security/compliance
  - Any app‑level rate limiting for login/register to mitigate brute force?
  - Password policy requirements and breach password checks.
- Gateway
  - Timeline to move gateway to RS256 with JWKS; header naming for correlation ID; any extra claims needed.
- Database naming/ports
  - ~~Confirm `huleedu_identity` @ port 5441; container name standard.~~ **CONFIRMED:** Port **5442**, `huleedu_identity_db` container

---

## Known Pain Points / Risks

- Key management: Production RS256 requires secure key storage and rotation; need agreed KMS/secret provider.
- Session state: Session table needs lifecycle cleanup; define TTL/cleanup worker or rely on expiry checks only.
- Outbox relay: Ensure Identity's outbox relay worker is started in containerized environments and Redis notify is correctly wired.
- Event duplication: Guard idempotency for event consumption patterns downstream.
- Password hashing cost tuning: Balance Argon2id cost for performance vs. security in prod.
- Error handling consistency: New endpoints should use `huleedu_service_libs.error_handling` factories.
- ~~Import hygiene: Ruff may flag import order; run repo's standard `lint-fix` when stabilizing.~~ **RESOLVED**

---

## How to Run and Validate (Dev)

- **Migrations (from service dir) - WORKING:**
  - `cd services/identity_service`
  - `../../.venv/bin/python ../../.venv/bin/alembic upgrade head` 
  - `../../.venv/bin/python ../../.venv/bin/alembic current`
  - **Database:** `huleedu_identity` on port **5442** (operational)
  - **Tables:** users, refresh_sessions, event_outbox, email_verification_tokens, password_reset_tokens
- **Type Safety:**
  - `pdm run typecheck-all` — **PASSES** (887 source files clean)
- Check JWKS:
  - `GET /.well-known/jwks.json` — empty in dev HS256 mode, populated in production RS256 mode.

---

## Next Steps (Recommended Order)

1. Implement identity event publishers in register/login flows; wire email verification + password reset endpoints (with events).
2. Add Argon2id and RS256 issuer unit tests; add migration/integration tests and outbox relay check.
3. Add Dockerfiles and compose entries; expose DB port **5442**.
4. Switch Gateway to JWKS RS256 in prod; keep HS256 for dev.
5. Add Prometheus metrics to auth flows and publish structured errors across endpoints.

---

**Originally prepared by:** Lead Architect Agent  
**Phase 2B update:** Database Migration Resolution completed  
**Date:** 2025-08-18
