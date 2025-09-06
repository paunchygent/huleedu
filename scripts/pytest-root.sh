#!/usr/bin/env bash

# Run pytest using the repository root as the reference point.
# Allows calling from any subdirectory with paths relative to repo root.
#
# Examples:
#   pdm run pytest-root tests/unit/test_auth_manager_individual.py -k 'payload'
#   pdm run pytest-root services/class_management_service/tests/test_core_logic.py
#   pdm run pytest-root tests/integration/test_foo.py::TestClass::test_case

set -euo pipefail
IFS=$'\n\t'

# Resolve repository root: prefer git, fallback to script location
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if ROOT_DIR=$(git rev-parse --show-toplevel 2>/dev/null); then
  ROOT="$ROOT_DIR"
else
  ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
fi

# Rewrite non-flag args as absolute paths relative to repo root.
# Be careful: options like -k/-m/-c/-o/-n and some long options take a value next.
REWRITTEN_ARGS=()
EXPECT_VALUE=false
# Options that consume the next argument as a value
OPTS_WITH_VALUES=( -k -m -c -o -n -p --maxfail --durations --tb --color --confcutdir --log-cli-level --log-level )

for arg in "$@"; do
  if $EXPECT_VALUE; then
    REWRITTEN_ARGS+=("$arg")
    EXPECT_VALUE=false
    continue
  fi

  # Flag handling
  if [[ "$arg" == -* ]]; then
    REWRITTEN_ARGS+=("$arg")
    # If it's a long option with inline value like --maxfail=1, continue
    if [[ "$arg" == --*=* ]]; then
      continue
    fi
    # If this flag expects a value, mark next arg as value
    for opt in "${OPTS_WITH_VALUES[@]}"; do
      if [[ "$arg" == "$opt" ]]; then
        EXPECT_VALUE=true
        break
      fi
    done
    continue
  fi

  # Absolute paths are kept
  if [[ "$arg" == /* ]]; then
    REWRITTEN_ARGS+=("$arg")
    continue
  fi

  # Handle nodeids like path::Class::test_name
  if [[ "$arg" == *::* ]]; then
    left_part="${arg%%::*}"
    right_part="${arg#*::}"
    if [[ "$left_part" != /* ]]; then
      left_part="$ROOT/$left_part"
    fi
    REWRITTEN_ARGS+=("${left_part}::${right_part}")
    continue
  fi

  # Treat as path relative to repo root
  REWRITTEN_ARGS+=("$ROOT/$arg")
done

# Run pytest with repo config explicitly
if ((${#REWRITTEN_ARGS[@]:-0} > 0)); then
  exec pdm run -p "$ROOT" -- pytest -c "$ROOT/pyproject.toml" -m "" "${REWRITTEN_ARGS[@]}"
else
  exec pdm run -p "$ROOT" -- pytest -c "$ROOT/pyproject.toml" -m ""
fi
