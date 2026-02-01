# LLM Provider Service - Environment Variables

## Overview

The LLM Provider Service supports flexible environment variable naming to work in multiple contexts:
- **Docker containers** (prefixed with `LLM_PROVIDER_SERVICE_`)
- **Local development** (unprefixed, backward compatible)
- **CI/CD pipelines** (both formats supported)

## API Key Configuration

All LLM provider API keys support **dual naming patterns** using Pydantic v2's `AliasChoices`:

### OpenAI

```bash
# Option 1: Prefixed (Docker container - docker-compose injects this)
LLM_PROVIDER_SERVICE_OPENAI_API_KEY=sk-...

# Option 2: Unprefixed (local .env, backward compatible)
OPENAI_API_KEY=sk-...
```

### Anthropic

```bash
# Option 1: Prefixed (Docker container)
LLM_PROVIDER_SERVICE_ANTHROPIC_API_KEY=sk-ant-...

# Option 2: Unprefixed (local .env)
ANTHROPIC_API_KEY=sk-ant-...
```

### Google (Gemini)

```bash
# Option 1: Prefixed (Docker container)
LLM_PROVIDER_SERVICE_GOOGLE_API_KEY=your-key
LLM_PROVIDER_SERVICE_GOOGLE_PROJECT_ID=your-project

# Option 2: Unprefixed (local .env)
GOOGLE_API_KEY=your-key
GOOGLE_PROJECT_ID=your-project
```

### OpenRouter

```bash
# Option 1: Prefixed (Docker container)
LLM_PROVIDER_SERVICE_OPENROUTER_API_KEY=sk-or-...

# Option 2: Unprefixed (local .env)
OPENROUTER_API_KEY=sk-or-...
```

## Priority Order

When **both** prefixed and unprefixed variables are set:
1. **Prefixed** takes precedence (Docker container environment)
2. **Unprefixed** is used as fallback (local development)

This ensures Docker deployments work correctly while maintaining backward compatibility.

## Architecture Pattern

This follows the established pattern from `services/api_gateway_service/config.py`:

```python
from pydantic import AliasChoices, Field, SecretStr

OPENAI_API_KEY: SecretStr = Field(
    default=SecretStr(""),
    validation_alias=AliasChoices(
        "LLM_PROVIDER_SERVICE_OPENAI_API_KEY",  # Docker (prefixed)
        "OPENAI_API_KEY",                        # Local (unprefixed)
    ),
    description="OpenAI API key for GPT models",
)
```

## Docker Compose Integration

In `docker-compose.services.yml`, environment variables are mapped:

```yaml
llm_provider_service:
  environment:
    - LLM_PROVIDER_SERVICE_OPENAI_API_KEY=${OPENAI_API_KEY}
    - LLM_PROVIDER_SERVICE_ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
    - LLM_PROVIDER_SERVICE_GOOGLE_API_KEY=${GOOGLE_API_KEY}
    - LLM_PROVIDER_SERVICE_OPENROUTER_API_KEY=${OPENROUTER_API_KEY}
```

This means:
1. Docker Compose reads unprefixed vars from `.env` file
2. Passes them to container with prefixed names
3. Pydantic Settings loads them via `AliasChoices`

## CLI Usage

### Inside Docker Container

```bash
# Run CLI inside the container
docker exec huleedu_llm_provider_service pdm run llm-check-models --provider openai

# The container has prefixed env vars injected by docker-compose
```

### Outside Docker (Local Development)

```bash
# Ensure .env has unprefixed keys
echo "OPENAI_API_KEY=sk-..." >> .env

# Run CLI from repo root
pdm run llm-check-models --provider openai
```

### GitHub Actions / CI

```bash
# Set GitHub secrets (unprefixed)
# Secrets: OPENAI_API_KEY, ANTHROPIC_API_KEY, etc.

# In workflow, they can be used either way:
env:
  OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
  # OR
  LLM_PROVIDER_SERVICE_OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
```

## Testing

Unit tests verify both patterns work correctly:

```bash
# Run configuration loading tests
pdm run pytest-root services/llm_provider_service/tests/unit/test_config_env_loading.py -v
```

## Troubleshooting

### CLI says "API key not found"

1. **Check environment variable is set:**
   ```bash
   echo $OPENAI_API_KEY
   # OR
   echo $LLM_PROVIDER_SERVICE_OPENAI_API_KEY
   ```

2. **Verify .env file exists:**
   ```bash
   cat .env | grep OPENAI_API_KEY
   ```

3. **Run inside Docker container:**
   ```bash
   docker exec huleedu_llm_provider_service env | grep OPENAI
   ```

### Docker container can't authenticate

1. **Verify .env file at repo root:**
   ```bash
   ls -la .env
   ```

2. **Check docker-compose loaded env vars:**
   ```bash
   docker-compose config | grep OPENAI_API_KEY
   ```

3. **Inspect container environment:**
   ```bash
   docker inspect huleedu_llm_provider_service | grep -A 10 "Env"
   ```

## Best Practices

1. **Use unprefixed format in `.env` files** for simplicity
2. **Let docker-compose handle prefixing** automatically
3. **Never commit `.env` files** with real API keys
4. **Use GitHub Secrets** for CI/CD pipelines
5. **Test locally before Docker** to isolate config issues

## References

- Pydantic v2 Settings: <https://docs.pydantic.dev/latest/concepts/pydantic_settings/>
- API Gateway pattern: `services/api_gateway_service/config.py:96-114`
- Pydantic AliasChoices: <https://docs.pydantic.dev/latest/api/pydantic/#pydantic.AliasChoices>
