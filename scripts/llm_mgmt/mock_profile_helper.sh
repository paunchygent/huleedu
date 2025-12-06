#!/usr/bin/env bash

# Helper to switch LLM Provider Service mock profiles and run parity tests.
#
# Usage (from repo root, in an env-aware shell):
#   pdm run llm-mock-profile cj-generic
#   pdm run llm-mock-profile eng5-anchor
#   pdm run llm-mock-profile eng5-lower5
#
# This script:
#   - Validates .env mock profile settings for the requested profile
#   - Restarts only the llm_provider_service dev container
#   - Runs the matching docker-backed parity test
#
# Profile correctness for tests is enforced by the
# llm_provider_service /admin/mock-mode endpoint, which reports the
# active mock configuration of the running container. This helper is
# the recommended way to keep .env and the running container in sync
# before invoking those docker-backed tests.

set -euo pipefail
IFS=$'\n\t'

# Resolve repository root robustly whether invoked directly or via PDM.
SCRIPT_PATH="${BASH_SOURCE[0]:-$0}"
SCRIPT_DIR="$(cd "$(dirname "$SCRIPT_PATH")" && pwd)"
# scripts/llm_mgmt/mock_profile_helper.sh → repo root is two levels up
REPO_ROOT="$(cd "$SCRIPT_DIR/../../" && pwd)"

PROFILE="${1:-}"
if [[ -z "$PROFILE" ]]; then
  echo "Usage: $0 <profile>" >&2
  echo "Profiles: cj-generic | eng5-anchor | eng5-lower5" >&2
  exit 1
fi

cd "$REPO_ROOT"

if [[ ! -f "$REPO_ROOT/.env" ]]; then
  echo "Missing .env at $REPO_ROOT/.env – cannot manage mock profiles." >&2
  exit 1
fi

# shellcheck disable=SC1090
source "$REPO_ROOT/.env"

case "$PROFILE" in
  cj-generic)
    EXPECTED_MODE="cj_generic_batch"
    TEST_PATH="tests/integration/test_cj_mock_parity_generic.py"
    ;;
  eng5-anchor)
    EXPECTED_MODE="eng5_anchor_gpt51_low"
    TEST_PATH="tests/integration/test_eng5_mock_parity_full_anchor.py"
    ;;
  eng5-lower5)
    EXPECTED_MODE="eng5_lower5_gpt51_low"
    TEST_PATH="tests/integration/test_eng5_mock_parity_lower5.py"
    ;;
  *)
    echo "Unknown profile: $PROFILE" >&2
    echo "Profiles: cj-generic | eng5-anchor | eng5-lower5" >&2
    exit 1
    ;;
esac

if [[ "${LLM_PROVIDER_SERVICE_USE_MOCK_LLM:-}" != "true" ]]; then
  echo "LLM_PROVIDER_SERVICE_USE_MOCK_LLM must be 'true' in .env (current: '${LLM_PROVIDER_SERVICE_USE_MOCK_LLM:-}')." >&2
  exit 1
fi

if [[ "${LLM_PROVIDER_SERVICE_MOCK_MODE:-}" != "$EXPECTED_MODE" ]]; then
  echo "LLM_PROVIDER_SERVICE_MOCK_MODE must be '$EXPECTED_MODE' for profile '$PROFILE' (current: '${LLM_PROVIDER_SERVICE_MOCK_MODE:-}')." >&2
  exit 1
fi

echo "✅ .env mock profile validated:"
echo "   LLM_PROVIDER_SERVICE_USE_MOCK_LLM=$LLM_PROVIDER_SERVICE_USE_MOCK_LLM"
echo "   LLM_PROVIDER_SERVICE_MOCK_MODE=$LLM_PROVIDER_SERVICE_MOCK_MODE"

echo "🔄 Restarting llm_provider_service to pick up profile..."
pdm run dev-recreate llm_provider_service

echo "🧪 Running parity test for profile '$PROFILE'..."
pdm run pytest-root "$TEST_PATH" -m 'docker and integration' -v

echo "✅ Profile '$PROFILE' parity test completed."
