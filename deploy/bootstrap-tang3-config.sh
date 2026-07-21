#!/usr/bin/env bash

set -euo pipefail

DEPLOY_ROOT="${RNABAG_DEPLOY_ROOT:-/home/johnny/services/rnabag}"
CODE_DIR="${RNABAG_CODE_DIR:-/mnt/nas/johnny/rnabag/RNABagShow}"
CONFIG_DIR="${RNABAG_CONFIG_DIR:-$DEPLOY_ROOT/config}"
CONFIG_FILE="${RNABAG_CONFIG_FILE:-$CONFIG_DIR/tang3.env}"
TEMP_DIR="${RNABAG_TEMP_DIR:-$DEPLOY_ROOT/runtime/uploads-tmp}"
BIND_IP="${RNABAG_APP_BIND_IP:-100.113.222.1}"

if [[ -e "$CONFIG_FILE" ]]; then
  echo "Refusing to overwrite existing config: $CONFIG_FILE" >&2
  exit 1
fi
if [[ ! -d "$CODE_DIR" ]]; then
  echo "RNABAG_CODE_DIR must be an existing directory: $CODE_DIR" >&2
  exit 1
fi
if ! python3 - "$BIND_IP" <<'PY'
import ipaddress
import sys
try:
    ipaddress.IPv4Address(sys.argv[1])
except ValueError:
    raise SystemExit(1)
PY
then
  echo "RNABAG_APP_BIND_IP must be an IPv4 address." >&2
  exit 1
fi
if ! command -v openssl >/dev/null 2>&1; then
  echo "openssl is required to generate deployment secrets." >&2
  exit 1
fi

umask 077
mkdir -p "$CONFIG_DIR" "$DEPLOY_ROOT/postgres" "$DEPLOY_ROOT/object-storage" "$DEPLOY_ROOT/runtime" "$TEMP_DIR" "$DEPLOY_ROOT/backups"
chmod 700 "$CONFIG_DIR" "$DEPLOY_ROOT/postgres" "$DEPLOY_ROOT/object-storage" "$DEPLOY_ROOT/runtime" "$TEMP_DIR" "$DEPLOY_ROOT/backups"

POSTGRES_PASSWORD="$(openssl rand -hex 32)"
MINIO_ROOT_USER="rnabag-root-$(openssl rand -hex 8)"
MINIO_ROOT_PASSWORD="$(openssl rand -hex 32)"
S3_ACCESS_KEY="rnabag-app-$(openssl rand -hex 8)"
S3_SECRET_KEY="$(openssl rand -hex 32)"

{
  printf 'RNABAG_DEPLOY_ROOT=%s\n' "$DEPLOY_ROOT"
  printf 'RNABAG_CODE_DIR=%s\n' "$CODE_DIR"
  printf 'RNABAG_POSTGRES_DATA_DIR=%s/postgres\n' "$DEPLOY_ROOT"
  printf 'RNABAG_OBJECT_DATA_DIR=%s/object-storage\n' "$DEPLOY_ROOT"
  printf 'POSTGRES_DB=rnabag\nPOSTGRES_USER=rnabag\nPOSTGRES_PASSWORD=%s\n' "$POSTGRES_PASSWORD"
  printf 'RNABAG_POSTGRES_PORT=5432\nRNABAG_DATABASE_URL=postgresql://rnabag:%s@127.0.0.1:5432/rnabag\n' "$POSTGRES_PASSWORD"
  printf 'MINIO_ROOT_USER=%s\nMINIO_ROOT_PASSWORD=%s\n' "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD"
  printf 'RNABAG_S3_ACCESS_KEY=%s\nRNABAG_S3_SECRET_KEY=%s\n' "$S3_ACCESS_KEY" "$S3_SECRET_KEY"
  printf 'RNABAG_S3_BUCKET=rnabag-private-inputs\nRNABAG_S3_ENDPOINT_URL=http://127.0.0.1:9000\nRNABAG_S3_REGION=us-east-1\nRNABAG_S3_PORT=9000\nRNABAG_S3_CONSOLE_PORT=9001\n'
  printf 'RNABAG_PERSISTENCE_ENABLED=true\nRNABAG_TEMP_DIR=%s\n' "$TEMP_DIR"
  printf 'RNABAG_APP_BIND_IP=%s\nRNABAG_APP_PORT=8000\nRNABAG_GPU_DEVICE_ID=0\n' "$BIND_IP"
} >"$CONFIG_FILE"
chmod 600 "$CONFIG_FILE"
echo "Created private tang3 config: $CONFIG_FILE"
