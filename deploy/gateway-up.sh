#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_ROOT="${RNABAG_DEPLOY_ROOT:-/home/johnny/services/rnabag}"
CONFIG_FILE="${RNABAG_CONFIG_FILE:-$DEPLOY_ROOT/config/persistence.env}"

if [[ ! -f "$CONFIG_FILE" ]]; then
  echo "Deployment config is missing: $CONFIG_FILE" >&2
  exit 1
fi
if ! docker info >/dev/null 2>&1; then
  echo "The current user cannot access Docker." >&2
  exit 1
fi

config_value() {
  local name="$1"
  sed -n "s/^${name}=//p" "$CONFIG_FILE" | tail -n 1
}

CONFIGURED_BIND_IP="$(config_value RNABAG_GATEWAY_BIND_IP)"
CONFIGURED_PORT="$(config_value RNABAG_GATEWAY_PORT)"
export RNABAG_GATEWAY_CONFIG_FILE="$DEPLOY_ROOT/config/nginx-intranet.conf"
export RNABAG_GATEWAY_BIND_IP="${RNABAG_GATEWAY_BIND_IP:-${CONFIGURED_BIND_IP:-172.16.17.4}}"
export RNABAG_GATEWAY_PORT="${RNABAG_GATEWAY_PORT:-${CONFIGURED_PORT:-8080}}"

"$SCRIPT_DIR/bootstrap-gateway-config.sh"
"$SCRIPT_DIR/app-smoke-test.sh" >/dev/null

docker compose \
  --env-file "$CONFIG_FILE" \
  -f "$SCRIPT_DIR/compose.gateway.yml" \
  run --rm --no-deps gateway nginx -t

docker compose \
  --env-file "$CONFIG_FILE" \
  -f "$SCRIPT_DIR/compose.gateway.yml" \
  up -d --wait

docker compose \
  --env-file "$CONFIG_FILE" \
  -f "$SCRIPT_DIR/compose.gateway.yml" \
  ps

curl --fail --silent --show-error \
  "http://127.0.0.1:$RNABAG_GATEWAY_PORT/api/v1/health/ready" \
  >/dev/null

echo "RNABag intranet gateway is ready:"
echo "http://$RNABAG_GATEWAY_BIND_IP:$RNABAG_GATEWAY_PORT/"
