#!/usr/bin/env bash

# HuleEdu Dev Shell
# ------------------
# Convenience helper to open an interactive shell with the repo's .env
# exported, so DB and service env vars are available for local tools
# (pdm, diagnostics scripts, direct DB access, etc.).
#
# This script is intentionally explicit: it does NOT run automatically.
# You opt in by invoking it when you want a shell that "has .env".

set -e

SCRIPT_DIR=$(cd -- "$(dirname "$0")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)

if [ ! -f "$REPO_ROOT/.env" ]; then
    echo "No .env file found at $REPO_ROOT/.env; nothing to load." >&2
else
    # Export all variables from .env into this shell, then drop
    # into an interactive shell with those variables set.
    set -a
    # shellcheck disable=SC1091
    source "$REPO_ROOT/.env"
    set +a
fi

cd "$REPO_ROOT"
exec "$SHELL"

