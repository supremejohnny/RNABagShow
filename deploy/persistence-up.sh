#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_ROOT="${RNABAG_DEPLOY_ROOT:-/home/johnny/services/rnabag}"
CONFIG_FILE="${RNABAG_CONFIG_FILE:-$DEPLOY_ROOT/config/persistence.env}"
PIP_INDEX_URL=""

if [[ ! -f "$CONFIG_FILE" ]]; then
  echo "Persistence config is missing: $CONFIG_FILE" >&2
  echo "Run deploy/bootstrap-persistence-config.sh first." >&2
  exit 1
fi
if ! docker info >/dev/null 2>&1; then
  echo "The current user cannot access Docker. Add the user to the docker group and log in again." >&2
  exit 1
fi
PIP_INDEX_URL="$(sed -n 's/^RNABAG_PIP_INDEX_URL=//p' "$CONFIG_FILE" | tail -n 1)"
PIP_INDEX_URL="${PIP_INDEX_URL:-https://pypi.org/simple}"

compose_build_supported() {
  local version
  version="$(docker buildx version 2>/dev/null | awk 'NR == 1 { print $2 }')"
  version="${version#v}"
  [[ -n "$version" ]] || return 1
  [[ "$(printf '%s\n' 0.17.0 "$version" | sort -V | head -n 1)" == "0.17.0" ]]
}

docker compose \
  --env-file "$CONFIG_FILE" \
  -f "$SCRIPT_DIR/compose.persistence.yml" \
  up -d --wait postgres minio

docker compose \
  --env-file "$CONFIG_FILE" \
  -f "$SCRIPT_DIR/compose.persistence.yml" \
  run --rm minio-init

if compose_build_supported; then
  docker compose \
    --env-file "$CONFIG_FILE" \
    -f "$SCRIPT_DIR/compose.persistence.yml" \
    build migrate
else
  echo "Docker Buildx is older than 0.17; using the Docker legacy builder for the migration image."
  DOCKER_BUILDKIT=0 docker build \
    --build-arg "RNABAG_PIP_INDEX_URL=$PIP_INDEX_URL" \
    --file "$SCRIPT_DIR/Dockerfile.persistence" \
    --tag rnabag-persistence:local \
    "$SCRIPT_DIR/.."
fi

docker compose \
  --env-file "$CONFIG_FILE" \
  -f "$SCRIPT_DIR/compose.persistence.yml" \
  run --rm migrate

docker compose \
  --env-file "$CONFIG_FILE" \
  -f "$SCRIPT_DIR/compose.persistence.yml" \
  ps
