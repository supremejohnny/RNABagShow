---
name: opencode-harness
description: Delegate bounded implementation and repair tasks from Codex to a locally installed OpenCode CLI backed by DeepSeek, then independently review the resulting Git diff and validate the implementation. Use when the user asks Codex to have OpenCode or DeepSeek implement, modify, debug, refactor, or test code while Codex retains architectural and review responsibility.
---

# OpenCode Harness V2

Artifact-driven, multi-role personal AI engineering workflow. Codex is the
architect and final-audit owner. OpenCode is the execution environment.

## Architecture

- **Codex**: Architect (MEDIUM/HIGH tasks) and Final Audit owner.
- **OpenCode**: Execution environment for Coding, Review, and Debug agents.
- **Coding**: `deepseek/deepseek-v4-pro` only.
- **Review & Debug**: `doubaoglm/glm-5-2-260617` only.
- Agents exchange task-local artifacts, not conversational sessions.
- Never run more than one write-capable coding agent in one worktree.

## Risk-based routing

Every task is classified LOW, MEDIUM, or HIGH by `scripts/router.py`.
Security, authentication, credentials, database migration, deployment,
destructive, and irreversible work must never route LOW.

| Route | Workflow |
|-------|----------|
| LOW   | Coding -> focused validation |
| MEDIUM | lightweight specification -> Coding -> Review -> independent verification |
| HIGH  | Codex Architect -> Coding -> Review -> Debug/repair (max 2 cycles) -> Codex final audit |

See `references/risk-routing.md` for the full classification algorithm.

## Model policy

| Role | Model | Retry |
|------|-------|-------|
| Coding | `deepseek/deepseek-v4-pro` | Fail closed; fallback identifier is the same model |
| Review | `doubaoglm/glm-5-2-260617` | None (one-shot) |
| Debug | `doubaoglm/glm-5-2-260617` | None (one-shot) |

- Never select any `lpc/*` model.
- If a required role model is unavailable, fail closed with a clear error.
- Cross-model fallback is never allowed.

See `references/model-policy.md` for provider configuration and failure behavior.

## Artifact contract

Logical project structure under `.ai/` (optional, no requirement for existing
repos):

```text
.ai/
  PROJECT.md
  ARCHITECTURE.md
  CONVENTIONS.md
  TASKS/<task-id>/
    REQUEST.md
    SPEC.md
    IMPLEMENTATION_PLAN.md
    ACCEPTANCE.md
    STATUS.json
    TEST_RESULTS.md
    DEBUG_REPORT.md
  REVIEWS/<task-id>/REVIEW.md
  trace/<timestamp>-<task-id>-<role>-<run-id>.json
```

The Architect's logical `docs/SPEC.md`, `docs/IMPLEMENTATION_PLAN.md`, and
`docs/ACCEPTANCE.md` outputs are task-scoped here as
`.ai/TASKS/<task-id>/...` to avoid collisions between features. If a repository
already has an authoritative task-doc location under `docs/`, map the artifact
paths there and do not create duplicate copies.

Route-specific requirements:

- **LOW**: Compact task artifact only.
- **MEDIUM**: REQUEST, completed SPEC, TEST_RESULTS, STATUS.json; REVIEW is
  written after Coding.
- **HIGH**: Complete artifact set.

Templates are in `assets/templates/`. The project initializer
(`scripts/init_project.py`) creates `.ai/` from templates and refuses to
overwrite existing files.

See `references/artifact-schema.md` for full specifications.

## Context contract

Priority order:

1. `AGENTS.md` and applicable repository instructions.
2. `.ai/PROJECT.md`, `.ai/ARCHITECTURE.md`, `.ai/CONVENTIONS.md` when present.
3. Current task artifacts.
4. Baseline Git status/diff and the implementation diff.
5. Focused test results.
6. Only the source files directly required by the task.

Do not load the entire repository, old conversations, unrelated logs, or
unrelated source. Record a context manifest for each run.

See `references/context-policy.md`.

## Execution trace

Structured JSON trace files with deterministic schemas. Minimum fields:

- schema_version, run_id, task_id, phase, agent, provider, model
- started_at, finished_at, git_head, baseline_diff_hash
- input_artifacts, output_artifacts, actions, commands, validation
- usage (input/output/reasoning/cache tokens, cost — null when unavailable)
- result, failure_reason, next_action

Never copy secrets, credentials, PHI, raw private data, or complete source
bodies into trace files. Record paths, commands, actions, outcomes, and
hashes.

Use `scripts/trace.py` to generate and validate traces.

## Role output contracts

- **Architect** produces `SPEC.md`, `IMPLEMENTATION_PLAN.md`, `ACCEPTANCE.md`
  for HIGH tasks. May inspect and write artifacts but must not perform bulk
  coding or low-value debugging.
