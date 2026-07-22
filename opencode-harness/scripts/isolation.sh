#!/usr/bin/env bash
# Create the same disposable artifact bundle used by run_agent.py.
set -euo pipefail

if [[ $# -lt 2 ]]; then
  printf 'Usage: %s <review|debug> <task-id> [--worktree <path>]\n' "${0##*/}" >&2
  exit 64
fi
phase=$1
task_id=$2
shift 2
[[ "$phase" == review || "$phase" == debug ]] || {
  printf 'FAIL: phase must be review or debug\n' >&2
  exit 64
}

worktree=""
if [[ $# -gt 0 ]]; then
  [[ $# -eq 2 && "$1" == --worktree ]] || { printf 'FAIL: invalid arguments\n' >&2; exit 64; }
  worktree=$2
else
  worktree="$(git rev-parse --show-toplevel 2>/dev/null)" || exit 69
fi
[[ -d "$worktree/.git" ]] || { printf 'FAIL: not a Git worktree: %s\n' "$worktree" >&2; exit 69; }

scripts_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
bundle="$(python3 - "$scripts_dir" "$worktree" "$task_id" "$phase" <<'PY'
import sys
sys.path.insert(0, sys.argv[1])
from run_agent import _create_isolation_bundle
print(_create_isolation_bundle(sys.argv[2], sys.argv[3], sys.argv[4]))
PY
)"

printf 'Phase: %s\nTask ID: %s\n' "$phase" "$task_id"
printf 'Bundle contains task artifacts, a complete patch, and focused results; no source tree copy.\n'
printf 'The agent must return its report as final JSON text; the wrapper writes the durable report.\n'
printf '%s\n' "$bundle"
