#!/usr/bin/env bash

# HuleEdu Dev Aliases & Helpers
# Source this file in your shell to enable helper functions.
#   echo 'source $(pwd)/scripts/dev-aliases.sh' >> ~/.zshrc   # or ~/.bashrc
# Or for current session only:
#   source scripts/dev-aliases.sh

_huleedu_aliases_banner_shown="${_huleedu_aliases_banner_shown:-}"
if [[ -z "$_huleedu_aliases_banner_shown" ]]; then
  echo "[huleedu] dev aliases loaded: pyp (pytest via repo root), pdmr (PDM from repo root)"
  export _huleedu_aliases_banner_shown=1
fi

# pyp: Run pytest with repo-root resolution, from any directory.
# Usage:
#   pyp services/<service>/tests/test_file.py -k 'expr' -m 'unit'
#   pyp tests/unit/test_something.py::TestClass::test_case
pyp() {
  local ROOT
  if ROOT=$(git rev-parse --show-toplevel 2>/dev/null); then
    :
  else
    # Fallback to script location/parent if not in a git repo
    local _src_dir
    if [[ -n "${BASH_SOURCE[0]:-}" ]]; then
      _src_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    else
      _src_dir="$(pwd)"
    fi
    ROOT="$(cd "$_src_dir/.." && pwd)"
  fi
  bash "$ROOT/scripts/pytest-root.sh" "$@"
}

# pdmr: Run a PDM command but pin the project to the monorepo root.
# Useful when you're in a service directory and want root scripts.
# Usage:
#   pdmr pytest-root services/... -k 'expr'
#   pdmr test-all
pdmr() {
  local ROOT
  if ROOT=$(git rev-parse --show-toplevel 2>/dev/null); then
    :
  else
    local _src_dir
    if [[ -n "${BASH_SOURCE[0]:-}" ]]; then
      _src_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    else
      _src_dir="$(pwd)"
    fi
    ROOT="$(cd "$_src_dir/.." && pwd)"
  fi
  pdm run -p "$ROOT" "$@"
}
