# Example Workflow: Add a User Authentication Module

This is an illustrative HIGH-risk task. It does not authorize authentication
changes in the current repository.

## 1. Route

The router selects HIGH because authentication changes security boundaries,
session handling, persistence, and multiple interfaces.

## 2. Architect artifacts (Codex)

`SPEC.md` defines:

- email/password login and logout behavior;
- password hashing and session-cookie security properties;
- authorization boundaries and uniform authentication errors;
- rate-limit, audit-event, privacy, and migration constraints;
- explicit non-goals such as OAuth, account recovery, and production rollout.

`IMPLEMENTATION_PLAN.md` orders bounded changes:

1. add the user/session schema and migration;
2. add hashing and session services;
3. add API endpoints and authorization middleware;
4. add unit, integration, and negative security tests;
5. update operational documentation without deploying.

`ACCEPTANCE.md` makes each requirement executable, for example:

- correct credentials create a Secure, HttpOnly, SameSite session cookie;
- invalid credentials return a uniform response;
- protected endpoints reject missing, expired, and revoked sessions;
- plaintext passwords and session tokens never enter logs or traces;
- migration upgrade and rollback validation succeeds in an isolated database.

## 3. Coding handoff (DeepSeek v4 Pro)

The Coding agent receives only the repository instructions, project context,
the current task artifacts, the baseline diff, and directly relevant files.
It implements the ordered plan, adds tests, and writes sanitized command
results to `TEST_RESULTS.md`. Code changes remain in the worktree; it does not
commit, deploy, or contact Codex.

## 4. Review handoff (GLM5.2)

The wrapper creates an isolated bundle containing the spec, acceptance
criteria, implementation patch, and test results. GLM5.2 returns only
`REVIEW.md`.

Example finding:

```text
Verdict: CHANGES_REQUIRED

F1 (HIGH): Session revocation is not checked on the protected-endpoint path.
Criterion: AC-3
Evidence: the patch validates signature and expiry but never queries revoked_at.
Affected files: backend/auth/middleware.py, backend/tests/test_auth.py
Correction: enforce revocation and add a revoked-session negative test.
```

## 5. Debug and repair

GLM5.2 receives the failed criterion, focused test result, trace, and patch. It
writes `DEBUG_REPORT.md` with the failure reason, affected files, minimal
proposed fix, and validation to rerun. A new DeepSeek Coding invocation applies
that bounded repair. The agents do not continue a shared chat.

## 6. Final verification (Codex)

Codex independently inspects the final diff, checks every acceptance item,
runs the security-focused and migration validation commands, reconciles the
review findings, and either marks STATUS.json accepted or reports the concrete
blocker. Production deployment remains a separate user-authorized task.
