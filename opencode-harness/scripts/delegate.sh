#!/usr/bin/env bash
# Compatibility entrypoint for one bounded Coding run.
set -euo pipefail

if [[ $# -ne 1 || ! -f "$1" ]]; then
  printf 'Usage: %s <task-file>\n' "${0##*/}" >&2
  exit 64
fi

scripts_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
repo_root="$(git rev-parse --show-toplevel 2>/dev/null)" || {
  printf 'FAIL: not inside a Git repository\n' >&2
  exit 69
}
task_file="$(cd "$(dirname "$1")" && pwd -P)/$(basename "$1")"
task_id="$(basename "$task_file" .md)"
task_id="${task_id%.txt}"

exec python3 "$scripts_dir/run_agent.py" coding \
  --repo-root "$repo_root" --task-id "$task_id" --task-file "$task_file"
