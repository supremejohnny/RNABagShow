# Model Policy

## Role-to-model mapping

| Role | Provider | Model | Retry |
|------|----------|-------|-------|
| Coding | deepseek | `deepseek/deepseek-v4-pro` | Fail closed; fallback is the same identifier |
| Review | doubaoglm | `doubaoglm/glm-5-2-260617` | None (one-shot only) |
| Debug | doubaoglm | `doubaoglm/glm-5-2-260617` | None (one-shot only) |

## Forbidden models

- Any `lpc/*` model must never be selected for any role.
- The Luna and Terra providers are still being configured; do not use them.
- No other model may be substituted for the specified role model.

## Coding fallback policy

The configured Coding fallback is the same exact
`deepseek/deepseek-v4-pro` identifier. Cross-model fallback is forbidden.
After a launched run fails, fail closed and write a failure trace; do not
automatically replay a potentially large context or duplicate file edits.

## Fail-closed behavior

Before launching any agent, verify the required model is available:

1. Run `opencode models` and parse the output.
2. Check that the required provider+model string is listed.
3. If the model is not found or the provider is unauthenticated, exit with
   a clear error message identifying the missing model.
4. Do not fall back to another model, another provider, or a degraded mode.

## Provider configuration

Providers must be configured in OpenCode before the harness runs. The
harness does not manage provider credentials.

Required provider configurations:

```text
deepseek:
  api_key: <configured in OpenCode>

doubaoglm:
  api_key: <configured in OpenCode>
```

## Model availability check

The `verify_environment.sh` script checks that `opencode models` succeeds.
`scripts/delegate.sh` additionally validates that the required model string
appears in the output before launching.

## Trace recording

Every agent run records the selected provider and model in the trace file.
If `opencode` does not emit trustworthy usage data, the `usage` fields
remain `null` — never fabricate token counts or costs.
