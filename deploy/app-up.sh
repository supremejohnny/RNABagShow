#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_ROOT="${RNABAG_DEPLOY_ROOT:-/home/johnny/services/rnabag}"
CONFIG_FILE="${RNABAG_CONFIG_FILE:-$DEPLOY_ROOT/config/persistence.env}"
EXPECTED_TEMP_DIR="$DEPLOY_ROOT/runtime/uploads-tmp"

if [[ ! -f "$CONFIG_FILE" ]]; then
  echo "Persistence config is missing: $CONFIG_FILE" >&2
  echo "Run deploy/bootstrap-persistence-config.sh first." >&2
  exit 1
fi
if ! docker info >/dev/null 2>&1; then
  echo "The current user cannot access Docker." >&2
  exit 1
fi

CONFIG_TEMP_DIR="$(sed -n 's/^RNABAG_TEMP_DIR=//p' "$CONFIG_FILE" | tail -n 1)"
if [[ "$CONFIG_TEMP_DIR" != "$EXPECTED_TEMP_DIR" ]]; then
  echo "Unexpected RNABAG_TEMP_DIR in $CONFIG_FILE" >&2
  echo "Expected: $EXPECTED_TEMP_DIR" >&2
  exit 1
fi

RUNNING_SERVICES="$(
  docker compose \
    --env-file "$CONFIG_FILE" \
    -f "$SCRIPT_DIR/compose.persistence.yml" \
    ps --status running --services
)"
if ! grep -qx postgres <<<"$RUNNING_SERVICES" || ! grep -qx minio <<<"$RUNNING_SERVICES"; then
  echo "PostgreSQL and MinIO must be running first." >&2
  echo "Run deploy/persistence-up.sh, then retry." >&2
  exit 1
fi

mkdir -p "$EXPECTED_TEMP_DIR"
chmod 700 "$DEPLOY_ROOT/runtime" "$EXPECTED_TEMP_DIR"

export RNABAG_UID="$(id -u)"
export RNABAG_GID="$(id -g)"

docker compose \
  --env-file "$CONFIG_FILE" \
  -f "$SCRIPT_DIR/compose.app-cpu.yml" \
  up -d --build --wait

docker compose \
  --env-file "$CONFIG_FILE" \
  -f "$SCRIPT_DIR/compose.app-cpu.yml" \
  ps

echo "RNABag is listening only on server loopback: http://127.0.0.1:${RNABAG_APP_PORT:-8000}/"
