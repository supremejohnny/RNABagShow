# Risk Routing

Every task is classified LOW, MEDIUM, or HIGH before execution begins.
Classification is performed by `scripts/router.py`, which applies the
algorithm defined here.

## Hard invariants

These task categories must **never** route LOW:

- Security: authentication, authorization, credential handling, encryption,
  key management, access control, session management, token handling.
- Privacy: PII, PHI, personal data handling, data retention, anonymization.
- Credentials: any change touching API keys, passwords, tokens, secrets,
  environment variables containing secrets.
- Database migration: schema changes, DDL, Alembic migrations, data
  transformations, new tables or columns.
- Deployment: Docker, Compose, Kubernetes, Nginx, proxy, gateway,
  production configuration, CI/CD.
- Destructive operations: delete, drop, purge, truncate, destroy,
  irreversible changes, force push.
- Data risk: changes to persistence layers, data integrity, backup
  procedures, object storage configuration.

These categories should **strongly prefer HIGH**:

- Architecture changes: new services, component restructuring, API
  breaking changes, new frameworks or patterns.
- Multi-component blast radius: changes touching 3+ independent
  subsystems.

## Scoring factors

The router evaluates each task against these weighted factors:

| Factor | Weight | Examples |
|--------|--------|----------|
| File count | 0-20 | >5 files (+20), >2 files (+10) |
| Core infrastructure | 0-15 | main.py, config/, api/, app/ |
| Security/privacy keywords | +30 cap | auth, credential, secret, token, password, encrypt, hash, permission, access_control, privacy, PHI, PII |
| Database keywords | +30 cap | migration, schema, database, postgres, sql, alembic, DDL, alter table |
| Deployment keywords | +25 cap | deploy, production, docker, kubernetes, compose, nginx, proxy, gateway |
| Destructive keywords | +40 cap | delete, destroy, drop, purge, truncate, irreversible, destructive |
| Architecture keywords | +20 cap | architecture, refactor, redesign, rewrite, restructure, new_service |
| Ambiguity indicators | 0-15 | maybe, perhaps, unclear, investigate, explore, experiment (>2 matches) |
| Verification complexity | 0-10 | integration test, e2e, performance, load test, manual test |

## Classification thresholds

1. Compute the raw score from all applicable factors.
2. Apply hard invariants: if any security, credential, privacy, database
   migration, deployment, destructive, or data-risk keyword is present,
   floor the score at the MEDIUM threshold (15).
3. Apply the thresholds:

| Score | Classification |
|-------|----------------|
| >= 40 | HIGH |
| >= 15 | MEDIUM |
| < 15  | LOW |

## Route behavior

### LOW

- Coding runs directly with `delegate.sh`.
- Run focused validation commands from the task file.
- No Architect artifact set required.
- Use compact task artifact in `.ai/TASKS/<id>/`.

### MEDIUM

- Codex writes or confirms a lightweight specification.
- Coding runs with `delegate.sh`.
- Review runs from an isolated artifact bundle.
- Independent verification runs after review.
- Inputs: REQUEST.md, SPEC.md, STATUS.json.
- Outputs: TEST_RESULTS.md and isolated REVIEW.md.

### HIGH

1. Codex produces Architect artifact set: SPEC.md, IMPLEMENTATION_PLAN.md,
   ACCEPTANCE.md.
2. Coding runs with `delegate.sh`.
3. Review runs from an isolated artifact bundle.
4. If defects remain: Debug run from isolated bundle (max 2 cycles).
5. Codex performs final audit against ACCEPTANCE.md.
6. Complete artifact set saved in `.ai/TASKS/<id>/`.

## Example classifications

| Task description | Classification | Reasoning |
|-----------------|----------------|-----------|
| "Fix typo in README" | LOW | Single file, no risk factors |
| "Add input validation to upload endpoint" | MEDIUM | Multiple files, API change |
| "Add authentication middleware" | HIGH | Security, architecture change |
| "Update a docstring in one file" | LOW | Single file, documentation only |
| "Run database migration to add column" | HIGH | Database migration never LOW |
| "Fix credential handling in config" | HIGH | Credentials never LOW, security |
| "Refactor preprocessing pipeline" | MEDIUM | Architecture keyword, multi-file |
| "Deploy new Docker compose file" | HIGH | Deployment never LOW |
| "Rename a CSS class in frontend" | LOW | Single file, no risk |
