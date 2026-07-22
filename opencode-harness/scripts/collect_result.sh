#!/usr/bin/env bash
# Collect bounded implementation evidence without replaying raw agent logs.
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel 2>/dev/null)" || {
  printf 'FAIL: not inside a Git repository\n' >&2
  exit 69
}
scripts_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"

printf '== git status --short ==\n'
git -C "$repo_root" status --short
printf '\n== patch summary ==\n'
git -C "$repo_root" diff --stat
printf '\nUntracked files are included in the review patch but not printed here.\n'
printf 'Patch hash: '
python3 "$scripts_dir/patch_collector.py" "$repo_root" --hash-only

printf '\n== recent execution traces ==\n'
for trace_dir in "$repo_root/.ai/trace" "$repo_root/.agent-runs/traces"; do
  if [[ -d "$trace_dir" ]]; then
    find "$trace_dir" -maxdepth 1 -type f -name '*.json' -print | sort | tail -n 10
  fi
done

printf '\nInspect task TEST_RESULTS.md and reports directly; raw OpenCode stdout is intentionally not persisted.\n'
