#!/usr/bin/env bash

set -euo pipefail

DEPLOY_ROOT="${RNABAG_DEPLOY_ROOT:-/home/johnny/services/rnabag}"
CONFIG_DIR="$DEPLOY_ROOT/config"
CONFIG_FILE="$CONFIG_DIR/persistence.env"

if [[ -e "$CONFIG_FILE" ]]; then
  echo "Refusing to overwrite existing config: $CONFIG_FILE" >&2
  exit 1
fi
if ! command -v openssl >/dev/null 2>&1; then
  echo "openssl is required to generate deployment secrets." >&2
  exit 1
fi

mkdir -p "$CONFIG_DIR"
chmod 700 "$CONFIG_DIR"
umask 077

POSTGRES_PASSWORD="$(openssl rand -hex 32)"
MINIO_ROOT_USER="rnabag-root-$(openssl rand -hex 8)"
MINIO_ROOT_PASSWORD="$(openssl rand -hex 32)"
S3_ACCESS_KEY="rnabag-app-$(openssl rand -hex 8)"
S3_SECRET_KEY="$(openssl rand -hex 32)"

{
  printf 'RNABAG_DEPLOY_ROOT=%s\n' "$DEPLOY_ROOT"
  printf 'RNABAG_POSTGRES_DATA_DIR=%s/postgres\n' "$DEPLOY_ROOT"
  printf 'RNABAG_OBJECT_DATA_DIR=%s/object-storage\n' "$DEPLOY_ROOT"
  printf 'POSTGRES_DB=rnabag\n'
  printf 'POSTGRES_USER=rnabag\n'
  printf 'POSTGRES_PASSWORD=%s\n' "$POSTGRES_PASSWORD"
  printf 'RNABAG_POSTGRES_PORT=5432\n'
  printf 'RNABAG_DATABASE_URL=postgresql://rnabag:%s@127.0.0.1:5432/rnabag\n' "$POSTGRES_PASSWORD"
  printf 'MINIO_ROOT_USER=%s\n' "$MINIO_ROOT_USER"
  printf 'MINIO_ROOT_PASSWORD=%s\n' "$MINIO_ROOT_PASSWORD"
  printf 'RNABAG_S3_ACCESS_KEY=%s\n' "$S3_ACCESS_KEY"
  printf 'RNABAG_S3_SECRET_KEY=%s\n' "$S3_SECRET_KEY"
  printf 'RNABAG_S3_BUCKET=rnabag-private-inputs\n'
  printf 'RNABAG_S3_ENDPOINT_URL=http://127.0.0.1:9000\n'
  printf 'RNABAG_S3_REGION=us-east-1\n'
  printf 'RNABAG_S3_PORT=9000\n'
  printf 'RNABAG_S3_CONSOLE_PORT=9001\n'
  printf 'RNABAG_PERSISTENCE_ENABLED=true\n'
  printf 'RNABAG_TEMP_DIR=%s/runtime/uploads-tmp\n' "$DEPLOY_ROOT"
  printf 'RNABAG_GATEWAY_BIND_IP=172.16.17.4\n'
  printf 'RNABAG_GATEWAY_PORT=8080\n'
  printf 'RNABAG_GATEWAY_ALLOWED_CIDR=172.28.0.0/24\n'
} >"$CONFIG_FILE"

chmod 600 "$CONFIG_FILE"
echo "Created private persistence config: $CONFIG_FILE"
