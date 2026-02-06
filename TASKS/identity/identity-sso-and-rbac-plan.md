---
id: identity-sso-and-rbac-plan
title: 'Identity: OIDC SSO + RBAC/ABAC (Weeks 1–3)'
type: task
status: proposed
priority: medium
domain: identity
service: ''
owner_team: agents
owner: ''
program: ''
created: '2025-08-23'
last_updated: '2026-02-01'
related: []
labels: []
---
Objective

- Implement OIDC SSO (Google for Education first), introduce RBAC/ABAC role model, and enforce in API Gateway + services.

Scope

- In: OIDC login, JWKS federation, role claims propagation, gateway authz middleware, identity roles administration endpoints.
- Out: SAML (tracked separately for later), SCIM (captured as stretch goal).

References

- Identity service: `services/identity_service/*` (routes, di, models)
- Gateway: `services/api_gateway_service/app/*`, `routers/*`
- Shared: `libs/huleedu_service_libs/error_handling/*`, `libs/common_core/identity_models.py`
- Rules: `020-architectural-mandates`, `042-async-patterns-and-di`, `048-structured-error-handling-standards`, `070-testing-and-quality-assurance`

Deliverables

1. OIDC SSO: `.well-known/openid-configuration` support, OIDC client config (Google), code/exchange + PKCE, session issuance.
2. RBAC/ABAC: Role model (student/teacher/admin/district_admin), optional attributes for ABAC (tenant_id, org_id).
3. Gateway enforcement: AuthN (existing) + AuthZ middleware with role/claims checks; per-route role guards.
4. Admin endpoints: Manage roles/assignments, minimal UI via API.
5. Tests: E2E login, token introspection, role-protected route access, regression.

Work Packages

1) OIDC Provider Integration (Identity)
   - Add provider config and discovery: `services/identity_service/api/well_known_routes.py` (extend for OIDC metadata)
   - Implement `/v1/auth/oidc/callback` exchange and session issuance.
   - Store external subject mapping ➜ internal user id.
   - Acceptance: OIDC login yields JWT with roles and tenant_id claims; JWKS validation works.

2) Role Model + Persistence (Identity)
   - Extend `services/identity_service/models_db.py` with role tables and user_role mappings; Alembic migration.
   - Update `domain_handlers/authentication_handler.py` to inject roles into tokens.
   - Acceptance: Assign/remove role endpoints; role appears in token introspection; tests pass.

3) Gateway AuthZ Middleware (Gateway)
   - Add role/attribute checks in `services/api_gateway_service/app/middleware.py` and per-router guards.
   - Map external roles ➜ internal ACL in routers.
   - Acceptance: Protected endpoints 403 without role; 200 with role.

4) Tenant/Org Propagation
   - Add `tenant_id` (if present) to JWT and forward as header to downstream services.
   - Update service consumers to trust gateway-issued claims via internal key.
   - Acceptance: Downstream services receive tenant_id and role in request context.

5) Tests + Docs
   - Add tests: `services/identity_service/tests/*`, `services/api_gateway_service/tests/test_auth.py` (expand)
   - Docs: Identity README (flows), Gateway README (guards), update `docs/`.

Dependencies

- Google OIDC credentials; secure callback URL; `.env` entries.

Risks/Mitigations

- Token audience/scope mismatch ➜ strict audience checks and e2e tests.
- Role drift ➜ centralize role definitions in identity and expose via introspection endpoint.

Definition of Done

- OIDC login end-to-end works; RBAC enforced at gateway; identity role admin endpoints live; tests pass (`pdm run test-all`).
