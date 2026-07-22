# Context Policy

## Priority order

When an agent prepares for a run, it loads context in this priority:

1. **Canonical repository instructions**: `AGENTS.md` and any applicable
   agent instructions from the repository root.
2. **Project-level AI context** (when present): `.ai/PROJECT.md`,
   `.ai/ARCHITECTURE.md`, `.ai/CONVENTIONS.md`.
3. **Current task artifacts**: All files under
   `.ai/TASKS/<current-task-id>/`, including REQUEST.md, SPEC.md,
   IMPLEMENTATION_PLAN.md, ACCEPTANCE.md, and STATUS.json.
4. **Baseline Git state**: `git status --short`, `git diff --stat`, and
   the task-specific implementation diff.
5. **Focused test results**: Output from the validation commands defined
   in the task's acceptance criteria.
6. **Relevant source files**: Only the files explicitly listed in the
   task's scope or identified as directly affected by the change.

## What NOT to load

- The entire repository (do not recursively load all files).
- Old conversations or previous unrelated agent sessions.
- Unrelated logs, including `.agent-runs/` files from other tasks.
- Unrelated source files outside the task scope.
- `.git/` internals beyond `status` and `diff`.
- Unrelated `harness/` notebook content. If repository instructions identify
  task-relevant local harness notes as authoritative current state, read only
  those named notes.
- Secrets, credentials, API keys, or environment variables.

## Context manifest

For MEDIUM and HIGH tasks, the trace records a minimal context manifest:

- Named input artifact paths.
- Safe tool/action names reported by OpenCode.
- The baseline patch hash and Git commit.

Do not copy artifact or source bodies into trace JSON. Unknown token usage
remains null and is never estimated.

## Context for Review and Debug

Review and Debug agents receive an isolated artifact bundle created by
`scripts/isolation.sh`. They do not have direct access to the source
worktree. The bundle contains:

- The task specification (SPEC.md or REQUEST.md).
- The acceptance criteria (ACCEPTANCE.md or equivalent).
- The implementation diff (as a patch file or rendered diff).
- Test results (TEST_RESULTS.md).
- No source file copies; changed source is represented only by the patch.

The bundle must not contain secrets, full source files, or raw data.

Patch redaction is defense in depth, not a universal secret scanner. It
excludes common credential/key files and redacts quoted literal assignments
for common credential names. Keep all real credentials outside Git and task
artifacts; an unfamiliar or unquoted secret format may not be recognized.
