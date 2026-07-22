# Artifact Schema

## Directory layout

```text
.ai/
  PROJECT.md              -- Project overview, tech stack, domain context
  ARCHITECTURE.md          -- System architecture, component diagram, data flow
  CONVENTIONS.md           -- Code conventions, naming, patterns for this repo
  TASKS/<task-id>/
    REQUEST.md             -- Original task request
    SPEC.md                -- Detailed specification
    IMPLEMENTATION_PLAN.md -- Step-by-step implementation plan
    ACCEPTANCE.md          -- Acceptance criteria checklist
    STATUS.json            -- Current state in the state machine
    TEST_RESULTS.md        -- Test output and validation results
    DEBUG_REPORT.md        -- Debug findings from repair phase
  REVIEWS/<task-id>/
    REVIEW.md              -- Independent review report
  trace/<timestamp>-<task-id>-<role>-<run-id>.json
```

## Route-specific artifact requirements

### LOW
- Compact task artifact in `.ai/TASKS/<task-id>/REQUEST.md`.
- TEST_RESULTS.md with validation output.
- Optional: REVIEW.md (at user discretion).

### MEDIUM
- REQUEST.md
- SPEC.md (lightweight: scope, constraints, acceptance criteria)
- REVIEW.md (from isolated Review run)
- TEST_RESULTS.md
- STATUS.json

### HIGH
- Complete artifact set:
  - REQUEST.md
  - SPEC.md (comprehensive)
  - IMPLEMENTATION_PLAN.md
  - ACCEPTANCE.md
  - STATUS.json
  - TEST_RESULTS.md
  - DEBUG_REPORT.md (if repair was needed)
  - REVIEWS/<task-id>/REVIEW.md
  - trace/*.json for each phase

## STATUS.json schema

```json
{
  "task_id": "<string>",
  "state": "routed|planned|implementing|testing|reviewing|repairing|verifying|accepted|blocked",
  "risk_level": "LOW|MEDIUM|HIGH",
  "repair_cycles": 0,
  "max_repair_cycles": 2,
  "updated_at": "<ISO-8601>",
  "artifacts": {
    "request": "<path or null>",
    "spec": "<path or null>",
    "implementation_plan": "<path or null>",
    "acceptance": "<path or null>",
    "test_results": "<path or null>",
    "review": "<path or null>",
    "debug_report": "<path or null>"
  },
  "runs": ["<run-id-1>", "<run-id-2>"]
}
```

## Trace filename convention

```text
trace/<timestamp>-<task-id>-<role>-<run-id>.json
```

Components:
- `timestamp`: ISO-8601 compact (`YYYYMMDDTHHMMSS`)
- `task-id`: slug from task title or explicit ID
- `role`: `architect`, `coding`, `review`, `debug`, `audit`
- `run-id`: short unique identifier (16 hex chars)

## Initialization rules

`scripts/init_project.py` creates `.ai/` from templates:

1. Never overwrite existing files.
2. If `.ai/` already exists, report which files are present and exit
   (use `--force` to add only missing template stubs).
3. If `AGENTS.md` or README files exist in the repo root, create stub
   `.ai/` files that reference them rather than duplicating content.
4. Create the `TASKS/`, `REVIEWS/`, and `trace/` subdirectories.
5. Do not copy application data or secrets into `.ai/`.

## Template source

Reusable output templates live in `assets/templates/`:

- `REQUEST.md` — minimal task request stub
- `SPEC.md` — specification template
- `IMPLEMENTATION_PLAN.md` — plan template
- `ACCEPTANCE.md` — acceptance criteria template
- `REVIEW.md` — review report template
- `DEBUG_REPORT.md` — debug report template
- `TEST_RESULTS.md` — test results template
- `STATUS.json` — status tracking template
- `trace.json` — trace schema reference
