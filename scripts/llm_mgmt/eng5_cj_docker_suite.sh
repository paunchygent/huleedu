#!/usr/bin/env bash

# ENG5/CJ docker test suite orchestrator.
#
# Usage (from repo root, in an env-aware shell):
#   pdm run eng5-cj-docker-suite            # run both small-net and regular-batch CJ tests
#   pdm run eng5-cj-docker-suite small-net  # only LOWER5 small-net CJ tests
#   pdm run eng5-cj-docker-suite regular    # only regular-batch CJ tests
#
# This helper:
#   - Ensures .env exists
#   - Recreates llm_provider_service and cj_assessment_service so they pick up current .env
#   - Runs the heavy CJ docker tests for the selected scenario(s)
#   - Relies on each test module’s own guards (/admin/mock-mode, settings flags) to
#     skip quickly when the active mock profile or batching-hints config does not match.

set -euo pipefail
IFS=$'\n\t'

# Wait for a Docker container to report healthy status.
wait_for_healthy() {
  local service=$1
  local max_wait=${2:-60}
  local waited=0
  echo "⏳ Waiting for $service to become healthy..."
  while [[ $waited -lt $max_wait ]]; do
    if docker ps --filter "name=huleedu_${service}" --format '{{.Status}}' | grep -q "(healthy)"; then
      echo "✅ $service is healthy"
      return 0
    fi
    sleep 2
    waited=$((waited + 2))
  done
  echo "❌ $service did not become healthy within ${max_wait}s" >&2
  return 1
}

SCRIPT_PATH="${BASH_SOURCE[0]:-$0}"
SCRIPT_DIR="$(cd "$(dirname "$SCRIPT_PATH")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../" && pwd)"

SCENARIO="${1:-all}"

cd "$REPO_ROOT"

if [[ ! -f "$REPO_ROOT/.env" ]]; then
  echo "Missing .env at $REPO_ROOT/.env – cannot run ENG5/CJ docker suite." >&2
  exit 1
fi

echo "✅ Using .env at $REPO_ROOT/.env for ENG5/CJ docker suite"

# Tests require: api_gateway_service, cj_assessment_service, llm_provider_service
# Ensure all required services are running and pick up current .env
REQUIRED_SERVICES="api_gateway_service llm_provider_service cj_assessment_service"

echo "🔄 Recreating required services: $REQUIRED_SERVICES"
# shellcheck disable=SC2086
pdm run dev-recreate $REQUIRED_SERVICES
wait_for_healthy api_gateway_service
wait_for_healthy llm_provider_service
wait_for_healthy cj_assessment_service

run_small_net_tests() {
  echo "🧪 Running LOWER5 small-net CJ docker tests..."
  pdm run pytest-root tests/functional/cj_eng5/test_cj_small_net_continuation_docker.py -m 'docker and integration' -v
}

run_regular_batch_tests() {
  echo "🧪 Running regular-batch CJ docker tests (resampling + callbacks)..."
  pdm run pytest-root tests/functional/cj_eng5/test_cj_regular_batch_resampling_docker.py -m 'docker and integration' -v
  pdm run pytest-root tests/functional/cj_eng5/test_cj_regular_batch_callbacks_docker.py -m 'docker and integration' -v
}

case "$SCENARIO" in
  small-net|small|lower5)
    run_small_net_tests
    ;;
  regular|large|generic)
    run_regular_batch_tests
    ;;
  all)
    run_small_net_tests
    run_regular_batch_tests
    ;;
  *)
    echo "Unknown scenario: $SCENARIO" >&2
    echo "Usage: $0 [all|small-net|regular]" >&2
    exit 1
    ;;
esac

echo "✅ ENG5/CJ docker suite ($SCENARIO) completed."
