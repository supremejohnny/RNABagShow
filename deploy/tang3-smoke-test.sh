#!/usr/bin/env bash
set -euo pipefail
DEPLOY_ROOT="${RNABAG_DEPLOY_ROOT:-/home/johnny/services/rnabag}"
CONFIG_FILE="${RNABAG_CONFIG_FILE:-$DEPLOY_ROOT/config/tang3.env}"
APP_IP="${RNABAG_APP_BIND_IP:-100.113.222.1}"
APP_PORT="${RNABAG_APP_PORT:-8000}"
[[ -f "$CONFIG_FILE" ]] || { echo "Tang3 config is missing: $CONFIG_FILE" >&2; exit 1; }
if [[ -z "${RNABAG_APP_BIND_IP:-}" && -f "$CONFIG_FILE" ]]; then
  APP_IP="$(sed -n 's/^RNABAG_APP_BIND_IP=//p' "$CONFIG_FILE" | tail -n 1)"
fi
BASE_URL="http://$APP_IP:$APP_PORT"
curl --fail --silent --show-error "$BASE_URL/api/v1/health/live"; echo
curl --fail --silent --show-error "$BASE_URL/api/v1/health/ready"; echo
curl --fail --silent --show-error "$BASE_URL/api/v1/tasks" >/dev/null
curl --fail --silent --show-error "$BASE_URL/" >/dev/null
echo "RNABag tang3 smoke checks passed at $BASE_URL/"
