#!/usr/bin/env bash

set -euo pipefail

DEPLOY_ROOT="${RNABAG_DEPLOY_ROOT:-/home/johnny/services/rnabag}"
PERSISTENCE_CONFIG_FILE="${RNABAG_CONFIG_FILE:-$DEPLOY_ROOT/config/persistence.env}"
CONFIG_DIR="$DEPLOY_ROOT/config"
GATEWAY_CONFIG_FILE="$CONFIG_DIR/nginx-intranet.conf"

config_value() {
  local name="$1"
  if [[ -f "$PERSISTENCE_CONFIG_FILE" ]]; then
    sed -n "s/^${name}=//p" "$PERSISTENCE_CONFIG_FILE" | tail -n 1
  fi
}

BIND_IP="${RNABAG_GATEWAY_BIND_IP:-$(config_value RNABAG_GATEWAY_BIND_IP)}"
BIND_IP="${BIND_IP:-172.16.17.4}"
PORT="${RNABAG_GATEWAY_PORT:-$(config_value RNABAG_GATEWAY_PORT)}"
PORT="${PORT:-8080}"
ALLOWED_CIDR="${RNABAG_GATEWAY_ALLOWED_CIDR:-$(config_value RNABAG_GATEWAY_ALLOWED_CIDR)}"
ALLOWED_CIDR="${ALLOWED_CIDR:-172.28.0.0/24}"

if [[ ! "$BIND_IP" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]]; then
  echo "Invalid RNABAG_GATEWAY_BIND_IP: $BIND_IP" >&2
  exit 1
fi
if [[ ! "$PORT" =~ ^[0-9]+$ ]] || (( PORT < 1 || PORT > 65535 )); then
  echo "Invalid RNABAG_GATEWAY_PORT: $PORT" >&2
  exit 1
fi
if [[ ! "$ALLOWED_CIDR" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}/[0-9]{1,2}$ ]]; then
  echo "Invalid RNABAG_GATEWAY_ALLOWED_CIDR: $ALLOWED_CIDR" >&2
  exit 1
fi

mkdir -p "$CONFIG_DIR"
chmod 700 "$CONFIG_DIR"

if [[ -d "$GATEWAY_CONFIG_FILE" ]]; then
  if find "$GATEWAY_CONFIG_FILE" -mindepth 1 -print -quit | grep -q .; then
    echo "Gateway config path is a non-empty directory; refusing to replace it:" >&2
    echo "$GATEWAY_CONFIG_FILE" >&2
    exit 1
  fi
  rmdir "$GATEWAY_CONFIG_FILE"
fi

if [[ -e "$GATEWAY_CONFIG_FILE" ]]; then
  if [[ ! -f "$GATEWAY_CONFIG_FILE" ]]; then
    echo "Gateway config path is not a regular file: $GATEWAY_CONFIG_FILE" >&2
    exit 1
  fi
  chmod 600 "$GATEWAY_CONFIG_FILE"
  echo "Using existing private gateway config: $GATEWAY_CONFIG_FILE"
  exit 0
fi

umask 077
{
  printf 'server {\n'
  printf '    listen %s:%s;\n' "$BIND_IP" "$PORT"
  printf '    listen 127.0.0.1:%s;\n' "$PORT"
  printf '    server_name _;\n\n'
  printf '    allow 127.0.0.1;\n'
  printf '    allow %s;\n' "$ALLOWED_CIDR"
  printf '    deny all;\n\n'
  printf '    client_max_body_size 2g;\n'
  printf '    client_body_timeout 900s;\n\n'
  printf '    location / {\n'
  printf '        proxy_pass http://127.0.0.1:8000;\n'
  printf '        proxy_http_version 1.1;\n'
  printf '        proxy_request_buffering off;\n'
  printf '        proxy_buffering off;\n'
  printf '        proxy_connect_timeout 30s;\n'
  printf '        proxy_send_timeout 900s;\n'
  printf '        proxy_read_timeout 900s;\n'
  printf '        proxy_set_header Host $host;\n'
  printf '        proxy_set_header X-Real-IP $remote_addr;\n'
  printf '        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;\n'
  printf '        proxy_set_header X-Forwarded-Proto $scheme;\n'
  printf '    }\n'
  printf '}\n'
} >"$GATEWAY_CONFIG_FILE"

chmod 600 "$GATEWAY_CONFIG_FILE"
echo "Created private gateway config: $GATEWAY_CONFIG_FILE"
echo "Allowed client network: $ALLOWED_CIDR"
