#!/usr/bin/env bash

set -euo pipefail

if ! repo_root="$(git rev-parse --show-toplevel 2>/dev/null)"; then
  printf 'FAIL: current directory is not inside a Git repository.\n' >&2
  exit 69
fi

printf '== git status --short ==\n'
git -C "$repo_root" status --short

printf '\n== git diff --stat ==\n'
git -C "$repo_root" diff --stat

printf '\n== git diff ==\n'
git -C "$repo_root" diff

printf '\n== latest OpenCode log ==\n'
shopt -s nullglob
logs=("$repo_root"/.agent-runs/opencode-*.log)
shopt -u nullglob

if (( ${#logs[@]} == 0 )); then
  printf 'WARN: no .agent-runs/opencode-*.log files found.\n' >&2
else
  latest_log=${logs[0]}
  for log_file in "${logs[@]:1}"; do
    if [[ "$log_file" -nt "$latest_log" ]]; then
      latest_log=$log_file
    fi
  done
  printf '%s\n' "$latest_log"
fi
