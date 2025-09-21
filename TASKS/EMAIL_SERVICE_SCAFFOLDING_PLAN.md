# Email Service – Scaffolding and Implementation Plan

Purpose: Implement a production‑ready, event‑driven Email Service that conforms to HuleEdu architectural rules, reuses shared libraries, and aligns data models with `common_core`. This plan follows existing Quart service patterns in the repo (DI with Dishka, event outbox, domain handlers, tests) and maps boundary interactions with Identity and other services.

## Objectives

- Provide transactional email delivery for verification and password reset flows.
- Consume identity and generic email events; emit delivery outcomes.
- Maintain strict schema alignment with `common_core` contracts and `ProcessingEvent` topics.
- Use Outbox pattern for business‑critical event publication.
- Offer minimal dev HTTP endpoints for local testing; primary interface is events.

## Scope

- Service: `services/email_service/` (Quart app + Kafka worker)
- Features: verification and password reset emails; generic notification channel
- Contracts: reuse `common_core.emailing_models` and identity events from `common_core.identity_models`
- Persistence: message store + outbox in service‑local Postgres
- Observability: Prometheus metrics, structured logging, correlation IDs

Non‑Scope (initial):
- Provider webhooks (bounce/complaint callbacks)
- Multi‑locale template catalogs (single locale/template set to start)
- Bulk/batched email

## Architectural Alignment

- Pattern: Event‑driven microservice (Rules 010, 020, 030)
- HTTP: Quart app with `app.py < 150 LoC`; blueprints under `api/` (Rule 042)
- Worker: `worker_main.py` + `kafka_consumer.py` + `event_processor.py`
- DI: Protocols in `protocols.py`, providers in `di.py`; `APP` (stateless) and `REQUEST` scopes
- Outbox: Use `huleedu_service_libs.outbox` for event publishing; share DB session for atomic writes
- Errors: Use `huleedu_service_libs.error_handling` factories (Rule 048)
- Types: Pydantic models + mypy compliance (Rule 050)

## Directory Structure (single app pattern)

```
services/email_service/
  app.py                      # DI init, blueprint registration, startup/shutdown hooks
  startup_setup.py            # DI container, metrics, tracing, start Kafka consumer + outbox
  config.py                   # Pydantic settings
  metrics.py                  # Prometheus counters/histograms
  protocols.py                # Provider, template renderer, repository interfaces
  di.py                       # Providers (APP/REQUEST scopes)
  models_db.py                # email_messages; outbox shared session
  api/
    dev_routes.py             # optional: /dev/send, /health
  implementations/
    provider_console_impl.py  # dev provider (stdout)
    provider_sendgrid_impl.py # example real provider (scaffold)
    template_renderer_impl.py # jinja2 renderer
    repository_impl.py        # message persistence
    event_publisher_impl.py   # Outbox publisher for EmailSent/Failed
  kafka_consumer.py           # consumer class; started from startup_setup
  event_processor.py          # map events→email send; emit outcomes
  alembic/
  tests/
```

## Contracts and Topics (common_core)

Use existing models and enums; do not duplicate.

- Identity events (`libs/common_core/src/common_core/identity_models.py`):
  - `EmailVerificationRequestedV1 { user_id, email, verification_token, expires_at, correlation_id }`
  - `PasswordResetRequestedV1 { user_id, email, token_id, expires_at, correlation_id }`
- Email events (`libs/common_core/src/common_core/emailing_models.py`):
  - `NotificationEmailRequestedV1 { message_id, template_id, to, variables, category, correlation_id }`
  - `EmailSentV1 { message_id, provider, sent_at, correlation_id }`
  - `EmailDeliveryFailedV1 { message_id, provider, failed_at, reason, correlation_id }`
- Topics (`libs/common_core/src/common_core/event_enums.py` + `topic_name()`):
  - Identity → `ProcessingEvent.IDENTITY_EMAIL_VERIFICATION_REQUESTED`, `ProcessingEvent.IDENTITY_PASSWORD_RESET_REQUESTED`
  - Email → `ProcessingEvent.EMAIL_NOTIFICATION_REQUESTED`, `ProcessingEvent.EMAIL_SENT`, `ProcessingEvent.EMAIL_DELIVERY_FAILED`

## Event Flows

1) Identity‑driven flows (primary)
- Consume: `IDENTITY_EMAIL_VERIFICATION_REQUESTED` with `EmailVerificationRequestedV1`
  - Render “verify email” template with link `frontend_base_url/verify?token=verification_token`
  - Send via provider; persist message record
  - Emit `EMAIL_SENT` or `EMAIL_DELIVERY_FAILED`
- Consume: `IDENTITY_PASSWORD_RESET_REQUESTED` with `PasswordResetRequestedV1`
  - Render “password reset” template with link `frontend_base_url/reset-password?token=token_id`
  - Send; emit delivery outcome events as above

2) Generic notification flow (secondary)
- Consume: `EMAIL_NOTIFICATION_REQUESTED` with `NotificationEmailRequestedV1`
  - Resolve `template_id`, interpolate `variables`, send and emit outcome

