#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

pdm run prompt-cache-benchmark --fixture full "$@"
