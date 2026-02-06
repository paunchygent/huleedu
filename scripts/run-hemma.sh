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

# Encode one argument into a single-token transport-safe string.
encode_arg_b64() {
  printf '%s' "$1" | base64 | tr -d '\n'
}

# Accept both invocation forms:
# - scripts/run-hemma.sh -- <cmd> [args...]
# - scripts/run-hemma.sh -- --shell "<shell command>"
# - scripts/run-hemma.sh --shell "<shell command>"
if [ "${1-}" = "--" ]; then
  shift
fi
if [ "${1-}" = "--shell" ]; then
  MODE="shell"
  shift
fi

if [ "$MODE" = "shell" ]; then
  if [ "$#" -ne 1 ]; then
    echo "Usage: scripts/run-hemma.sh --shell \"<remote shell command string>\"" >&2
    exit 2
  fi
  shell_cmd_b64="$(encode_arg_b64 "$1")"
  ssh "$REMOTE_HOST" /bin/bash -s -- "$REMOTE_REPO_ROOT" "$MODE" "$shell_cmd_b64" <<'EOF'
set -euo pipefail
repo_root="$1"
mode="$2"
shell_cmd_b64="$3"
cd "$repo_root"
if [ "$mode" != "shell" ]; then
  echo "Internal mode error: expected shell mode." >&2
  exit 3
fi
shell_cmd="$(printf '%s' "$shell_cmd_b64" | base64 -d)"
exec /bin/bash -lc "$shell_cmd"
EOF
else
  if [ "$#" -lt 1 ]; then
    echo "Usage: scripts/run-hemma.sh -- <remote-command> [args...]" >&2
    exit 2
  fi
  encoded_args=()
  for arg in "$@"; do
    encoded_args+=("$(encode_arg_b64 "$arg")")
  done
  ssh "$REMOTE_HOST" /bin/bash -s -- "$REMOTE_REPO_ROOT" "$MODE" "${encoded_args[@]}" <<'EOF'
set -euo pipefail
repo_root="$1"
mode="$2"
shift 2
cd "$repo_root"
if [ "$mode" != "argv" ]; then
  echo "Internal mode error: expected argv mode." >&2
  exit 3
fi
decoded_args=()
for encoded_arg in "$@"; do
  decoded_args+=("$(printf '%s' "$encoded_arg" | base64 -d)")
done
exec "${decoded_args[@]}"
EOF
fi
