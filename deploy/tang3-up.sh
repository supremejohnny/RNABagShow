#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_ROOT="${RNABAG_DEPLOY_ROOT:-/home/johnny/services/rnabag}"
CONFIG_FILE="${RNABAG_CONFIG_FILE:-$DEPLOY_ROOT/config/tang3.env}"
CODE_DIR="${RNABAG_CODE_DIR-}"
TEMP_DIR="${RNABAG_TEMP_DIR-}"
BIND_IP="${RNABAG_APP_BIND_IP-}"
GPU_ID="${RNABAG_GPU_DEVICE_ID-}"

[[ -f "$CONFIG_FILE" ]] || { echo "Tang3 config is missing: $CONFIG_FILE" >&2; exit 1; }
config_value() { sed -n "s/^$1=//p" "$CONFIG_FILE" | tail -n 1; }
CODE_DIR="${CODE_DIR:-$(config_value RNABAG_CODE_DIR)}"
TEMP_DIR="${TEMP_DIR:-$(config_value RNABAG_TEMP_DIR)}"
BIND_IP="${BIND_IP:-$(config_value RNABAG_APP_BIND_IP)}"
GPU_ID="${GPU_ID:-$(config_value RNABAG_GPU_DEVICE_ID)}"
[[ -d "$CODE_DIR" ]] || { echo "Code directory is missing: $CODE_DIR" >&2; exit 1; }
[[ -d "$TEMP_DIR" ]] || { echo "Temporary directory is missing: $TEMP_DIR" >&2; exit 1; }
[[ -d "$DEPLOY_ROOT/postgres" && -d "$DEPLOY_ROOT/object-storage" ]] || {
  echo "Tang3 persistence directories are missing under $DEPLOY_ROOT." >&2
  exit 1
}
python3 - "$BIND_IP" <<'PY' >/dev/null 2>&1 || { echo "Invalid RNABAG_APP_BIND_IP." >&2; exit 1; }
import ipaddress
import sys
ipaddress.IPv4Address(sys.argv[1])
PY
ip -4 address show | grep -Fq "inet $BIND_IP/" || {
  echo "RNABAG_APP_BIND_IP is not assigned to this host: $BIND_IP" >&2
  exit 1
}
[[ "$GPU_ID" =~ ^[0-9]+$ ]] || { echo "RNABAG_GPU_DEVICE_ID must be numeric." >&2; exit 1; }
command -v docker >/dev/null 2>&1 || { echo "docker is required." >&2; exit 1; }
docker info >/dev/null 2>&1 || { echo "The current user cannot access Docker." >&2; exit 1; }
docker run --rm --gpus "device=$GPU_ID" nvidia/cuda:12.1.1-base-ubuntu22.04 nvidia-smi >/dev/null 2>&1 || {
  echo "Configured GPU is unavailable: $GPU_ID" >&2
  exit 1
}

RUNNING_SERVICES="$(docker compose --env-file "$CONFIG_FILE" -f "$SCRIPT_DIR/compose.persistence.yml" ps --status running --services)"
grep -qx postgres <<<"$RUNNING_SERVICES" && grep -qx minio <<<"$RUNNING_SERVICES" || {
  echo "PostgreSQL and MinIO must be running first." >&2
  echo "Run deploy/persistence-up.sh with the tang3 config, then retry." >&2
  exit 1
}

export RNABAG_UID="$(id -u)" RNABAG_GID="$(id -g)" RNABAG_CODE_DIR TEMP_DIR RNABAG_TEMP_DIR="$TEMP_DIR" RNABAG_APP_BIND_IP="$BIND_IP" RNABAG_GPU_DEVICE_ID="$GPU_ID"
docker compose --env-file "$CONFIG_FILE" -f "$SCRIPT_DIR/compose.app-gpu.yml" up -d --build --wait --force-recreate
docker compose --env-file "$CONFIG_FILE" -f "$SCRIPT_DIR/compose.app-gpu.yml" ps
echo "RNABag GPU service is listening on http://$BIND_IP:8000/"
