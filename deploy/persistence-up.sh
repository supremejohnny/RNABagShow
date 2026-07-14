#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_ROOT="${RNABAG_DEPLOY_ROOT:-/home/johnny/services/rnabag}"
CONFIG_FILE="${RNABAG_CONFIG_FILE:-$DEPLOY_ROOT/config/persistence.env}"

if [[ ! -f "$CONFIG_FILE" ]]; then
  echo "Persistence config is missing: $CONFIG_FILE" >&2
  echo "Run deploy/bootstrap-persistence-config.sh first." >&2
  exit 1
fi
if ! docker info >/dev/null 2>&1; then
  echo "The current user cannot access Docker. Add the user to the docker group and log in again." >&2
  exit 1
fi

docker compose \
  --env-file "$CONFIG_FILE" \
  -f "$SCRIPT_DIR/compose.persistence.yml" \
  up -d

docker compose \
  --env-file "$CONFIG_FILE" \
  -f "$SCRIPT_DIR/compose.persistence.yml" \
  ps
