#!/usr/bin/env bash
set -euo pipefail

usage() {
  printf 'Usage: %s <task-file> [LOW|MEDIUM|HIGH]\n' "${0##*/}" >&2
}

if [[ $# -lt 1 || ! -f "$1" ]]; then
  usage
  exit 64
fi

task_arg=$1
scripts_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
repo_root="$(git rev-parse --show-toplevel 2>/dev/null)" || {
  printf 'FAIL: not inside a Git repository\n' >&2
  exit 69
}
task_id="$(basename "$task_arg" .md)"
task_id="${task_id%.txt}"

if [[ $# -ge 2 ]]; then
  risk_level="$(printf '%s' "$2" | tr '[:lower:]' '[:upper:]')"
else
  router_exit=0
  router_output="$(python3 "$scripts_dir/router.py" "$task_arg" 2>&1)" || router_exit=$?
  case "$router_exit" in
    0) risk_level=LOW ;;
    2) risk_level=MEDIUM ;;
    3) risk_level=HIGH ;;
    *) printf 'FAIL: router failed (%s): %s\n' "$router_exit" "$router_output" >&2; exit 69 ;;
  esac
  printf 'Router classification: %s\n%s\n' "$risk_level" "$router_output"
fi

case "$risk_level" in LOW|MEDIUM|HIGH) ;; *) printf 'FAIL: invalid risk level: %s\n' "$risk_level" >&2; exit 64 ;; esac

status_update() {
  python3 "$scripts_dir/status.py" --repo-root "$repo_root" --task-id "$task_id" --state "$1" >/dev/null
}

find_report() {
  local name=$1
  local candidate
  for candidate in \
    "$repo_root/.ai/REVIEWS/$task_id/$name" \
    "$repo_root/.ai/TASKS/$task_id/$name" \
    "$repo_root/.agent-runs/reviews/$task_id/$name" \
    "$repo_root/.agent-runs/tasks/$task_id/$name"; do
    if [[ -f "$candidate" ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  return 1
}

python3 "$scripts_dir/init_task.py" \
  --task-id "$task_id" --risk-level "$risk_level" --repo-root "$repo_root" \
  --request "$(<"$task_arg")" --add-missing

if [[ "$risk_level" != LOW ]]; then
  if ! python3 "$scripts_dir/init_task.py" \
      --task-id "$task_id" --risk-level "$risk_level" --repo-root "$repo_root" \
      --check-required "$risk_level"; then
    status_update blocked
    printf 'Codex Architect must complete the required artifact files before Coding.\n' >&2
    exit 1
  fi
  status_update planned
fi

printf '\n[Phase: Coding | model: deepseek/deepseek-v4-pro]\n'
status_update implementing
if ! python3 "$scripts_dir/run_agent.py" coding \
    --repo-root "$repo_root" --task-id "$task_id" --task-file "$task_arg"; then
  status_update blocked
  exit 1
fi
status_update testing

if [[ "$risk_level" == LOW ]]; then
  status_update verifying
  printf '\nLOW route complete: Coding -> bounded validation. Codex final acceptance is optional.\n'
  exit 0
fi

printf '\n[Phase: Review | model: doubaoglm/glm-5-2-260617]\n'
status_update reviewing
if ! python3 "$scripts_dir/run_agent.py" review --repo-root "$repo_root" --task-id "$task_id"; then
  status_update blocked
  exit 1
fi

review_path="$(find_report REVIEW.md)" || {
  status_update blocked
  printf 'FAIL: REVIEW.md was not written\n' >&2
  exit 1
}
verdict="$(sed -nE 's/^Verdict:[[:space:]]*(PASS|CHANGES_REQUIRED|BLOCKED)[[:space:]]*$/\1/p' "$review_path")"

case "$verdict" in
  PASS)
    status_update verifying
    printf '\nReview PASS. Codex owns independent final verification and acceptance.\n'
    ;;
  BLOCKED)
    status_update blocked
    printf '\nReview BLOCKED. Resolve missing authority or artifacts before continuing.\n' >&2
    exit 1
    ;;
  CHANGES_REQUIRED)
    if ! python3 "$scripts_dir/status.py" --repo-root "$repo_root" --task-id "$task_id" --check-repair-limit >/dev/null; then
      status_update blocked
      printf '\nRepair-cycle limit reached; escalate to Codex Architect.\n' >&2
      exit 1
    fi
    printf '\n[Phase: Debug | model: doubaoglm/glm-5-2-260617]\n'
    status_update repairing
    python3 "$scripts_dir/status.py" --repo-root "$repo_root" --task-id "$task_id" --increment-repair >/dev/null
    if ! python3 "$scripts_dir/run_agent.py" debug --repo-root "$repo_root" --task-id "$task_id"; then
      status_update blocked
      exit 1
    fi
    debug_path="$(find_report DEBUG_REPORT.md)" || {
      status_update blocked
      printf 'FAIL: DEBUG_REPORT.md was not written\n' >&2
      exit 1
    }
    printf '\nDebug diagnosis written to %s. Start a new bounded Coding run for the proposed repair.\n' "$debug_path"
    ;;
  *)
    status_update blocked
    printf 'FAIL: invalid or ambiguous review verdict\n' >&2
    exit 1
    ;;
esac