- **Coding** modifies the bounded source scope, writes tests, runs focused
  checks, and writes exact test results. Preserves unrelated changes.
- **Review** writes `REVIEW.md` with verdict (`PASS|CHANGES_REQUIRED|BLOCKED`),
  findings tied to acceptance criteria, severity, evidence, affected files,
  missing validation, security assessment, and residual risk. No style-only
  nits. One-shot, artifact-driven. No source worktree write access.
- **Debug** writes `DEBUG_REPORT.md` with failure reason, evidence, proposed
  fix, affected files, and validation to rerun. Does not modify source.
  One-shot, artifact-driven. No source worktree write access.

See `references/role-contracts.md`.

## State model

Resumable states: routed, planned, implementing, testing, reviewing,
repairing, verifying, accepted, blocked.

Maximum two bounded repair cycles. Each cycle ends after Debug writes its
artifact; start a new Coding invocation explicitly rather than continuing a
chat. After two unresolved cycles, escalate to the user.

See `references/state-model.md`.

For a concrete end-to-end artifact handoff, including an authentication-module
example, read `references/example-workflow.md`.

## Workflow

1. Read the repository's `AGENTS.md`, applicable `.ai/` context, and
   relevant source before delegating.
2. Run `python3 opencode-harness/scripts/router.py <task-file>` to classify
   risk. Print the classification and reasoning before proceeding.
3. For MEDIUM tasks, Codex completes the lightweight SPEC. For HIGH tasks,
   Codex completes SPEC, IMPLEMENTATION_PLAN, and ACCEPTANCE before Coding.
4. Verify the environment: `bash opencode-harness/scripts/verify_environment.sh`
5. Initialize the task (creates STATUS.json and route-required templates):
   ```bash
   python3 opencode-harness/scripts/init_task.py --task-id <id> --risk-level LOW|MEDIUM|HIGH --repo-root <repo>
   ```
6. Run the orchestrated workflow:
   ```bash
   bash opencode-harness/scripts/orchestrator.sh <task-file> <risk-level>
   ```
   Or invoke individual agent roles directly:
   ```bash
   python3 opencode-harness/scripts/run_agent.py coding --task-id <id> --task-file <task-file>
   python3 opencode-harness/scripts/run_agent.py review --task-id <id>
   python3 opencode-harness/scripts/run_agent.py debug --task-id <id>
   ```
   Legacy delegation still works:
   ```bash
   bash opencode-harness/scripts/delegate.sh <task-file>
   ```

7. Collect implementation evidence:
   ```bash
   bash opencode-harness/scripts/collect_result.sh
   ```

8. Independently run every test, lint, type-check, and build command required
   by the task.
9. If defects remain within the repair budget, create a targeted repair task.
10. Codex performs the final audit and reports actual changes, validation
    results, risks, and unresolved issues to the user.

## Mandatory rules

- Codex owns architecture decisions and final acceptance. OpenCode is the
  primary implementer, not the final reviewer.
- Never trust only OpenCode's written completion report. Git diffs, source
  code, and test results are the handoff evidence.
- Never ask OpenCode to call Codex.
- Never run multiple write-capable implementation agents concurrently in the
  same worktree.
- Preserve all pre-existing, task-unrelated user changes and keep delegation
  strictly within the task scope.
- OpenCode must not commit, push, reset, rebase, alter Git history, or use
  destructive Git commands. Codex must not use destructive Git commands
  either.
- Do not automatically delegate tasks involving secrets, credentials,
  production deployment, destructive database migrations, or irreversible
  operations.
- Do not place secrets in task files, prompts, logs, tests, or completion
  reports.
- Do not commit automatically. The user retains control of Git publication.
- Review and Debug must not receive write access to the source worktree.
  Give them an isolated artifact bundle and capture their report as an
  output file.
- Keep `AGENTS.md` and canonical project documentation authoritative.
  The optional `.ai/` project layout must not overwrite or duplicate an
  existing repository's durable contracts.
- Coding always uses `deepseek/deepseek-v4-pro`; its configured fallback
  identifier is the same exact model. A failed launched run stops and writes
  a failure trace instead of replaying a large context or duplicate edits.
  Never switch Coding to another model.
- Review and Debug always use `doubaoglm/glm-5-2-260617`. Do not use any
  `lpc/*` model.
- If a required role model is unavailable, fail closed with a clear error
  before any agent run.

## Compatibility

The legacy `opencode_harness` path remains via a compatibility symlink.
Existing `opencode_harness/scripts/delegate.sh <task-file>` invocations
continue to work.

## Validation

```bash
python3 "${CODEX_HOME:-$HOME/.codex}/skills/.system/skill-creator/scripts/quick_validate.py" opencode-harness
bash -n opencode-harness/scripts/*.sh
python3 -m unittest discover -s opencode-harness/tests -v
```
