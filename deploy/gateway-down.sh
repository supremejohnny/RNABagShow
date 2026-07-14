#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_ROOT="${RNABAG_DEPLOY_ROOT:-/home/johnny/services/rnabag}"
CONFIG_FILE="${RNABAG_CONFIG_FILE:-$DEPLOY_ROOT/config/persistence.env}"

config_value() {
  local name="$1"
  sed -n "s/^${name}=//p" "$CONFIG_FILE" | tail -n 1
}

CONFIGURED_BIND_IP="$(config_value RNABAG_GATEWAY_BIND_IP)"
CONFIGURED_PORT="$(config_value RNABAG_GATEWAY_PORT)"
export RNABAG_GATEWAY_CONFIG_FILE="$DEPLOY_ROOT/config/nginx-intranet.conf"
export RNABAG_GATEWAY_BIND_IP="${RNABAG_GATEWAY_BIND_IP:-${CONFIGURED_BIND_IP:-172.16.17.4}}"
export RNABAG_GATEWAY_PORT="${RNABAG_GATEWAY_PORT:-${CONFIGURED_PORT:-8080}}"

docker compose \
  --env-file "$CONFIG_FILE" \
  -f "$SCRIPT_DIR/compose.gateway.yml" \
  down --remove-orphans

echo "RNABag intranet exposure is stopped. FastAPI and persistence were not stopped."
