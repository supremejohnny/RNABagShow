# State Model

## States

| State | Description |
|-------|-------------|
| `routed` | Task classified (LOW/MEDIUM/HIGH), route selected. |
| `planned` | Architect artifacts written (HIGH) or lightweight spec confirmed (MEDIUM). |
| `implementing` | Coding agent actively modifying source. |
| `testing` | Validation commands executing against implementation. |
| `reviewing` | Review agent evaluating implementation against spec. |
| `repairing` | Debug agent analyzing failures; Coding preparing to re-run. |
| `verifying` | Final validation pass before acceptance. |
| `accepted` | All acceptance criteria met, final audit passed. |
| `blocked` | Cannot proceed; escalation required. |

## Transitions

### LOW route

```
routed -> implementing -> testing -> accepted
                               |
                               v (optional)
                           reviewing -> accepted
```

### MEDIUM route

```
routed -> planned -> implementing -> testing -> reviewing -> verifying -> accepted
                                                                    |
                                                                    v
                                                                blocked
```

### HIGH route

```
routed -> planned -> implementing -> testing -> reviewing
                                                  |
                               +------------------+
                               |                  |
                          PASS verdict     CHANGES_REQUIRED
                               |                  |
                          verifying          repairing -> implementing
                               |             (max 2 cycles)
                          accepted                |
                                                  v
                                              blocked

                          BLOCKED verdict -> blocked
```

## Repair budget

- Maximum 2 bounded repair cycles per task.
- Each cycle stops after Debug writes DEBUG_REPORT.md. A new Coding run is
  explicitly started with that artifact; agents do not continue chatting.
- If a second repair cycle still produces CHANGES_REQUIRED, transition
  to `blocked` and escalate to the user.
- Codex may decide to accept remaining LOW-severity findings without
  repair if they do not violate acceptance criteria.

## Escalation triggers

Transition to `blocked` when:

1. Review verdict is `BLOCKED` (unrecoverable issue).
2. Two repair cycles fail to resolve CHANGES_REQUIRED.
3. Required model is unavailable.
4. Task file, specification, or acceptance criteria are missing or
   unparseable for HIGH tasks.
5. Coding agent produces no diff, no test results, or a non-zero exit
   with no recoverable error.

## STATUS.json updates

The STATUS.json file is updated at each orchestrated state transition. Agent
runners append run IDs and discovered output artifact paths.

Each update records:
- `state`: current state
- `updated_at`: ISO-8601 timestamp
- `repair_cycles`: incremented when transitioning to `repairing`
- `runs`: append new run IDs

## Recovery from blocked

A blocked task requires human intervention. The user may:

- Clarify or rewrite the specification.
- Approve acceptance of remaining LOW-severity findings.
- Manually fix an unrecoverable issue and reset the state to `planned`.
- Cancel the task.

The harness does not auto-recover from `blocked`.
