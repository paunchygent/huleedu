#!/usr/bin/env bash
#
# Canonical local PDM runner.
# - Runs from repo root.
# - Loads .env into the current process environment.
# - Executes `pdm run ...` with provided arguments.
#
# Usage:
#   scripts/run-local-pdm.sh <pdm-script-or-command> [args...]

set -euo pipefail

if [ "$#" -lt 1 ]; then
  echo "Usage: scripts/run-local-pdm.sh <pdm-script-or-command> [args...]" >&2
  exit 2
fi

SCRIPT_DIR=$(cd -- "$(dirname "$0")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)

cd "$REPO_ROOT"

if [ -f ".env" ]; then
  set -a
  # shellcheck disable=SC1091
  source ".env"
  set +a
fi

exec pdm run "$@"

