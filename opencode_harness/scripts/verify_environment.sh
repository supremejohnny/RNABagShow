#!/usr/bin/env bash

set -euo pipefail

pass() {
  printf 'PASS: %s\n' "$1"
}

warn() {
  printf 'WARN: %s\n' "$1" >&2
}

fail() {
  printf 'FAIL: %s\n' "$1" >&2
}

status=0

if command -v git >/dev/null 2>&1; then
  pass "git is available"
else
  fail "git is not available on PATH"
  status=1
fi

opencode_cli="$(command -v opencode || true)"
if [[ -n "$opencode_cli" ]]; then
  pass "opencode is available at $opencode_cli"
else
  fail "opencode is not available on PATH"
  warn "Install OpenCode or add its bin directory to PATH; no credentials were inspected."
  exit 1
fi

if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  repo_root="$(git rev-parse --show-toplevel)"
  pass "current directory is in Git repository: $repo_root"
else
  fail "current directory is not inside a Git repository"
  status=1
fi

if version="$("$opencode_cli" --version 2>/dev/null)"; then
  pass "opencode version: $version"
else
  fail "opencode --version failed"
  status=1
fi

if models="$("$opencode_cli" models 2>/dev/null)"; then
  pass "opencode models succeeded"
  if [[ -n "$models" ]]; then
    printf '%s\n' "$models"
  else
    warn "opencode models returned no model IDs"
  fi
else
  fail "opencode models failed"
  warn "Check provider authentication and network access. This script does not read or print API keys or tokens."
  status=1
fi

exit "$status"
