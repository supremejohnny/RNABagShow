#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_ROOT="${RNABAG_DEPLOY_ROOT:-/home/johnny/services/rnabag}"
CONFIG_FILE="${RNABAG_CONFIG_FILE:-$DEPLOY_ROOT/config/persistence.env}"
EXPECTED_CONFIRMATION="delete-rnabag-test-database-and-objects"
EXPECTED_DEPLOY_ROOT="/home/johnny/services/rnabag"

if [[ "${RNABAG_CONFIRM_RESET:-}" != "$EXPECTED_CONFIRMATION" ]]; then
  echo "Destructive reset refused." >&2
  echo "Set RNABAG_CONFIRM_RESET=$EXPECTED_CONFIRMATION to confirm." >&2
  exit 1
fi
if [[ ! -f "$CONFIG_FILE" ]]; then
  echo "Persistence config is missing: $CONFIG_FILE" >&2
  exit 1
fi
if [[ "$DEPLOY_ROOT" != "$EXPECTED_DEPLOY_ROOT" ]]; then
  echo "Unexpected deployment root; reset refused: $DEPLOY_ROOT" >&2
  exit 1
fi

set -a
source "$CONFIG_FILE"
set +a

if [[ "$RNABAG_POSTGRES_DATA_DIR" != "$DEPLOY_ROOT/postgres" ]]; then
  echo "Unexpected PostgreSQL data path; reset refused." >&2
  exit 1
fi
if [[ "$RNABAG_OBJECT_DATA_DIR" != "$DEPLOY_ROOT/object-storage" ]]; then
  echo "Unexpected object data path; reset refused." >&2
  exit 1
fi
if ! docker info >/dev/null 2>&1; then
  echo "The current user cannot access Docker." >&2
  exit 1
fi

export RNABAG_UID="$(id -u)"
export RNABAG_GID="$(id -g)"
RUNNING_APP_SERVICES="$(
  docker compose \
    --env-file "$CONFIG_FILE" \
    -f "$SCRIPT_DIR/compose.app-cpu.yml" \
    ps --status running --services
)"
if grep -qx app <<<"$RUNNING_APP_SERVICES"; then
  echo "Destructive reset refused while the RNABag app is running." >&2
  echo "Run deploy/app-down.sh first, then retry." >&2
  exit 1
fi

docker compose \
  --env-file "$CONFIG_FILE" \
  -f "$SCRIPT_DIR/compose.persistence.yml" \
  down --remove-orphans

docker run --rm \
  --user 0:0 \
  --entrypoint sh \
  -v "$RNABAG_POSTGRES_DATA_DIR:/wipe" \
  postgres:16-alpine \
  -c 'rm -rf /wipe/* /wipe/.[!.]* /wipe/..?*'

docker run --rm \
  --user 0:0 \
  --entrypoint sh \
  -v "$RNABAG_OBJECT_DATA_DIR:/wipe" \
  minio/mc:latest \
  -c 'rm -rf /wipe/* /wipe/.[!.]* /wipe/..?*'

echo "RNABag test PostgreSQL and object-storage data were deleted."
echo "The private config file was preserved."