Notes
- Email Service never mutates Identity DB; it only sends and publishes outcomes.
- All events must be wrapped in `EventEnvelope` at publish time via outbox.

## HTTP Endpoints (dev/testing)

- `GET /health` → `{ status: "ok" }`
- `POST /v1/dev/send` (dev‑only): `{ to, template_id, variables?, category?, subjectOverride? }` → triggers send via internal path; returns 202
  - Guard behind `HULEEDU_ENVIRONMENT != production`
  - Optional bearer: require `Authorization: Bearer $EMAIL_DEV_TOKEN`
  - Minimal validation: email format, required fields

## Protocols (Rule 042)

```python
# services/email_service/protocols.py
from __future__ import annotations
from typing import Protocol, Mapping, Any, Optional

class EmailProvider(Protocol):
    async def send_email(self, to: str, subject: str, html: str, text: Optional[str] = None) -> str: ...

class TemplateRenderer(Protocol):
    async def render(self, template_id: str, variables: Mapping[str, Any]) -> tuple[str, str]: ...  # (subject, html)

class EmailRepository(Protocol):
    async def save_message(self, message: dict) -> str: ...  # returns message_id
    async def mark_sent(self, message_id: str, provider: str) -> None: ...
    async def mark_failed(self, message_id: str, provider: str, reason: str) -> None: ...

class EmailEventPublisher(Protocol):
    async def publish_sent(self, message_id: str, provider: str, correlation_id: str) -> None: ...
    async def publish_failed(self, message_id: str, provider: str, reason: str, correlation_id: str) -> None: ...
```

Scopes
- `APP`: provider client, renderer (stateless), settings
- `REQUEST`: DB session/repository

## Persistence

Tables (Alembic migrations created from the service directory):
- `email_messages(id, to, template_id, variables_json, status, provider, provider_message_id, last_error, created_at, updated_at)`
- `outbox(...)` via shared lib; ensure atomic writes when emitting events

Indexes
- `email_messages(status)` for monitoring
- Outbox: partial index on `(published_at, topic, created_at)` where `published_at IS NULL` (per rules)

## Configuration (Pydantic Settings)

`services/email_service/config.py`:
- Core:
  - `EMAIL_PROVIDER` (e.g., `console`, `smtp`)
  - `EMAIL_FROM`, `EMAIL_REPLY_TO`
  - `FRONTEND_BASE_URL` (for verify/reset links)
  - `EMAIL_TEMPLATE_DIR` (e.g., `services/email_service/templates`)
  - `EMAIL_DEV_TOKEN` (optional, protects dev route)
- SMTP (Namecheap Private Email):
  - `SMTP_HOST` (e.g., `mail.privateemail.com`)
  - `SMTP_PORT` (587 for STARTTLS or 465 for SSL/TLS)
  - `SMTP_USERNAME` (full mailbox, e.g., `no-reply@yourdomain.tld`)
  - `SMTP_PASSWORD`
  - `SMTP_USE_TLS` (true for 587)
  - `SMTP_USE_SSL` (true for 465)
- Provider‑specific (if later using API providers): `SENDGRID_API_KEY`, `POSTMARK_TOKEN`, etc.

Respect `HULEEDU_ENVIRONMENT` and separate dev/prod config per Rule 080. Combine HTTP and Kafka lifecycle in `startup_setup.initialize_services` and `shutdown_services`, mirroring patterns in `batch_orchestrator_service` and `batch_conductor_service`.

## Metrics

- Counters: `email_send_attempt_total`, `email_send_success_total`, `email_send_failure_total`
- Histogram: `email_send_duration_seconds`
- Labels: `template_id`, `provider`, `category`

## Provider: Namecheap Private Email (SMTP)

- Server: `mail.privateemail.com`
- Ports: `587` (STARTTLS) or `465` (SSL/TLS)
- Auth: `SMTP_USERNAME` is full email address; password is mailbox password
- Alignment: `EMAIL_FROM` domain must match authenticated domain (DMARC/SPF alignment)
- Headers: set `Message-ID`, `Date`, optional `List-Unsubscribe`, and provide `multipart/alternative` (text + HTML)

## Business Logic Orchestration

`event_processor.py` responsibilities:
- Map incoming events to a canonical send request:
  - Verification: template_id=`verify_email`, variables={ email, link, expires_at }
  - Reset: template_id=`password_reset`, variables={ email, link, expires_at }
  - Generic: use as‑is from `NotificationEmailRequestedV1`
- Call renderer → provider → repository → publish outcome via outbox
- Always include `correlation_id` from inbound event in outcome events

## Compliance with Shared Libraries

- Outbox publishing via `huleedu_service_libs.outbox`
- Errors via `huleedu_service_libs.error_handling`
- Logging via `huleedu_service_libs.logging_utils.create_service_logger`
- Event envelopes via `common_core.events.envelope.EventEnvelope`
- Topics via `common_core.event_enums.ProcessingEvent` + `topic_name()`
- Contracts strictly from `common_core.emailing_models` and `common_core.identity_models`

