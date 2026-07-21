#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_ROOT="${RNABAG_DEPLOY_ROOT:-/home/johnny/services/rnabag}"
CONFIG_FILE="${RNABAG_CONFIG_FILE:-$DEPLOY_ROOT/config/tang3.env}"
[[ -f "$CONFIG_FILE" ]] || { echo "Tang3 config is missing: $CONFIG_FILE" >&2; exit 1; }
export RNABAG_UID="${RNABAG_UID:-$(id -u)}"
export RNABAG_GID="${RNABAG_GID:-$(id -g)}"
docker compose --env-file "$CONFIG_FILE" -f "$SCRIPT_DIR/compose.app-gpu.yml" down
