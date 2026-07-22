# Role Output Contracts

## Architect (Codex, MEDIUM and HIGH tasks)

**Produces:**

- `SPEC.md` — Detailed specification covering:
  - Objective and scope
  - Current vs required behavior
  - Affected components, files, and interfaces
  - Edge cases and error handling
  - Constraints and non-goals
- `IMPLEMENTATION_PLAN.md` — Step-by-step plan with:
  - Ordered implementation steps
  - File-level changes per step
  - Dependencies between steps
  - Testing strategy per step
- `ACCEPTANCE.md` — Verifiable acceptance criteria:
  - Each criterion is a checkable statement
  - Each criterion references specific validation commands
  - Includes security assessment checklist for relevant tasks

**Prohibited:**

- Must not perform bulk coding.
- Must not run low-value debugging cycles.
- Must not modify source files (only inspect and write artifacts).

**Model:** Not constrained by this harness (Architect runs in Codex).

---

## Coding (OpenCode + DeepSeek)

**Executes:**

1. Reads the task specification and repository context.
2. Modifies only files in the stated scope.
3. Writes or updates relevant tests.
4. Runs focused validation commands from the task file.
5. Records exact test results verbatim in TEST_RESULTS.md.
6. Generates a trace file for the run.

**Preserves:**

- Pre-existing unrelated user changes in the worktree.
- Git history (never commit, push, reset, rebase, or use destructive
  Git commands).
- Application files outside the task scope.

**Model:** `deepseek/deepseek-v4-pro`. The fallback identifier is the same
exact model; a failed launched run stops and produces a failure trace.

**Output:**

- Modified source files.
- New or updated test files.
- Trace file in `.ai/trace/` or `.agent-runs/`.
- TEST_RESULTS.md with concise, sanitized command results. Never copy secrets,
  private data, or unnecessarily large logs.

---

## Review (OpenCode + doubaoglm)

**Consumes:** Isolated artifact bundle created by `scripts/run_agent.py`.

**Produces:** `REVIEW.md` with:

```
Verdict: PASS | CHANGES_REQUIRED | BLOCKED
```

**Required sections:**

1. **Verdict** — top-level classification.
2. **Findings** — each finding references a specific acceptance criterion
   or specification section and includes:
   - Severity: `CRITICAL | HIGH | MEDIUM | LOW`
   - Evidence: concrete observation, not opinion
   - Affected files: paths relative to repo root
   - Correction: minimal guidance for the fix
3. **Missing validation** — validation commands from the task that were
   not executed or whose results are absent.
4. **Security assessment** — brief security review (HIGH and MEDIUM
   tasks only).
5. **Residual risk** — remaining concerns, open questions, or
   assumptions that were not validated.

**Prohibited:**

- Must not modify source files.
- Must not report style-only nits.
- Must not access the source worktree directly.
- Must not run additional agents or delegate further.

**Model:** `doubaoglm/glm-5-2-260617`. One-shot run only. No retry.

**Execution:** One-shot, artifact-driven. Receives only the isolated
bundle. Returns only the REVIEW.md file.

---

## Debug (OpenCode + doubaoglm)

**Consumes:** Isolated artifact bundle created by `scripts/run_agent.py`.

**Produces:** `DEBUG_REPORT.md` with:

1. **Failure reason** — what the review or tests identified as broken.
2. **Evidence** — logs, diffs, test output demonstrating the failure.
3. **Proposed fix** — minimal, concrete description; no actual source
   patches.
4. **Affected files** — which files need modification.
5. **Validation to rerun** — exact commands to verify the fix.

**Prohibited:**

- Must not modify source files.
- Must not run the coding agent.
- Must not access the source worktree directly.

**Model:** `doubaoglm/glm-5-2-260617`. One-shot run only. No retry.

**Execution:** One-shot, artifact-driven. Receives only the isolated
bundle. Returns only the DEBUG_REPORT.md file.

---

## Final Audit (Codex)

After all phases complete (and repair cycles if any), Codex performs
the final audit:

- Verifies that every acceptance criterion in ACCEPTANCE.md is met.
- Reviews the REVIEW.md findings and confirms resolution.
- Inspects the final `git diff`.
- Runs validation commands independently.
- Reports to the user: actual changes, validation results, risks, and
  unresolved issues.

**Model:** Not constrained by this harness (Audit runs in Codex).
