---
id: 'TASK-IDENTITY-RS256-JWT-ROLLOUT'
title: 'TASK: Identity RS256 JWT Rollout'
type: 'task'
status: 'research'
priority: 'medium'
domain: 'identity'
service: ''
owner_team: 'agents'
owner: ''
program: ''
created: '2025-11-16'
last_updated: '2025-11-17'
related: []
labels: []
---
# TASK: Identity RS256 JWT Rollout

**Status**: 🟡 BLOCKED (awaiting implementation)
**Priority**: HIGH
**Created**: 2025-11-13
**Type**: Infrastructure / Security

## Purpose
Switch the platform from shared-secret (HS256) JWTs to asymmetric RS256 tokens in production so only Identity can mint access tokens while every service can verify them via a published public key / JWKS. This removes the need to distribute the signing secret and aligns with the multi-service security model.

## Context
- Identity already has both issuers implemented (`DevTokenIssuer` for HS256, `Rs256TokenIssuer` for asymmetric) and DI switches based on `settings.is_production()` plus `JWT_RS256_PRIVATE_KEY_PATH`.
- Consumer services currently rely on `JWT_SECRET_KEY` via `JWTValidationSettings`, so they will reject RS256 tokens immediately.
- There is no shared JWKS endpoint consumption wired up; validators support only local secrets or PEM paths.
- We just fixed HS256 signing consistency. Before moving on, we need a tracked plan to finish the RS256 rollout without forgetting key distribution and configuration changes.

## Prerequisites
1. Generate/secure an RSA key pair for Identity (private stays in Secrets Manager / container secret, public exposed via JWKS or PEM file).
2. Decide whether services will read the public key from:
   - A mounted PEM file (`JWT_PUBLIC_KEY_PATH`), or
   - A JWKS endpoint (requires adding JWKS fetch logic to `JWTValidationSettings`).
3. Update deployment/secrets tooling to provide the new env vars (`IDENTITY_JWT_RS256_PRIVATE_KEY_PATH`, `JWT_PUBLIC_KEY_PATH` / `JWT_JWKS_URL`, etc.).

## Implementation Plan
1. **Identity configuration**
   - Create secure storage for the RSA private key (KMS, Vault, or secrets file).
   - Set `IDENTITY_JWT_RS256_PRIVATE_KEY_PATH` and `IDENTITY_JWT_RS256_PUBLIC_JWKS_KID` in prod compose/k8s manifests.
   - Ensure Identity publishes the corresponding public key via JWKS handler or static file.

2. **Consumer services**
   - Extend `JWTValidationSettings` to optionally load a PEM from disk *and/or* fetch JWKS (respect caching/backoff).
   - Update every service’s env/config to supply `JWT_PUBLIC_KEY_PATH` (or `JWT_JWKS_URL`) in production. Keep `JWT_SECRET_KEY` for dev so HS256 still works locally.
   - Document how to rotate keys (JWKS kid + caching strategy).
   - Preserve DI boundaries: services should only consume the shared validation helpers; no direct `os.getenv` or ad-hoc key parsing in business code.

3. **DI / DDD guardrails**
   - Keep the `TokenIssuer` abstraction untouched; selection between HS256/RS256 must stay in `IdentityImplementationsProvider.provide_token_issuer`.
   - Inject all key material via `Settings` so neither issuers nor validators reach into env variables directly.
   - Centralize JWKS/PEM loading logic in `libs/huleedu_service_libs.auth` to avoid duplicating crypto code inside domain modules.

4. **CI / tooling**
   - Update `scripts/validate_service_config.py` to ensure prod configs provide the appropriate public key/JWKS env vars when RS256 is enabled.
   - Add a smoke test that requests a token from Identity (with RS256) and exercises at least one admin endpoint per service to ensure signature verification works end-to-end.

5. **Rollout**
   - Stage: deploy Identity with RS256 enabled but keep HS256 fallback until consumers are updated (dual-sign if necessary or run in staging env).
   - Cutover: once all services verify RS256, remove HS256 secret from prod envs.
   - Post-cutover: rotate HS256 secrets used in dev to ensure they’re not reused in prod.

## Success Criteria
- Identity prod instances sign access/refresh tokens with RS256.
- All consumer services validate RS256 tokens using the published public key/JWKS without any manual overrides.
- `scripts/validate_service_config.py` fails builds if RS256 configs are missing.
- Smoke tests confirm that CJ admin CLI, BOS, API Gateway, etc., authenticate successfully after rollout.
- HS256 secrets are no longer shipped to production services.

## Related Documents
- `.claude/HANDOFF.md` (Phase 1 fallback + prompt contracts)
- `services/identity_service/di.py`
- `libs/huleedu_service_libs/src/huleedu_service_libs/auth/jwt_settings.py`
- `scripts/validate_service_config.py`
