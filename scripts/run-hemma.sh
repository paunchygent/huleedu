#!/usr/bin/env bash
#
# Canonical Hemma remote runner.
# - Always `cd` to canonical Hemma repo root before execution.
# - Keeps local env-loading concerns separate from remote commands.
#
# Usage:
#   scripts/run-hemma.sh -- <remote-command> [args...]
#   scripts/run-hemma.sh --shell "<remote shell command string>"
#   HULEEDU_HEMMA_HOST=hemma scripts/run-hemma.sh -- sudo docker ps

set -euo pipefail

if [ "$#" -lt 1 ]; then
  echo "Usage: scripts/run-hemma.sh -- <remote-command> [args...]" >&2
  echo "   or: scripts/run-hemma.sh --shell \"<remote shell command string>\"" >&2
  exit 2
fi

REMOTE_HOST="${HULEEDU_HEMMA_HOST:-hemma}"
REMOTE_REPO_ROOT="${HULEEDU_HEMMA_REPO_ROOT:-/home/paunchygent/apps/huleedu}"
MODE="argv"
if [ "${1-}" = "--shell" ]; then
  MODE="shell"
  shift
elif [ "${1-}" = "--" ]; then
  shift
fi

if [ "$MODE" = "shell" ]; then
  if [ "$#" -ne 1 ]; then
    echo "Usage: scripts/run-hemma.sh --shell \"<remote shell command string>\"" >&2
    exit 2
  fi
  ssh "$REMOTE_HOST" /bin/bash -s -- "$REMOTE_REPO_ROOT" "$MODE" "$1" <<'EOF'
set -euo pipefail
repo_root="$1"
mode="$2"
shell_cmd="$3"
cd "$repo_root"
if [ "$mode" != "shell" ]; then
  echo "Internal mode error: expected shell mode." >&2
  exit 3
fi
eval "$shell_cmd"
EOF
else
  if [ "$#" -lt 1 ]; then
    echo "Usage: scripts/run-hemma.sh -- <remote-command> [args...]" >&2
    exit 2
  fi
  ssh "$REMOTE_HOST" /bin/bash -s -- "$REMOTE_REPO_ROOT" "$MODE" "$@" <<'EOF'
set -euo pipefail
repo_root="$1"
mode="$2"
shift 2
cd "$repo_root"
if [ "$mode" != "argv" ]; then
  echo "Internal mode error: expected argv mode." >&2
  exit 3
fi
"$@"
EOF
fi
