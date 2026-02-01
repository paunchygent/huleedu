#!/usr/bin/env bash
#
# Validate production .env configuration (Hemma/shared-infra aligned).
#
# This script intentionally prints only missing/invalid keys (never secret values).

set -euo pipefail

REPO_ROOT=$(cd -- "$(dirname "$0")/.." && pwd)
cd "$REPO_ROOT"

if [ ! -f "$REPO_ROOT/.env" ]; then
  echo "❌ Missing .env at $REPO_ROOT/.env"
  echo "   Create one from env.example and set Hemma secrets locally on Hemma."
  exit 1
fi

# shellcheck disable=SC1091
set -a
source "$REPO_ROOT/.env"
set +a

fail=0

require_nonempty() {
  local key="$1"
  local val="${!key-}"
  if [ -z "${val}" ]; then
    echo "❌ Missing or empty: ${key}"
    fail=1
  fi
}

warn_if_set() {
  local key="$1"
  local val="${!key-}"
  if [ -n "${val}" ]; then
    echo "⚠️  ${key} is set; prefer explicit compose -f files for prod deploy on Hemma"
  fi
}

require_equal_if_both_set() {
  local key_a="$1"
  local key_b="$2"
  local a="${!key_a-}"
  local b="${!key_b-}"
  if [ -n "${a}" ] && [ -n "${b}" ] && [ "${a}" != "${b}" ]; then
    echo "❌ ${key_a} and ${key_b} differ (should match in prod)"
    fail=1
  fi
}

echo "🔎 Validating production .env (no secrets printed)"

require_nonempty "HULEEDU_ENVIRONMENT"
require_nonempty "ENVIRONMENT"

if [ "${HULEEDU_ENVIRONMENT-}" != "production" ]; then
  echo "❌ HULEEDU_ENVIRONMENT must be 'production' (got: ${HULEEDU_ENVIRONMENT-<unset>})"
  fail=1
fi

if [ "${ENVIRONMENT-}" != "production" ]; then
  echo "❌ ENVIRONMENT must be 'production' (got: ${ENVIRONMENT-<unset>})"
  fail=1
fi

require_nonempty "HULEEDU_DB_USER"
require_nonempty "HULEEDU_PROD_DB_PASSWORD"
require_nonempty "HULEEDU_INTERNAL_API_KEY"

# JWT secrets (API Gateway uses JWT_SECRET_KEY in docker-compose.services.yml)
require_nonempty "JWT_SECRET_KEY"
require_equal_if_both_set "JWT_SECRET_KEY" "API_GATEWAY_JWT_SECRET_KEY"

# Avoid COMPOSE_FILE drift (Hemma uses explicit -f layering)
warn_if_set "COMPOSE_FILE"

# LLM keys: require at least one when not explicitly mocked
if [ "${LLM_PROVIDER_SERVICE_USE_MOCK_LLM-}" = "true" ]; then
  echo "ℹ️  LLM_PROVIDER_SERVICE_USE_MOCK_LLM=true; skipping provider API key checks"
else
  if [ -z "${OPENAI_API_KEY-}" ] && [ -z "${ANTHROPIC_API_KEY-}" ] && [ -z "${OPENROUTER_API_KEY-}" ]; then
    echo "❌ Missing provider API key: set one of OPENAI_API_KEY / ANTHROPIC_API_KEY / OPENROUTER_API_KEY"
    fail=1
  fi
fi

if [ $fail -ne 0 ]; then
  echo ""
  echo "❌ Production .env validation failed"
  exit 1
fi

echo "✅ Production .env looks sane"