## DNS & Deliverability Checklist

- MX: point domain to Namecheap’s mail servers
- SPF: publish TXT with provider include (e.g., `v=spf1 include:spf.privateemail.com ~all`) or exact value provided by Namecheap
- DKIM: enable in Namecheap email admin; publish selector TXT records
- DMARC: start with `v=DMARC1; p=none; rua=mailto:dmarc-reports@yourdomain.tld; ruf=mailto:dmarc-failures@yourdomain.tld; fo=1`
  - After validation, move to `p=quarantine`, then `p=reject`
- Mailboxes: create `no-reply@yourdomain` (sender) and `test@yourdomain` (receive testing)

## Boundary Interactions and Model Alignment

- Inbound:
  - `EmailVerificationRequestedV1` (Identity) → uses fields `verification_token`, `expires_at`; must generate link accordingly
  - `PasswordResetRequestedV1` (Identity) → uses `token_id`
  - `NotificationEmailRequestedV1` (Any service)
- Outbound:
  - `EmailSentV1`, `EmailDeliveryFailedV1` (Email)
- No DB coupling across services; only event contracts align at boundaries.

## Security & Privacy

- Disable `/v1/dev/send` in production; optionally require `EMAIL_DEV_TOKEN` in non‑prod
- Redact recipient in logs (log domain only), never log credentials or tokens
- Store SMTP credentials in secrets; mount only for the email_service container

## Testing & Validation (Real Send/Receive)

- Configure DNS + mailboxes; set env as above
- Use `/v1/dev/send` to send to Gmail/Outlook/Yahoo; verify inbox/spam placement
- Validate headers and authentication with mail‑tester.com
- Receive test: send from external to `test@yourdomain` and read via Namecheap webmail/IMAP
- Links: confirm verification/reset links render and expire correctly

## Reliability: Retries & Backoff

- On transient SMTP errors, retry with exponential backoff (cap attempts)
- Persist failure reason; emit `EMAIL_DELIVERY_FAILED` with `correlation_id`
- Throttle initial volumes; respect provider hourly/daily limits

## Content & Headers Guidance

- Keep templates simple; include a plain‑text alternative
- Avoid URL shorteners; use branded domain in links
- Add `List-Unsubscribe` mailto header when appropriate

## Testing Strategy

- Unit:
  - Template rendering with variable substitution and Swedish characters
  - Provider adapter (console + stubbed real provider) behavior
  - Repository persistence and status transitions
  - Event processor mapping from inbound events to send requests
- Contract:
  - Validate `EmailSentV1`/`EmailDeliveryFailedV1` payloads
  - Validate consumption of `EmailVerificationRequestedV1`/`PasswordResetRequestedV1`
- Integration (fast):
  - End‑to‑end worker test with in‑memory provider and fake consumer
- Markers: use `@pytest.mark.integration` for provider/network tests

## Rollout Plan (single app lifecycle)

1) Scaffold service structure (no separate worker) and DI
2) Implement console provider + jinja2 renderer + repository
3) Implement event processor mappings and outbox publisher
4) Start Kafka consumer in `startup_setup.initialize_services` with background task + monitoring
5) Add health/dev endpoints and metrics
6) Add Alembic migrations for `email_messages` and ensure outbox
7) Add unit + contract tests; run `typecheck-all` and fast tests
8) Wire docker compose: add service container, Kafka topic subscriptions, env vars
9) Validate Identity → Email end‑to‑end in dev (`pdm run dev-start email_service`)

## Risks & Decisions

- Token field names differ (`verification_token` vs `token_id`): handled in mapping logic
- Templating i18n not included initially; design templates with variables to enable later localization
- Provider choice abstracted behind protocol; production adapter can be added without changing core logic

## Acceptance Criteria

- Service builds and starts; `/health` returns 200
- On `IDENTITY_EMAIL_VERIFICATION_REQUESTED`, service sends an email and emits `EMAIL_SENT` (or `EMAIL_DELIVERY_FAILED` on failure)
- On `IDENTITY_PASSWORD_RESET_REQUESTED`, service sends an email and emits outcome events
- On `EMAIL_NOTIFICATION_REQUESTED`, service renders template and emits outcome events
- All published events wrapped in `EventEnvelope` with correct `event_type` (`topic_name(...)`) and `correlation_id`
- Schema compliance verified via contract tests; mypy `typecheck-all` passes without ignores/casts

## TODO Checklist

- [ ] Create service skeleton and DI providers
- [ ] Implement console provider adapter
- [ ] Implement template renderer (jinja2)
- [ ] Implement repository + migrations
- [ ] Implement event processor + outbox publisher
- [ ] Add health and dev endpoints
- [ ] Add metrics counters/histogram
- [ ] Write unit and contract tests
- [ ] Update docker compose with service and topics
- [ ] Validate with Identity flows in dev
