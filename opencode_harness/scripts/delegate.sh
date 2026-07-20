#!/usr/bin/env bash

set -euo pipefail

usage() {
  printf 'Usage: %s <task-file>\n' "${0##*/}" >&2
}

if [[ $# -ne 1 ]]; then
  usage
  exit 64
fi

task_arg=$1
if [[ ! -f "$task_arg" ]]; then
  printf 'FAIL: task file does not exist: %s\n' "$task_arg" >&2
  exit 66
fi

if ! repo_root="$(git rev-parse --show-toplevel 2>/dev/null)"; then
  printf 'FAIL: current directory is not inside a Git repository.\n' >&2
  exit 69
fi

task_dir="$(cd "$(dirname "$task_arg")" && pwd -P)"
task_file="$task_dir/$(basename "$task_arg")"
run_dir="$repo_root/.agent-runs"
mkdir -p "$run_dir"
timestamp="$(date '+%Y%m%d-%H%M%S')"
log_file="$run_dir/opencode-$timestamp.log"

opencode_cli="$(command -v opencode || true)"
if [[ -z "$opencode_cli" ]]; then
  printf 'FAIL: opencode is not available on PATH.\n' | tee "$log_file" >&2
  printf 'Log: %s\n' "$log_file" >&2
  exit 127
fi

model="${OPENCODE_DELEGATE_MODEL:-SET_ME_FROM_OPENCODE_MODELS}"
agent="${OPENCODE_DELEGATE_AGENT:-build}"

if [[ "$model" == "SET_ME_FROM_OPENCODE_MODELS" ]]; then
  {
    printf 'FAIL: OPENCODE_DELEGATE_MODEL is not configured.\n'
    printf 'Run `opencode models`, choose the configured DeepSeek model ID, and export OPENCODE_DELEGATE_MODEL.\n'
  } | tee "$log_file" >&2
  printf 'Log: %s\n' "$log_file" >&2
  exit 64
fi

if ! run_help="$("$opencode_cli" run --help 2>&1)"; then
  printf 'FAIL: unable to inspect `opencode run --help`.\n' | tee "$log_file" >&2
  printf 'Log: %s\n' "$log_file" >&2
  exit 69
fi

for required_option in --model --agent --dir --auto; do
  if ! grep -q -- "$required_option" <<<"$run_help"; then
    printf 'FAIL: installed OpenCode does not support required option %s.\n' "$required_option" | tee "$log_file" >&2
    printf 'Log: %s\n' "$log_file" >&2
    exit 69
  fi
done

task_content="$(<"$task_file")"
prompt="$(printf '%s\n\n%s\n\n%s\n' \
  'Implement the bounded task below directly in the current Git worktree.' \
  'First inspect the repository and follow every applicable AGENTS.md instruction. Modify only the stated scope and preserve unrelated existing changes. Do not commit, push, reset, rebase, or otherwise alter Git history. Do not read, expose, or print secrets. Write or update relevant tests and run the task validation commands. At completion, report modified files, validation commands with results, and any remaining issues. Do not call Codex.' \
  "$task_content")"

printf 'Delegating task: %s\n' "$task_file"
printf 'Repository: %s\n' "$repo_root"
printf 'Model: %s\n' "$model"
printf 'Agent: %s\n' "$agent"
printf 'Log: %s\n' "$log_file"

set +e
"$opencode_cli" run \
  --auto \
  --model "$model" \
  --agent "$agent" \
  --dir "$repo_root" \
  "$prompt" 2>&1 | tee "$log_file"
opencode_status=${PIPESTATUS[0]}
set -e

if [[ $opencode_status -ne 0 ]]; then
  printf 'FAIL: OpenCode exited with status %d. Log: %s\n' "$opencode_status" "$log_file" >&2
else
  printf 'PASS: OpenCode completed. Codex must now inspect the Git diff and run validation independently.\n'
fi

exit "$opencode_status"
