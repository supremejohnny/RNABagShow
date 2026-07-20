---
name: opencode_harness
description: Delegate bounded implementation and repair tasks from Codex to a locally installed OpenCode CLI backed by DeepSeek, then independently review the resulting Git diff and validate the implementation. Use when the user asks Codex to have OpenCode or DeepSeek implement, modify, debug, refactor, or test code while Codex retains architectural and review responsibility.
---

# OpenCode Harness

Use Codex as architect and reviewer and OpenCode as the primary implementer for bounded, non-trivial coding tasks.

## Workflow

1. Read the repository's `AGENTS.md`, relevant README files, configuration, and related source before delegating.
2. Analyze the requirements and make the architecture decisions in Codex.
3. For a non-trivial coding task, read `references/task-template.md` and create a bounded task Markdown file. For a very simple change, Codex may implement it directly.
4. Verify the environment when needed with `bash opencode_harness/scripts/verify_environment.sh`, then delegate from the repository worktree:

   ```bash
   bash opencode_harness/scripts/delegate.sh <task-file>
   ```

5. After OpenCode returns, independently inspect the handoff evidence:

   ```bash
   git status --short
   git diff --stat
   git diff
   ```

   `bash opencode_harness/scripts/collect_result.sh` collects the same evidence and identifies the latest run log.
6. Independently run every test, lint, type-check, and build command required by the task.
7. If defects remain, create a new, narrowly targeted repair task and delegate again. Prefer this over taking over a large implementation directly.
8. Perform the final audit and report actual changes, validation results, risks, and unresolved issues to the user.

## Mandatory rules

- Codex owns architecture decisions and final acceptance. OpenCode is the primary implementer, not the final reviewer.
- Never trust only OpenCode's written completion report. Git diffs, source code, and test results are the handoff evidence.
- Never ask OpenCode to call Codex.
- Never run multiple write-capable implementation agents concurrently in the same worktree.
- Preserve all pre-existing, task-unrelated user changes and keep delegation strictly within the task scope.
- OpenCode must not commit, push, reset, rebase, alter Git history, or use destructive Git commands. Codex must not use destructive Git commands either.
- Do not automatically delegate tasks involving secrets, credentials, production deployment, destructive database migrations, or irreversible operations.
- Do not place secrets in task files, prompts, logs, tests, or completion reports.
- Do not commit automatically. The user retains control of Git publication.
