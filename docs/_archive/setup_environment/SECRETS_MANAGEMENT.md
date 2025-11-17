# HuleEdu Secrets Management Guide

## Current State & Security Issues

### 🚨 Critical Security Problems

- API keys are hardcoded in `docker-compose.yml`
- Secrets are committed to version control
- Same credentials used across all environments
- No secret rotation or access control

## Production-Ready Solution

### Phase 1: Immediate Security Fix (🔥 **URGENT**)

#### Step 1: Create Environment File

1. Copy `env.example` to `.env` in the project root
2. Fill in your actual API keys and secrets
3. **NEVER commit `.env` to version control**

#### Step 2: Update Docker Compose

Replace hardcoded values in `docker-compose.yml`:

```yaml
# BEFORE (INSECURE):
- OPENAI_API_KEY=sk-proj-954feuR9...

# AFTER (SECURE):
- OPENAI_API_KEY=${OPENAI_API_KEY}
```

#### Step 3: Environment Variable Substitution

Docker Compose will automatically read from `.env` file in the same directory.

### Phase 2: Environment Separation

#### Development Setup

```bash
# .env.development
ENVIRONMENT=development
CJ_ASSESSMENT_SERVICE_USE_MOCK_LLM=true
LOG_LEVEL=DEBUG
```

#### Staging Setup

```bash
# .env.staging
ENVIRONMENT=staging
CJ_ASSESSMENT_SERVICE_USE_MOCK_LLM=false
LOG_LEVEL=INFO
```

#### Production Setup

```bash
# .env.production
ENVIRONMENT=production
CJ_ASSESSMENT_SERVICE_USE_MOCK_LLM=false
LOG_LEVEL=WARNING
```

### Phase 3: Production Infrastructure

#### Option A: AWS Secrets Manager

```bash
# Install AWS CLI
aws secretsmanager get-secret-value \
  --secret-id prod/huledu/openai-api-key \
  --query SecretString --output text
```

#### Option B: HashiCorp Vault

```bash
# Vault integration
vault kv get -field=api_key secret/huledu/openai
```

#### Option C: Kubernetes Secrets

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: huledu-api-keys
type: Opaque
data:
  openai-api-key: <base64-encoded-key>
```

## Implementation Steps

### Immediate Actions (Next 30 minutes)

1. **Create `.env` file:**

   ```bash
   cp env.example .env
   # Edit .env with your actual values
   ```

2. **Update `docker-compose.yml`:**
   Replace all hardcoded API keys with `${VARIABLE_NAME}` syntax

3. **Test the setup:**

   ```bash
   docker compose down --remove-orphans
   docker compose up -d cj_assessment_service
   docker compose logs cj_assessment_service
   ```

4. **Verify `.env` is ignored:**

   ```bash
   git status  # Should not show .env file
   ```

### Environment-Specific Configurations

#### For Development

- Use mock LLM services when possible
- Lower resource limits
- Verbose logging

#### For Production

- Real API keys with appropriate rate limits
- Higher resource allocations
- Error-level logging only
- Enable all security features

## Security Best Practices

### ✅ Do's

- Use environment-specific configurations
- Rotate API keys regularly
- Monitor API usage and costs
- Use least-privilege access
- Audit secret access logs
- Use external secrets management in production

### ❌ Don'ts

- Never commit secrets to version control
- Don't use the same keys across environments
- Don't share API keys in chat/email
- Don't hardcode secrets in source code
- Don't use production keys in development

## Secret Rotation Strategy

### Monthly Rotation

1. Generate new API keys
2. Update secrets management system
3. Deploy updated configurations
4. Revoke old keys
5. Monitor for any failures

### Emergency Rotation

1. Immediately revoke compromised keys
2. Generate new keys
3. Emergency deployment
4. Security incident review

## Monitoring & Alerting

### Key Metrics to Track

- API key usage patterns
- Failed authentication attempts
- Secret access logs
- Cost monitoring for LLM APIs

### Alerts to Configure

- Unusual API usage spikes
- Authentication failures
- Secret rotation reminders
- Cost threshold breaches

## Compliance Considerations

### For Enterprise Deployment

- GDPR compliance for EU data
- SOC 2 Type II certification
- Regular security audits
- Penetration testing
- Data encryption at rest and in transit

## Migration Timeline

### Week 1: Immediate Security

- [x] Create `.env` template
- [ ] Update `docker-compose.yml`
- [ ] Test environment variable substitution
- [ ] Document new process

### Week 2-3: Environment Separation

- [ ] Create environment-specific configs
- [ ] Set up staging environment
- [ ] CI/CD pipeline integration
- [ ] Testing and validation

### Month 2-3: Production Infrastructure

- [ ] Choose secrets management solution
- [ ] Implement secret rotation
- [ ] Set up monitoring
- [ ] Security audit and penetration testing

## Cost Considerations

### LLM API Costs

- OpenAI: $0.01-0.02 per 1K tokens
- Anthropic: $0.25-1.25 per 1M tokens
- Google: $0.125-0.375 per 1M characters

### Secrets Management Costs

- AWS Secrets Manager: $0.40/secret/month + $0.05/10K requests
- HashiCorp Vault: $0.03/secret/hour (cloud)
- Azure Key Vault: $0.03/transaction + storage costs

## Emergency Procedures

### If Secrets Are Compromised

1. **Immediate:** Revoke all compromised keys
2. **Within 1 hour:** Generate new keys
3. **Within 4 hours:** Deploy new configurations  
4. **Within 24 hours:** Complete security review
5. **Within 1 week:** Implement additional safeguards

### Contact Information

- Security Team: <security@huledu.com>
- DevOps Lead: <devops@huledu.com>
- Emergency Hotline: [Your emergency contact]

---

**Remember: Security is everyone's responsibility. When in doubt, ask the security team.**
