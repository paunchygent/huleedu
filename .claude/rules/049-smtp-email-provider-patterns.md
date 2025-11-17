---
description: SMTP email provider configuration patterns
globs: services/email_service/**/*.py, docker-compose*.yml, .env
alwaysApply: true
---
# 090: SMTP Email Provider Patterns

## Provider Switch Pattern
```bash
# Development with SMTP
EMAIL_EMAIL_PROVIDER=smtp pdm run dev dev email_service

# Development with mock (default)
pdm run dev dev email_service

# Production SMTP
docker-compose -f docker-compose.yml -f docker-compose.services.yml -f docker-compose.smtp.yml up -d
```

## Environment Variables (.env)
```bash
EMAIL_EMAIL_PROVIDER=mock|smtp
EMAIL_SMTP_HOST=mail.privateemail.com
EMAIL_SMTP_PORT=587
EMAIL_SMTP_USERNAME=noreply@hule.education
EMAIL_SMTP_PASSWORD=dixgyg-pymje5-Jiwbar
EMAIL_SMTP_USE_TLS=true
EMAIL_SMTP_TIMEOUT=30
EMAIL_DEFAULT_FROM_EMAIL=noreply@hule.education
EMAIL_DEFAULT_FROM_NAME=HuleEdu
```

## Docker Override Pattern
```yaml
# docker-compose.dev.yml - allows SMTP override
- EMAIL_EMAIL_PROVIDER=${EMAIL_EMAIL_PROVIDER:-mock}

# docker-compose.smtp.yml - forces SMTP
- EMAIL_EMAIL_PROVIDER=smtp
```

## SMTP Success Pattern (aiosmtplib)
```python
send_errors = await smtp.send_message(msg)
if send_errors:
    if isinstance(send_errors, tuple) and len(send_errors) == 2:
        error_dict, message = send_errors
        if error_dict:  # Actual errors
            return EmailSendResult(success=False, error_message=f"Send failure: {error_dict}")
        else:  # Success response like "2.0.0 Ok: queued as 4c8ZLy5RCtz3hhS7"
            logger.info(f"SMTP server response: {message}")
```

## Test Delivery Targets
- Direct test: `pdm run python test_smtp_live.py`
- Integration: Registration triggers welcome + verification emails
- Target: `info@hule.education` (same domain, reliable delivery)

## Critical Debugging
```bash
# Check provider in container
docker exec huleedu_email_service env | grep EMAIL_EMAIL_PROVIDER

# Monitor SMTP logs
docker logs huleedu_email_service 2>&1 | grep -E "SMTP|Email sent"

# Verify credentials loaded
docker exec huleedu_email_service env | grep EMAIL_SMTP
```